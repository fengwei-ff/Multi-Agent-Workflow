from __future__ import annotations

from app.workflows.schema import (
    EdgeCondition,
    WorkflowDef,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodePosition,
)

BUILTIN_DEV_DELIVERY_ID = 'dev_delivery'

_TS = '2026-08-06T00:00:00+00:00'


def _node(node_id: str, ntype: str, x: float, y: float, data: dict | None = None) -> WorkflowNode:
    return WorkflowNode(
        id=node_id,
        type=ntype,  # type: ignore[arg-type]
        position=WorkflowNodePosition(x=x, y=y),
        data=data or {},
    )


DEV_DELIVERY_WORKFLOW = WorkflowDef(
    id=BUILTIN_DEV_DELIVERY_ID,
    name='研发交付流',
    description='产品 → 需求确认 → 后端 → 前端 → CR → 测试 的角色化多 agent 交付流程',
    builtin=True,
    created_at=_TS,
    updated_at=_TS,
    nodes=[
        _node('start', 'start', 0, 200),
        _node('pm', 'agent', 200, 200, {
            'role_id': 'product_manager',
            'task_template': (
                '用户需求：{user_request}\n\n'
                '人工反馈（如有，请据此修订 PRD）：{hitl.message}\n\n'
                '请完成 PRD 并提交产物。'
            ),
        }),
        _node('hitl_req', 'hitl', 420, 200, {
            'title': '需求确认',
            'options': ['approve', 'revise'],
            'summary_fields': ['node_outputs.pm.summary', 'node_outputs.pm.acceptance_items'],
        }),
        _node('backend', 'agent', 640, 120, {
            'role_id': 'backend_dev',
            'task_template': (
                '请根据 docs/prd.md 实现后端 API 并写 docs/api.md。\n'
                'PRD 摘要：{node_outputs.pm.summary}\n'
                '打回意见（如有）：{node_outputs.cr.summary}{node_outputs.qa.summary}'
            ),
        }),
        _node('frontend', 'agent', 860, 120, {
            'role_id': 'frontend_dev',
            'task_template': '请根据 docs/prd.md 与 docs/api.md 实现前端页面。',
        }),
        _node('cr', 'agent', 1080, 200, {
            'role_id': 'code_reviewer',
            'task_template': '请对照 docs/prd.md 与 docs/api.md 评审 src/ 下全部代码。',
        }),
        _node('qa', 'agent', 1300, 200, {
            'role_id': 'qa_tester',
            'task_template': (
                '请根据 docs/prd.md 拆分测试 checklist 写入 docs/checklist.md，'
                '并逐条真实验证（含接口测试）。'
            ),
        }),
        _node('end', 'end', 1520, 200),
    ],
    edges=[
        WorkflowEdge(id='e_start_pm', source='start', target='pm'),
        WorkflowEdge(id='e_pm_hitl', source='pm', target='hitl_req'),
        WorkflowEdge(
            id='e_hitl_revise',
            source='hitl_req',
            target='pm',
            condition=EdgeCondition(left='hitl.action', op='eq', value='revise'),
            max_iterations=5,
            label='打回修订',
        ),
        WorkflowEdge(id='e_hitl_backend', source='hitl_req', target='backend', label='通过'),
        WorkflowEdge(id='e_backend_frontend', source='backend', target='frontend'),
        WorkflowEdge(id='e_frontend_cr', source='frontend', target='cr'),
        WorkflowEdge(
            id='e_cr_reject',
            source='cr',
            target='backend',
            condition=EdgeCondition(left='node_outputs.cr.verdict', op='eq', value='reject'),
            max_iterations=3,
            label='打回修改',
        ),
        WorkflowEdge(id='e_cr_qa', source='cr', target='qa', label='通过'),
        WorkflowEdge(
            id='e_qa_fail',
            source='qa',
            target='backend',
            condition=EdgeCondition(left='node_outputs.qa.verdict', op='eq', value='fail'),
            max_iterations=3,
            label='回退修复',
        ),
        WorkflowEdge(id='e_qa_end', source='qa', target='end', label='通过'),
    ],
)
