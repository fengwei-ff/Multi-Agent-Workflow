from __future__ import annotations

from functools import partial
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import make_counter_node, node_agent, node_end, node_hitl, node_start
from app.models import WorkflowState
from app.workflows.conditions import eval_condition
from app.workflows.schema import WorkflowDef, WorkflowEdge
from app.workflows.validate import find_back_edges, validate_workflow

DEFAULT_MAX_ITERATIONS = 5


def counter_node_name(edge_id: str) -> str:
    return f'__count__{edge_id}'


def make_edge_router(edges: list[WorkflowEdge], back_edges: set[str]) -> Callable[[WorkflowState], str]:
    """Router returns the selected edge.id; back edges are skipped once over budget."""

    def router(state: WorkflowState) -> str:
        counts = state.get('loop_counts') or {}
        for edge in edges:
            if edge.condition is None:
                continue
            if edge.id in back_edges:
                limit = edge.max_iterations or DEFAULT_MAX_ITERATIONS
                if int(counts.get(edge.id) or 0) >= limit:
                    continue
            try:
                if eval_condition(edge.condition.model_dump(), dict(state)):
                    return edge.id
            except ValueError:
                continue
        for edge in edges:
            if edge.condition is None:
                return edge.id
        raise ValueError(f'没有可用的出边（条件均不满足且无 default 边），source={edges[0].source}')

    return router


def compile_workflow_builder(workflow: WorkflowDef) -> StateGraph:
    errors = validate_workflow(workflow)
    if errors:
        raise ValueError(errors)

    back_edges = find_back_edges(workflow)

    outgoing: dict[str, list[WorkflowEdge]] = {node.id: [] for node in workflow.nodes}
    for edge in workflow.edges:
        if edge.source in outgoing:
            outgoing[edge.source].append(edge)

    builder = StateGraph(WorkflowState)

    def resolve_target(edge: WorkflowEdge) -> Any:
        if edge.id in back_edges:
            return counter_node_name(edge.id)
        return edge.target

    # 回头边计数器节点
    for edge in workflow.edges:
        if edge.id in back_edges:
            builder.add_node(counter_node_name(edge.id), make_counter_node(edge.id))
            builder.add_edge(counter_node_name(edge.id), edge.target)

    for node in workflow.nodes:
        if node.type == 'start':
            builder.add_node(node.id, node_start)
        elif node.type == 'end':
            builder.add_node(node.id, node_end)
        elif node.type == 'agent':
            builder.add_node(node.id, partial(node_agent, node_id=node.id, data=dict(node.data or {})))
        elif node.type == 'hitl':
            builder.add_node(node.id, partial(node_hitl, node_id=node.id, data=dict(node.data or {})))
        else:
            raise ValueError(f'未知节点类型: {node.type}')

    starts = [node for node in workflow.nodes if node.type == 'start']
    for start in starts:
        builder.add_edge(START, start.id)

    for node in workflow.nodes:
        outs = outgoing.get(node.id, [])
        if not outs:
            if node.type == 'end':
                builder.add_edge(node.id, END)
            continue

        needs_router = len(outs) > 1 or any(e.condition is not None for e in outs) or any(
            e.id in back_edges for e in outs
        )
        if needs_router:
            router = make_edge_router(outs, back_edges)
            path_map = {edge.id: resolve_target(edge) for edge in outs}
            builder.add_conditional_edges(node.id, router, path_map)
        else:
            builder.add_edge(node.id, resolve_target(outs[0]))

    return builder
