from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import ValidationError

from app.config import get_settings
from app.graph.workflow import shutdown_graph
from app.graph.runtime import ensure_checkpointer
from app.models import (
    CreateThreadBody,
    CreateWorkflowBody,
    CreateWorkflowRunBody,
    ResumeBody,
    ThreadStateResponse,
    UpdateWorkflowBody,
)
from app.roles.schema import CreateRoleBody, UpdateRoleBody
from app.roles.store import (
    create_role,
    delete_role,
    duplicate_role,
    ensure_seeded as ensure_roles_seeded,
    get_role,
    list_roles,
    update_role,
)
from app.sandbox import PREVIEW_ROOT, build_preview_from_dir
from app.agents.tools import workspace_dir_for
from app.service import (
    backfill_missing_snapshots,
    create_thread_meta,
    delete_thread_meta,
    get_thread_meta,
    get_thread_state,
    list_threads,
    list_threads_for_workflow,
    retry_run,
    resume_run,
    start_run,
)
from app.workflows.schema import WorkflowEdge, WorkflowNode
from app.workflows.store import (
    create_workflow,
    delete_workflow,
    duplicate_workflow,
    ensure_seeded,
    get_workflow,
    list_workflows,
    update_workflow,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
)
logger = logging.getLogger('workflow_agent.api')


def _resolve_preview_entry(preview_id: str) -> Path:
    run_dir = PREVIEW_ROOT / preview_id
    marker = run_dir / 'entry_dir.txt'
    if not marker.exists():
        raise FileNotFoundError(preview_id)
    relative = marker.read_text(encoding='utf-8').strip()
    entry_dir = (run_dir / relative).resolve()
    if not entry_dir.exists():
        raise FileNotFoundError(preview_id)
    return entry_dir


def _workflow_summary(item: Any) -> dict[str, Any]:
    return {
        'id': item.id,
        'name': item.name,
        'description': item.description,
        'builtin': item.builtin,
        'updated_at': item.updated_at,
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    ensure_seeded()
    ensure_roles_seeded()
    await ensure_checkpointer()
    backfilled = backfill_missing_snapshots()
    if backfilled:
        logger.info('Backfilled workflow_snapshot for %s legacy thread(s)', backfilled)
    logger.info(
        'API starting (mock_llm=%s, model=%s)',
        settings.should_use_mock,
        settings.openai_model,
    )
    yield
    await shutdown_graph()
    logger.info('API shutdown complete')


app = FastAPI(title='Multi-Agent-Workflow API', version='0.1.0', lifespan=lifespan)
settings = get_settings()
cors_origins = settings.cors_origin_list or ['http://localhost:5173']
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials='*' not in cors_origins,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.get('/health')
async def health() -> dict[str, Any]:
    s = get_settings()
    return {
        'status': 'ok',
        'mock_llm': s.should_use_mock,
        'model': s.openai_model,
    }


@app.get('/workflows')
async def workflows() -> dict[str, Any]:
    ensure_seeded()
    items = list_workflows()
    return {'workflows': [_workflow_summary(item) for item in items]}


@app.post('/workflows')
async def create_workflow_endpoint(body: CreateWorkflowBody) -> dict[str, Any]:
    nodes = [WorkflowNode.model_validate(n) for n in body.nodes] if body.nodes is not None else None
    edges = [WorkflowEdge.model_validate(e) for e in body.edges] if body.edges is not None else None
    item = create_workflow(
        name=body.name,
        description=body.description,
        nodes=nodes,
        edges=edges,
    )
    return item.model_dump()


@app.get('/workflows/{workflow_id}')
async def read_workflow(workflow_id: str) -> dict[str, Any]:
    ensure_seeded()
    item = get_workflow(workflow_id)
    if item is None:
        raise HTTPException(status_code=404, detail='Workflow not found')
    return item.model_dump()


@app.put('/workflows/{workflow_id}')
async def put_workflow(workflow_id: str, body: UpdateWorkflowBody) -> dict[str, Any]:
    fields: dict[str, Any] = body.model_dump(exclude_unset=True)
    try:
        item = update_workflow(workflow_id, **fields)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Workflow not found') from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        detail = exc.args[0] if exc.args else str(exc)
        raise HTTPException(status_code=422, detail=detail) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    return item.model_dump()


@app.delete('/workflows/{workflow_id}')
async def remove_workflow(workflow_id: str) -> dict[str, str]:
    try:
        delete_workflow(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Workflow not found') from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {'status': 'deleted'}


@app.post('/workflows/{workflow_id}/duplicate')
async def duplicate_workflow_endpoint(workflow_id: str) -> dict[str, Any]:
    ensure_seeded()
    try:
        item = duplicate_workflow(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Workflow not found') from exc
    return item.model_dump()


@app.get('/workflows/{workflow_id}/runs')
async def list_workflow_runs(workflow_id: str) -> dict[str, Any]:
    ensure_seeded()
    if get_workflow(workflow_id) is None:
        raise HTTPException(status_code=404, detail='Workflow not found')
    items = list_threads_for_workflow(workflow_id)
    return {'threads': [item.model_dump() for item in items]}


@app.post('/workflows/{workflow_id}/runs')
async def create_workflow_run(workflow_id: str, body: CreateWorkflowRunBody) -> dict[str, str]:
    try:
        meta = create_thread_meta(body.user_request, workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'thread_id': meta.thread_id}


@app.get('/roles')
async def roles() -> dict[str, Any]:
    ensure_roles_seeded()
    items = list_roles()
    return {'roles': [item.model_dump() for item in items]}


@app.post('/roles')
async def create_role_endpoint(body: CreateRoleBody) -> dict[str, Any]:
    item = create_role(
        name=body.name,
        system_prompt=body.system_prompt,
        output_schema=body.output_schema,
        max_steps=body.max_steps,
    )
    return item.model_dump()


@app.get('/roles/{role_id}')
async def read_role(role_id: str) -> dict[str, Any]:
    ensure_roles_seeded()
    item = get_role(role_id)
    if item is None:
        raise HTTPException(status_code=404, detail='Role not found')
    return item.model_dump()


@app.put('/roles/{role_id}')
async def put_role(role_id: str, body: UpdateRoleBody) -> dict[str, Any]:
    fields: dict[str, Any] = body.model_dump(exclude_unset=True)
    try:
        item = update_role(role_id, **fields)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Role not found') from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return item.model_dump()


@app.delete('/roles/{role_id}')
async def remove_role(role_id: str) -> dict[str, str]:
    try:
        delete_role(role_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Role not found') from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {'status': 'deleted'}


@app.post('/roles/{role_id}/duplicate')
async def duplicate_role_endpoint(role_id: str) -> dict[str, Any]:
    ensure_roles_seeded()
    try:
        item = duplicate_role(role_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Role not found') from exc
    return item.model_dump()


@app.get('/threads/{thread_id}/workspace/files')
async def workspace_files(thread_id: str) -> dict[str, Any]:
    meta = get_thread_meta(thread_id)
    if meta is None:
        raise HTTPException(status_code=404, detail='Thread not found')
    root = workspace_dir_for(thread_id)
    if not root.exists():
        return {'files': []}
    files = [
        str(item.relative_to(root))
        for item in sorted(root.rglob('*'))
        if item.is_file()
    ]
    return {'files': files}


@app.get('/threads/{thread_id}/workspace/file')
async def workspace_file(thread_id: str, path: str) -> dict[str, str]:
    meta = get_thread_meta(thread_id)
    if meta is None:
        raise HTTPException(status_code=404, detail='Thread not found')
    root = workspace_dir_for(thread_id).resolve()
    normalized = path.replace('\\', '/').strip()
    if not normalized or normalized.startswith('/') or '..' in Path(normalized).parts:
        raise HTTPException(status_code=403, detail='Invalid path')
    target = (root / normalized).resolve()
    if not str(target).startswith(str(root)):
        raise HTTPException(status_code=403, detail='Invalid path')
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail='File not found')
    return {'path': normalized, 'content': target.read_text(encoding='utf-8', errors='replace')}


@app.get('/threads')
async def threads() -> dict[str, Any]:
    items = list_threads()
    return {'threads': [item.model_dump() for item in items]}


@app.post('/threads')
async def create_thread(body: CreateThreadBody) -> dict[str, str]:
    try:
        meta = create_thread_meta(body.user_request, body.workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {'thread_id': meta.thread_id}


@app.get('/threads/{thread_id}', response_model=ThreadStateResponse)
async def read_thread(thread_id: str) -> ThreadStateResponse:
    meta = get_thread_meta(thread_id)
    if meta is None:
        raise HTTPException(status_code=404, detail='Thread not found')
    try:
        return await get_thread_state(thread_id)
    except ValueError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('Failed to read thread %s', thread_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete('/threads/{thread_id}')
async def remove_thread(thread_id: str) -> dict[str, str]:
    try:
        delete_thread_meta(thread_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Thread not found') from exc
    return {'status': 'deleted'}


@app.post('/threads/{thread_id}/runs')
async def run_thread(thread_id: str, body: CreateThreadBody | None = None) -> StreamingResponse:
    meta = get_thread_meta(thread_id)
    if meta is None:
        raise HTTPException(status_code=404, detail='Thread not found')

    user_request = (body.user_request if body is not None else '') or meta.title
    # Prefer original request stored at creation time — re-read from body if provided
    if body is not None and body.user_request:
        user_request = body.user_request

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in start_run(thread_id, user_request):
                yield f'data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n'
        except Exception as exc:
            logger.exception('Run failed for %s', thread_id)
            yield f'data: {json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)}\n\n'

    return StreamingResponse(event_stream(), media_type='text/event-stream')


@app.post('/threads/{thread_id}/resume')
async def resume_thread(thread_id: str, body: ResumeBody) -> StreamingResponse:
    meta = get_thread_meta(thread_id)
    if meta is None:
        raise HTTPException(status_code=404, detail='Thread not found')

    decision = {
        'action': body.action,
        'message': body.message or '',
        'feedback': body.feedback or body.message or '',
    }

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in resume_run(thread_id, decision):
                yield f'data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n'
        except Exception as exc:
            logger.exception('Resume failed for %s', thread_id)
            yield f'data: {json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)}\n\n'

    return StreamingResponse(event_stream(), media_type='text/event-stream')


@app.post('/threads/{thread_id}/retry')
async def retry_thread(thread_id: str) -> StreamingResponse:
    meta = get_thread_meta(thread_id)
    if meta is None:
        raise HTTPException(status_code=404, detail='Thread not found')
    state = await get_thread_state(thread_id)
    if state.phase == 'done':
        raise HTTPException(status_code=409, detail='当前流程已结束，无需重试')
    if state.interrupt is not None:
        raise HTTPException(status_code=409, detail='当前节点等待人工确认，不能使用重试，请直接确认或修改')
    if not state.can_retry:
        raise HTTPException(status_code=409, detail='当前线程没有可恢复的待执行节点')

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in retry_run(thread_id):
                yield f'data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n'
        except Exception as exc:
            logger.exception('Retry failed for %s', thread_id)
            yield f'data: {json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)}\n\n'

    return StreamingResponse(event_stream(), media_type='text/event-stream')


@app.post('/threads/{thread_id}/preview')
async def build_thread_preview(thread_id: str) -> dict[str, str]:
    meta = get_thread_meta(thread_id)
    if meta is None:
        raise HTTPException(status_code=404, detail='Thread not found')
    workspace = workspace_dir_for(thread_id)
    if not workspace.exists() or not any(workspace.iterdir()):
        raise HTTPException(status_code=409, detail='当前线程的工作区还没有可预览的文件')
    try:
        result = await build_preview_from_dir(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception('Preview build failed for %s', thread_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        'preview_id': result.preview_id,
        'preview_url': f'/previews/{result.preview_id}/index.html',
        'logs': result.logs,
    }


@app.get('/previews/{preview_id}')
@app.get('/previews/{preview_id}/')
async def serve_preview_root(preview_id: str) -> FileResponse:
    return await serve_preview(preview_id, '')


@app.get('/previews/{preview_id}/{asset_path:path}')
async def serve_preview(preview_id: str, asset_path: str = '') -> FileResponse:
    try:
        entry_dir = _resolve_preview_entry(preview_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Preview not found') from exc

    requested = (entry_dir / asset_path).resolve() if asset_path else (entry_dir / 'index.html').resolve()
    if not requested.is_relative_to(entry_dir):
        raise HTTPException(status_code=403, detail='Invalid preview path')
    if requested.exists() and requested.is_file():
        return FileResponse(requested)

    fallback = entry_dir / 'index.html'
    if fallback.exists():
        return FileResponse(fallback)
    raise HTTPException(status_code=404, detail='Preview asset not found')
