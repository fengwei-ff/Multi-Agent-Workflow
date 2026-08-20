from __future__ import annotations

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
        if node_type == 'agent':
            data = {'role_id': 'backend_dev', 'task_template': '{user_request}'}
        elif node_type == 'hitl':
            data = {'title': '审批', 'options': ['approve', 'revise'], 'summary_fields': []}
        else:
            data = {}
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


def linear_workflow() -> WorkflowDef:
    """start -> a -> end，最小合法流程。"""
    return make_workflow(
        [make_node('start', 'start'), make_node('a'), make_node('end', 'end')],
        [
            WorkflowEdge(id='e1', source='start', target='a'),
            WorkflowEdge(id='e2', source='a', target='end'),
        ],
    )


def codes_of(workflow: WorkflowDef) -> set[str]:
    return {err['code'] for err in validate_workflow(workflow)}


def test_builtin_seed_valid():
    assert validate_workflow(DEV_DELIVERY_WORKFLOW) == []


def test_builtin_back_edges_detected():
    back = find_back_edges(DEV_DELIVERY_WORKFLOW)
    assert {'e_hitl_revise', 'e_cr_reject', 'e_qa_fail'} <= back
    assert 'e_start_pm' not in back


def test_linear_workflow_valid():
    assert validate_workflow(linear_workflow()) == []


def test_start_and_end_count():
    wf = make_workflow([make_node('a')], [])
    codes = codes_of(wf)
    assert 'start_count' in codes
    assert 'end_count' in codes


def test_duplicate_node_and_edge_ids():
    wf = make_workflow(
        [
            make_node('start', 'start'),
            make_node('a'),
            make_node('a'),
            make_node('end', 'end'),
        ],
        [
            WorkflowEdge(id='e1', source='start', target='a'),
            WorkflowEdge(id='e1', source='a', target='end'),
        ],
    )
    codes = codes_of(wf)
    assert 'duplicate_node_id' in codes
    assert 'duplicate_edge_id' in codes


def test_missing_edge_endpoints():
    wf = make_workflow(
        [make_node('start', 'start'), make_node('end', 'end')],
        [WorkflowEdge(id='e1', source='start', target='ghost')],
    )
    codes = codes_of(wf)
    assert 'missing_target' in codes


def test_condition_path_whitelist():
    wf = make_workflow(
        [make_node('start', 'start'), make_node('a'), make_node('end', 'end')],
        [
            WorkflowEdge(id='e1', source='start', target='a'),
            WorkflowEdge(
                id='e2',
                source='a',
                target='end',
                condition=EdgeCondition(left='evil.path', op='eq', value=1),
            ),
        ],
    )
    assert 'condition_path' in codes_of(wf)


def test_condition_node_ref_must_exist():
    wf = make_workflow(
        [make_node('start', 'start'), make_node('a'), make_node('end', 'end')],
        [
            WorkflowEdge(id='e1', source='start', target='a'),
            WorkflowEdge(
                id='e2',
                source='a',
                target='end',
                condition=EdgeCondition(left='node_outputs.ghost.verdict', op='eq', value='pass'),
            ),
        ],
    )
    assert 'condition_node_ref' in codes_of(wf)


def test_unreachable_node():
    wf = make_workflow(
        [
            make_node('start', 'start'),
            make_node('a'),
            make_node('orphan'),
            make_node('end', 'end'),
        ],
        [
            WorkflowEdge(id='e1', source='start', target='a'),
            WorkflowEdge(id='e2', source='a', target='end'),
        ],
    )
    assert 'unreachable_node' in codes_of(wf)


def test_no_outgoing():
    wf = make_workflow(
        [make_node('start', 'start'), make_node('a'), make_node('end', 'end')],
        [WorkflowEdge(id='e1', source='start', target='a')],
    )
    assert 'no_outgoing' in codes_of(wf)


def test_multiple_outs_require_exactly_one_default():
    # 两条条件边、无 default → 报错
    wf = make_workflow(
        [make_node('start', 'start'), make_node('a'), make_node('b'), make_node('end', 'end')],
        [
            WorkflowEdge(id='e1', source='start', target='a'),
            WorkflowEdge(
                id='e2',
                source='a',
                target='b',
                condition=EdgeCondition(left='hitl.action', op='eq', value='x'),
            ),
            WorkflowEdge(
                id='e3',
                source='a',
                target='end',
                condition=EdgeCondition(left='hitl.action', op='eq', value='y'),
            ),
            WorkflowEdge(id='e4', source='b', target='end'),
        ],
    )
    assert 'default_edge_count' in codes_of(wf)


def test_branch_with_default_valid():
    wf = make_workflow(
        [make_node('start', 'start'), make_node('a'), make_node('b'), make_node('end', 'end')],
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
    assert validate_workflow(wf) == []


def test_back_edge_requires_max_iterations():
    # a -> b -> a 回头边无 max_iterations
    wf = make_workflow(
        [make_node('start', 'start'), make_node('a'), make_node('b'), make_node('end', 'end')],
        [
            WorkflowEdge(id='e1', source='start', target='a'),
            WorkflowEdge(id='e2', source='a', target='b'),
            WorkflowEdge(
                id='e3',
                source='b',
                target='a',
                condition=EdgeCondition(left='hitl.action', op='eq', value='revise'),
            ),
            WorkflowEdge(id='e4', source='b', target='end'),
        ],
    )
    assert 'back_edge_no_limit' in codes_of(wf)


def test_default_edge_cannot_be_back_edge():
    # b -> a 无条件回头边（循环无法退出）
    wf = make_workflow(
        [make_node('start', 'start'), make_node('a'), make_node('b'), make_node('end', 'end')],
        [
            WorkflowEdge(id='e1', source='start', target='a'),
            WorkflowEdge(id='e2', source='a', target='b'),
            WorkflowEdge(id='e3', source='b', target='a', max_iterations=3),
            WorkflowEdge(id='e4', source='b', target='end'),
        ],
    )
    assert 'default_is_back_edge' in codes_of(wf)


def test_agent_requires_role():
    wf = make_workflow(
        [
            make_node('start', 'start'),
            make_node('a', 'agent', {'task_template': 'x'}),
            make_node('end', 'end'),
        ],
        [
            WorkflowEdge(id='e1', source='start', target='a'),
            WorkflowEdge(id='e2', source='a', target='end'),
        ],
    )
    assert 'agent_missing_role' in codes_of(wf)


def test_hitl_requires_options():
    wf = make_workflow(
        [
            make_node('start', 'start'),
            make_node('h', 'hitl', {'title': '审批', 'options': []}),
            make_node('end', 'end'),
        ],
        [
            WorkflowEdge(id='e1', source='start', target='h'),
            WorkflowEdge(id='e2', source='h', target='end'),
        ],
    )
    assert 'hitl_missing_options' in codes_of(wf)
