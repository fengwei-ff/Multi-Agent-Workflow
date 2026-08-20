from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from app.agents.loop import run_agent_loop
from app.agents.tools import Workspace, workspace_dir_for
from app.models import WorkflowState
from app.roles.store import ensure_seeded as ensure_roles_seeded, get_role
from app.workflows.conditions import resolve_path

logger = logging.getLogger('workflow_agent.nodes')

_PLACEHOLDER_RE = re.compile(r'\{([a-zA-Z_][\w.]*)\}')


def render_template(template: str, state: WorkflowState) -> str:
    """Render {dot.path} placeholders against state; unknown paths render as ''."""
    def _sub(match: re.Match) -> str:
        value = resolve_path(dict(state), match.group(1))
        if value is None:
            return ''
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    try:
        return _PLACEHOLDER_RE.sub(_sub, template)
    except Exception:
        logger.exception('Failed to render template')
        return template


async def node_start(state: WorkflowState) -> dict[str, Any]:
    return {'phase': state.get('phase') or 'running'}


async def node_end(state: WorkflowState) -> dict[str, Any]:
    return {'phase': 'done'}


async def node_agent(
    state: WorkflowState,
    config: RunnableConfig,
    *,
    node_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    role_id = str(data.get('role_id') or '')
    ensure_roles_seeded()
    role = get_role(role_id)
    if role is None:
        raise ValueError(f'agent 节点 {node_id} 引用的角色不存在: {role_id}')

    task_template = str(data.get('task_template') or '{user_request}')
    task_text = render_template(task_template, state)
    max_steps = data.get('max_steps')

    thread_id = str((config.get('configurable') or {}).get('thread_id') or 'default')
    workspace = Workspace(workspace_dir_for(thread_id))
    artifact_queue = (config.get('configurable') or {}).get('artifact_queue')

    async def emit(event: dict[str, Any]) -> None:
        if artifact_queue is not None:
            await artifact_queue.put({'type': 'agent', 'node': node_id, **event})

    result = await run_agent_loop(
        role=role,
        task_text=task_text,
        workspace=workspace,
        max_steps=int(max_steps) if max_steps else None,
        emit=emit,
    )

    summary = str(result.get('summary') or f'{role.name} 已完成')
    return {
        'node_outputs': {node_id: result},
        'active_node_id': node_id,
        'last_assistant_message': summary,
        'messages': [AIMessage(content=f'[{role.name}] {summary}')],
    }


async def node_hitl(
    state: WorkflowState,
    *,
    node_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    title = str(data.get('title') or '人工审批')
    options = list(data.get('options') or ['approve', 'reject'])
    summary_fields = list(data.get('summary_fields') or [])

    summary_parts: list[str] = []
    for field in summary_fields:
        value = resolve_path(dict(state), str(field))
        if value is None:
            continue
        rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        summary_parts.append(f'## {field}\n{rendered}')
    summary = '\n\n'.join(summary_parts) or str(state.get('last_assistant_message') or '')

    payload = {
        'kind': 'approval',
        'title': title,
        'summary': summary,
        'options': options,
        'payload': {'node_id': node_id},
    }
    decision = interrupt(payload)
    if not isinstance(decision, dict):
        decision = {'action': options[0] if options else 'approve'}

    action = str(decision.get('action') or (options[0] if options else 'approve'))
    message = str(decision.get('message') or decision.get('feedback') or '').strip()

    updates: dict[str, Any] = {
        'hitl': {'node_id': node_id, 'action': action, 'message': message},
        'active_node_id': node_id,
    }
    if message:
        updates['messages'] = [AIMessage(content=f'[审批 {title}] {action}: {message}')]
    return updates


def make_counter_node(edge_id: str):
    """Synthetic node inserted on back edges to count loop iterations."""

    async def counter(state: WorkflowState) -> dict[str, Any]:
        return {'loop_counts': {edge_id: int((state.get('loop_counts') or {}).get(edge_id) or 0) + 1}}

    return counter
