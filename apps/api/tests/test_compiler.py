from __future__ import annotations

import pytest

from app.graph.compiler import (
    DEFAULT_MAX_ITERATIONS,
    compile_workflow_builder,
    counter_node_name,
    make_edge_router,
)
from app.graph.nodes import make_counter_node
from app.workflows.schema import (
    EdgeCondition,
    WorkflowDef,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodePosition,
)
from app.workflows.seed import DEV_DELIVERY_WORKFLOW
from app.workflows.validate import find_back_edges, validate_workflow

TS = '2026-08-06T00:00:00+00:00'


def make_node(node_id: str, node_type: str = 'agent', data: dict | None = None) -> WorkflowNode:
    if data is None:
        data = {'role_id': 'backend_dev', 'task_template': '{user_request}'} if node_type == 'agent' else {}
    return WorkflowNode(
        id=node_id,
        type=node_type,
        position=WorkflowNodePosition(x=0, y=0),
        data=data,
    )


def make_workflow(nodes: list[WorkflowNode], edges: list[WorkflowEdge]) -> WorkflowDef:
    return WorkflowDef(
        id='test',
        name='test',
        builtin=False,
        created_at=TS,
        updated_at=TS,
        nodes=nodes,
        edges=edges,
    )


def builder_node_keys(builder) -> set[str]:
    nodes = getattr(builder, 'nodes', None) or {}
    return set(nodes.keys()) if isinstance(nodes, dict) else set(nodes)


def test_builtin_valid():
    assert validate_workflow(DEV_DELIVERY_WORKFLOW) == []


def test_compile_builtin_has_nodes_and_counters():
    builder = compile_workflow_builder(DEV_DELIVERY_WORKFLOW)
    keys = builder_node_keys(builder)
    for node_id in ('start', 'pm', 'hitl_req', 'backend', 'frontend', 'cr', 'qa', 'end'):
        assert node_id in keys
    back = find_back_edges(DEV_DELIVERY_WORKFLOW)
    for edge_id in back:
        assert counter_node_name(edge_id) in keys


def test_compile_invalid_raises():
    wf = make_workflow([make_node('a')], [])
    with pytest.raises(ValueError):
        compile_workflow_builder(wf)


def test_router_prefers_matching_condition():
    edges = [
        WorkflowEdge(
            id='cond',
            source='a',
            target='b',
            condition=EdgeCondition(left='hitl.action', op='eq', value='revise'),
        ),
        WorkflowEdge(id='default', source='a', target='c'),
    ]
    router = make_edge_router(edges, set())
    assert router({'hitl': {'action': 'revise'}}) == 'cond'
    assert router({'hitl': {'action': 'approve'}}) == 'default'
    assert router({}) == 'default'


def test_router_skips_over_budget_back_edge():
    edges = [
        WorkflowEdge(
            id='back',
            source='b',
            target='a',
            condition=EdgeCondition(left='hitl.action', op='eq', value='revise'),
            max_iterations=2,
        ),
        WorkflowEdge(id='default', source='b', target='end'),
    ]
    router = make_edge_router(edges, {'back'})
    state = {'hitl': {'action': 'revise'}, 'loop_counts': {}}
    assert router(state) == 'back'
    state['loop_counts'] = {'back': 2}
    assert router(state) == 'default'


def test_router_back_edge_default_limit():
    edges = [
        WorkflowEdge(
            id='back',
            source='b',
            target='a',
            condition=EdgeCondition(left='hitl.action', op='eq', value='revise'),
            max_iterations=DEFAULT_MAX_ITERATIONS,
        ),
        WorkflowEdge(id='default', source='b', target='end'),
    ]
    router = make_edge_router(edges, {'back'})
    state = {'hitl': {'action': 'revise'}, 'loop_counts': {'back': DEFAULT_MAX_ITERATIONS}}
    assert router(state) == 'default'


def test_router_raises_without_default():
    edges = [
        WorkflowEdge(
            id='cond',
            source='a',
            target='b',
            condition=EdgeCondition(left='hitl.action', op='eq', value='x'),
        ),
    ]
    router = make_edge_router(edges, set())
    with pytest.raises(ValueError):
        router({'hitl': {'action': 'y'}})


def test_counter_node_increments_loop_count():
    import asyncio

    counter = make_counter_node('e_loop')
    result = asyncio.run(counter({'loop_counts': {}}))
    assert result['loop_counts'] == {'e_loop': 1}
    result = asyncio.run(counter({'loop_counts': {'e_loop': 2}}))
    assert result['loop_counts'] == {'e_loop': 3}


def test_compile_simple_branch():
    wf = make_workflow(
        [
            make_node('start', 'start', {}),
            make_node('a'),
            make_node('b'),
            make_node('end', 'end', {}),
        ],
        [
            WorkflowEdge(id='e1', source='start', target='a'),
            WorkflowEdge(
                id='e2',
                source='a',
                target='b',
                condition=EdgeCondition(left='hitl.action', op='eq', value='x'),
            ),
            WorkflowEdge(id='e3', source='a', target='end'),
            WorkflowEdge(id='e4', source='b', target='end'),
        ],
    )
    builder = compile_workflow_builder(wf)
    keys = builder_node_keys(builder)
    assert {'start', 'a', 'b', 'end'} <= keys
