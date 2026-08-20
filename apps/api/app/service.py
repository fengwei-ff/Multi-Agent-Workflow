from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.types import Command

from app.agents.tools import workspace_dir_for
from app.models import (
    ChatMessage,
    InterruptPayload,
    ThreadMeta,
    ThreadStateResponse,
)
from app.persistence import JsonCollectionStore, database_path_for

logger = logging.getLogger('workflow_agent.service')

_DATA_DIR = Path(__file__).resolve().parents[1] / '.data'
_DEFAULT_META_PATH = _DATA_DIR / 'metadata.db'
_LEGACY_META_PATH = _DATA_DIR / 'threads.json'
_META_PATH = _DEFAULT_META_PATH
T = TypeVar('T')

DEFAULT_WORKFLOW_ID = 'dev_delivery'
_run_locks: dict[str, asyncio.Lock] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_meta() -> dict[str, ThreadMeta]:
    return _parse_meta(_store().load())


def _parse_meta(raw: dict[str, object]) -> dict[str, ThreadMeta]:
    items: dict[str, ThreadMeta] = {}
    for key, value in raw.items():
        try:
            items[key] = ThreadMeta.model_validate(value)
        except Exception:
            logger.warning('Skipping invalid thread meta entry: %s', key)
    return items


def _save_meta(meta: dict[str, ThreadMeta]) -> None:
    _store().replace({key: value.model_dump() for key, value in meta.items()})


def _store() -> JsonCollectionStore:
    legacy_path = _LEGACY_META_PATH if _META_PATH == _DEFAULT_META_PATH else _META_PATH
    return JsonCollectionStore(database_path_for(_META_PATH), 'threads', legacy_path)


def _mutate_meta(callback: Callable[[dict[str, ThreadMeta]], T]) -> T:
    def mutate(raw: dict[str, object]) -> T:
        meta = _parse_meta(raw)
        result = callback(meta)
        raw.clear()
        raw.update({key: value.model_dump() for key, value in meta.items()})
        return result

    return _store().mutate(mutate)


def list_threads() -> list[ThreadMeta]:
    meta = _load_meta()
    return sorted(meta.values(), key=lambda item: item.updated_at, reverse=True)


def list_threads_for_workflow(workflow_id: str) -> list[ThreadMeta]:
    return [item for item in list_threads() if item.workflow_id == workflow_id]


def get_thread_meta(thread_id: str) -> ThreadMeta | None:
    return _load_meta().get(thread_id)


def delete_thread_meta(thread_id: str) -> None:
    def delete(meta: dict[str, ThreadMeta]) -> None:
        if thread_id not in meta:
            raise KeyError(thread_id)
        del meta[thread_id]

    _mutate_meta(delete)


def create_thread_meta(user_request: str, workflow_id: str) -> ThreadMeta:
    from app.roles.store import ensure_seeded as ensure_roles_seeded, get_role
    from app.workflows.store import ensure_seeded, get_workflow
    from app.workflows.validate import validate_workflow

    ensure_seeded()
    ensure_roles_seeded()
    wf = get_workflow(workflow_id)
    if wf is None:
        raise ValueError(f'Unknown workflow_id: {workflow_id}')
    errors = validate_workflow(wf)
    if errors:
        raise ValueError(f'Invalid workflow: {errors}')

    for node in wf.nodes:
        if node.type == 'agent':
            role_id = str((node.data or {}).get('role_id') or '')
            if get_role(role_id) is None:
                raise ValueError(f'agent 节点 {node.id} 引用的角色不存在: {role_id}')

    thread_id = str(uuid.uuid4())
    title = user_request.strip().replace('\n', ' ')[:48] or '未命名需求'
    now = _now()
    item = ThreadMeta(
        thread_id=thread_id,
        title=title,
        workflow_id=workflow_id,
        workflow_name=wf.name,
        workflow_snapshot=deepcopy(wf.model_dump()),
        created_at=now,
        updated_at=now,
    )
    _mutate_meta(lambda meta: meta.__setitem__(thread_id, item))
    return item


def touch_thread(thread_id: str) -> None:
    def touch(meta: dict[str, ThreadMeta]) -> None:
        item = meta.get(thread_id)
        if item is None:
            return
        item.updated_at = _now()
        meta[thread_id] = item

    _mutate_meta(touch)


def backfill_missing_snapshots() -> int:
    """For threads missing workflow_snapshot, copy current template by workflow_id (fallback dev_delivery). Returns count updated."""
    from app.workflows.store import ensure_seeded, get_workflow

    ensure_seeded()
    def backfill(meta: dict[str, ThreadMeta]) -> int:
        updated = 0
        for item in meta.values():
            needs_snapshot = item.workflow_snapshot is None
            needs_name = not (item.workflow_name or '').strip()
            if not needs_snapshot and not needs_name:
                continue

            workflow_id = item.workflow_id or DEFAULT_WORKFLOW_ID
            wf = get_workflow(workflow_id) or get_workflow(DEFAULT_WORKFLOW_ID)
            if wf is None:
                logger.warning('Cannot backfill thread %s: workflow not found', item.thread_id)
                continue

            if needs_snapshot:
                item.workflow_snapshot = deepcopy(wf.model_dump())
            if needs_name:
                item.workflow_name = wf.name
            meta[item.thread_id] = item
            updated += 1
        return updated

    return _mutate_meta(backfill)


async def _graph_for_thread(thread_id: str):
    from app.graph.runtime import get_graph_for_snapshot
    from app.workflows.schema import WorkflowDef
    from app.workflows.store import ensure_seeded, get_workflow

    meta = get_thread_meta(thread_id)
    if meta and meta.workflow_snapshot:
        try:
            snap = WorkflowDef.model_validate(meta.workflow_snapshot)
        except Exception as exc:
            raise ValueError(
                '该历史 run 使用旧版节点体系，已归档不可查看/恢复'
            ) from exc
    else:
        ensure_seeded()
        workflow_id = (meta.workflow_id if meta else None) or DEFAULT_WORKFLOW_ID
        snap = get_workflow(workflow_id) or get_workflow(DEFAULT_WORKFLOW_ID)
        if snap is None:
            raise ValueError(f'Workflow not found for thread {thread_id}: {workflow_id}')
    return await get_graph_for_snapshot(snap)


def _message_to_chat(msg: Any) -> ChatMessage | None:
    if isinstance(msg, dict):
        role = msg.get('role') or msg.get('type')
        content = msg.get('content', '')
        if role in {'human', 'user'}:
            return ChatMessage(role='user', content=str(content))
        if role in {'ai', 'assistant'}:
            return ChatMessage(role='assistant', content=str(content))
        if role == 'system':
            return ChatMessage(role='system', content=str(content))
        return None

    if isinstance(msg, BaseMessage):
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        msg_type = getattr(msg, 'type', '')
        if msg_type == 'human':
            return ChatMessage(role='user', content=content)
        if msg_type == 'ai':
            return ChatMessage(role='assistant', content=content)
        if msg_type == 'system':
            return ChatMessage(role='system', content=content)
    return None


def _extract_interrupt(snapshot: Any) -> InterruptPayload | None:
    interrupts = getattr(snapshot, 'interrupts', None) or ()
    if not interrupts:
        tasks = getattr(snapshot, 'tasks', None) or ()
        collected = []
        for task in tasks:
            collected.extend(getattr(task, 'interrupts', None) or [])
        interrupts = collected

    if not interrupts:
        return None

    first = interrupts[0]
    value = getattr(first, 'value', first)
    if isinstance(value, dict):
        try:
            return InterruptPayload.model_validate(value)
        except Exception:
            return InterruptPayload(
                kind='approval',
                title='需要确认',
                summary=str(value),
                options=['approve', 'reject'],
            )
    return InterruptPayload(
        kind='approval',
        title='需要确认',
        summary=str(value),
        options=['approve', 'reject'],
    )


def state_to_response(thread_id: str, snapshot: Any) -> ThreadStateResponse:
    values = snapshot.values if snapshot is not None else {}
    values = values or {}
    messages_raw = values.get('messages') or []
    messages: list[ChatMessage] = []
    for item in messages_raw:
        converted = _message_to_chat(item)
        if converted is not None:
            messages.append(converted)

    interrupt_payload = _extract_interrupt(snapshot) if snapshot is not None else None
    next_nodes = list(getattr(snapshot, 'next', None) or [])
    interrupted = interrupt_payload is not None or bool(next_nodes)
    can_retry = interrupt_payload is None and bool(next_nodes)

    phase = str(values.get('phase') or 'running')

    meta = get_thread_meta(thread_id)
    workflow_nodes: list[dict[str, Any]] = []
    if meta and meta.workflow_snapshot:
        raw_nodes = meta.workflow_snapshot.get('nodes') or []
        if isinstance(raw_nodes, list):
            for node in raw_nodes:
                if not isinstance(node, dict):
                    continue
                node_id = node.get('id')
                node_type = node.get('type')
                if not node_id or not node_type:
                    continue
                workflow_nodes.append(
                    {
                        'id': str(node_id),
                        'type': str(node_type),
                        'data': node.get('data') if isinstance(node.get('data'), dict) else {},
                    }
                )

    hitl_raw = values.get('hitl')
    hitl = dict(hitl_raw) if isinstance(hitl_raw, dict) else None

    return ThreadStateResponse(
        thread_id=thread_id,
        phase=phase,
        workflow_id=meta.workflow_id if meta else None,
        workflow_name=meta.workflow_name if meta else None,
        workflow_nodes=workflow_nodes,
        user_request=str(values.get('user_request') or ''),
        active_node_id=str(values.get('active_node_id') or ''),
        node_outputs=dict(values.get('node_outputs') or {}),
        hitl=hitl,
        workspace_dir=str(values.get('workspace_dir') or ''),
        last_assistant_message=str(values.get('last_assistant_message') or ''),
        messages=messages,
        interrupted=interrupted and phase != 'done',
        interrupt=interrupt_payload if phase != 'done' else None,
        can_retry=can_retry and phase != 'done',
        pending_nodes=next_nodes if phase != 'done' else [],
    )


def _config(thread_id: str) -> dict[str, Any]:
    return {'configurable': {'thread_id': thread_id}}


async def get_thread_state(thread_id: str) -> ThreadStateResponse:
    graph = await _graph_for_thread(thread_id)
    snapshot = await graph.aget_state(_config(thread_id))
    return state_to_response(thread_id, snapshot)


async def start_run(thread_id: str, user_request: str) -> AsyncIterator[dict[str, Any]]:
    graph = await _graph_for_thread(thread_id)
    config = _config(thread_id)
    workspace = workspace_dir_for(thread_id)
    workspace.mkdir(parents=True, exist_ok=True)
    initial = {
        'user_request': user_request,
        'messages': [HumanMessage(content=user_request)],
        'phase': 'running',
        'node_outputs': {},
        'loop_counts': {},
        'workspace_dir': str(workspace),
        'active_node_id': '',
        'last_assistant_message': '',
    }

    async for event in _stream_events(graph, initial, config):
        yield event
    touch_thread(thread_id)


async def resume_run(thread_id: str, decision: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    graph = await _graph_for_thread(thread_id)
    config = _config(thread_id)
    async for event in _stream_events(graph, Command(resume=decision), config):
        yield event
    touch_thread(thread_id)


async def retry_run(thread_id: str) -> AsyncIterator[dict[str, Any]]:
    graph = await _graph_for_thread(thread_id)
    config = _config(thread_id)
    snapshot = await graph.aget_state(config)
    state = state_to_response(thread_id, snapshot)

    if state.phase == 'done':
        raise ValueError('当前流程已结束，无需重试')
    if state.interrupt is not None:
        raise ValueError('当前节点等待人工确认，不能使用重试，请直接确认或修改')
    if not state.can_retry:
        raise ValueError('当前线程没有可恢复的待执行节点')

    async for event in _stream_events(graph, None, config):
        yield event
    touch_thread(thread_id)


async def _stream_events(graph: Any, input_data: Any, config: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    event_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    # Custom top-level config keys get dropped by langchain ensure_config;
    # pass the queue through `configurable`, which is preserved.
    runtime_config = {
        **config,
        'configurable': {**config.get('configurable', {}), 'artifact_queue': event_queue},
    }

    async def run_graph() -> None:
        thread_id = str(config.get('configurable', {}).get('thread_id') or '')
        run_lock = _run_locks.setdefault(thread_id, asyncio.Lock())
        try:
            async with run_lock:
                async for chunk in graph.astream(input_data, config=runtime_config, stream_mode='updates'):
                    if not isinstance(chunk, dict):
                        continue
                    for node_name, update in chunk.items():
                        if node_name == '__interrupt__':
                            interrupts = update
                            value = None
                            if interrupts:
                                first = interrupts[0]
                                value = getattr(first, 'value', first)
                            await event_queue.put(
                                {
                                    'type': 'interrupt',
                                    'node': node_name,
                                    'data': value,
                                }
                            )
                            continue
                        await event_queue.put(
                            {
                                'type': 'node',
                                'node': node_name,
                                'data': _serialize_update(update),
                            }
                        )
        except Exception as exc:
            logger.exception('Graph stream failed')
            try:
                snapshot = await graph.aget_state(config)
                response = state_to_response(config['configurable']['thread_id'], snapshot)
                await event_queue.put({'type': 'state', 'data': response.model_dump()})
            except Exception:
                logger.exception('Failed to load checkpoint after graph error')
            await event_queue.put({'type': 'error', 'message': str(exc)})
            await event_queue.put(None)
            return

        snapshot = await graph.aget_state(config)
        response = state_to_response(config['configurable']['thread_id'], snapshot)
        await event_queue.put(
            {
                'type': 'state',
                'data': response.model_dump(),
            }
        )
        if response.interrupted and response.interrupt is not None:
            await event_queue.put(
                {
                    'type': 'interrupt',
                    'data': response.interrupt.model_dump(),
                }
            )
        await event_queue.put({'type': 'done'})
        await event_queue.put(None)

    task = asyncio.create_task(run_graph())
    try:
        while True:
            event = await event_queue.get()
            if event is None:
                break
            yield event
    finally:
        await task


def _serialize_update(update: Any) -> dict[str, Any]:
    if update is None:
        return {}
    if isinstance(update, dict):
        result: dict[str, Any] = {}
        for key, value in update.items():
            if key == 'messages':
                messages = []
                for msg in value or []:
                    converted = _message_to_chat(msg)
                    if converted is not None:
                        messages.append(converted.model_dump())
                result[key] = messages
            elif isinstance(value, (str, int, float, bool)) or value is None:
                result[key] = value
            elif isinstance(value, (list, dict)):
                try:
                    result[key] = json.loads(json.dumps(value, ensure_ascii=False, default=str))
                except Exception:
                    result[key] = str(value)
            else:
                result[key] = str(value)
        return result
    return {'value': str(update)}
