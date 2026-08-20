from __future__ import annotations

from typing import Any

from app.workflows.conditions import validate_condition_path
from app.workflows.schema import WorkflowDef


def _reachable_targets(edges: list[Any], start_id: str) -> set[str]:
    """Nodes reachable from start_id (following source→target)."""
    outgoing: dict[str, list[str]] = {}
    for edge in edges:
        outgoing.setdefault(edge.source, []).append(edge.target)
    seen: set[str] = set()
    stack = [start_id]
    while stack:
        current = stack.pop()
        for nxt in outgoing.get(current, []):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def find_back_edges(workflow: WorkflowDef) -> set[str]:
    """Edge ids that close a loop: DFS from start; u→v is a back edge iff v is
    still on the DFS stack (gray) when u is explored. This singles out the
    "return" edge of each cycle instead of every edge on the cycle."""
    outgoing: dict[str, list[Any]] = {}
    for edge in workflow.edges:
        outgoing.setdefault(edge.source, []).append(edge)

    starts = [node.id for node in workflow.nodes if node.type == 'start']
    roots = starts or ([workflow.nodes[0].id] if workflow.nodes else [])

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}
    back: set[str] = set()
    for root in roots:
        if color.get(root, WHITE) != WHITE:
            continue
        color[root] = GRAY
        stack: list[tuple[str, Any]] = [(root, iter(outgoing.get(root, [])))]
        while stack:
            current, it = stack[-1]
            descended = False
            for edge in it:
                target_color = color.get(edge.target, WHITE)
                if target_color == GRAY:
                    back.add(edge.id)
                elif target_color == WHITE:
                    color[edge.target] = GRAY
                    stack.append((edge.target, iter(outgoing.get(edge.target, []))))
                    descended = True
                    break
            if not descended:
                color[current] = BLACK
                stack.pop()
    return back


def validate_workflow(workflow: WorkflowDef) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    nodes = workflow.nodes
    edges = workflow.edges
    node_ids = [node.id for node in nodes]

    seen: set[str] = set()
    for node in nodes:
        if node.id in seen:
            errors.append({
                'code': 'duplicate_node_id',
                'message': f'节点 id 重复: {node.id}',
                'node_id': node.id,
            })
        seen.add(node.id)

    seen_edges: set[str] = set()
    for edge in edges:
        if edge.id in seen_edges:
            errors.append({
                'code': 'duplicate_edge_id',
                'message': f'边 id 重复: {edge.id}',
                'edge_id': edge.id,
            })
        seen_edges.add(edge.id)

    starts = [n for n in nodes if n.type == 'start']
    ends = [n for n in nodes if n.type == 'end']
    if len(starts) != 1:
        errors.append({
            'code': 'start_count',
            'message': f'必须恰好一个 start 节点，当前 {len(starts)} 个',
        })
    if not ends:
        errors.append({'code': 'end_count', 'message': '至少需要一个 end 节点'})

    id_set = set(node_ids)
    for edge in edges:
        if edge.source not in id_set:
            errors.append({
                'code': 'missing_source',
                'message': f'边的 source 不存在: {edge.source}',
                'edge_id': edge.id,
            })
        if edge.target not in id_set:
            errors.append({
                'code': 'missing_target',
                'message': f'边的 target 不存在: {edge.target}',
                'edge_id': edge.id,
            })
        if edge.condition is not None:
            err = validate_condition_path(edge.condition.left)
            if err:
                errors.append({
                    'code': 'condition_path',
                    'message': err,
                    'edge_id': edge.id,
                })
            elif edge.condition.left.startswith('node_outputs.'):
                parts = edge.condition.left.split('.')
                if len(parts) >= 2 and parts[1] not in id_set:
                    errors.append({
                        'code': 'condition_node_ref',
                        'message': f'条件引用的节点不存在: {parts[1]}',
                        'edge_id': edge.id,
                    })

    # 可达性：所有节点从 start 可达
    if starts:
        reachable = _reachable_targets(edges, starts[0].id) | {starts[0].id}
        for node in nodes:
            if node.id not in reachable:
                errors.append({
                    'code': 'unreachable_node',
                    'message': f'节点从 start 不可达: {node.id}',
                    'node_id': node.id,
                })

    # 出边规则：多条出边时恰好一条 default（无条件）；条件边之外必须有 default
    outgoing: dict[str, list] = {node.id: [] for node in nodes}
    for edge in edges:
        if edge.source in outgoing:
            outgoing[edge.source].append(edge)

    back_edges = find_back_edges(workflow)

    for node in nodes:
        outs = outgoing.get(node.id, [])
        defaults = [e for e in outs if e.condition is None]

        if node.type == 'end':
            continue
        if not outs:
            errors.append({
                'code': 'no_outgoing',
                'message': f'节点缺少出边: {node.id}',
                'node_id': node.id,
            })
        if len(outs) > 1 and len(defaults) != 1:
            errors.append({
                'code': 'default_edge_count',
                'message': f'节点 {node.id} 有 {len(outs)} 条出边，必须恰好一条无条件 default 边',
                'node_id': node.id,
            })
        for edge in defaults:
            if edge.id in back_edges:
                errors.append({
                    'code': 'default_is_back_edge',
                    'message': f'default 边不能是回头边（否则循环无法退出）: {edge.id}',
                    'edge_id': edge.id,
                    'node_id': node.id,
                })

        if node.type == 'agent':
            role_id = str((node.data or {}).get('role_id') or '')
            if not role_id.strip():
                errors.append({
                    'code': 'agent_missing_role',
                    'message': f'agent 节点未配置角色: {node.id}',
                    'node_id': node.id,
                })
        if node.type == 'hitl':
            options = (node.data or {}).get('options') or []
            if not options:
                errors.append({
                    'code': 'hitl_missing_options',
                    'message': f'hitl 节点未配置审批选项: {node.id}',
                    'node_id': node.id,
                })

    # 回头边必须有 max_iterations 兜底
    for edge in edges:
        if edge.id in back_edges and not edge.max_iterations:
            errors.append({
                'code': 'back_edge_no_limit',
                'message': f'回头边缺少 max_iterations: {edge.id}',
                'edge_id': edge.id,
            })

    return errors
