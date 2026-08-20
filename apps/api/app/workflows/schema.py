from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

NodeType = Literal['start', 'end', 'agent', 'hitl']

ConditionOp = Literal['eq', 'neq', 'in', 'contains', 'gt', 'lt', 'exists']


class EdgeCondition(BaseModel):
    left: str  # 状态字段点路径，如 'node_outputs.cr_1.verdict' / 'hitl.action'
    op: ConditionOp
    value: Any = None


class AgentNodeData(BaseModel):
    role_id: str = ''
    task_template: str = ''
    max_steps: int | None = None


class HitlNodeData(BaseModel):
    title: str = '人工审批'
    options: list[str] = Field(default_factory=lambda: ['approve', 'reject'])
    summary_fields: list[str] = Field(default_factory=list)


class WorkflowNodePosition(BaseModel):
    x: float
    y: float


class WorkflowNode(BaseModel):
    id: str
    type: NodeType
    position: WorkflowNodePosition
    data: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    id: str
    source: str
    target: str
    condition: EdgeCondition | None = None  # 无条件 = default 兜底边
    max_iterations: int | None = None       # 回头边专用，默认 5
    label: str | None = None


class WorkflowViewport(BaseModel):
    x: float
    y: float
    zoom: float


class WorkflowDef(BaseModel):
    id: str
    name: str
    description: str | None = None
    builtin: bool
    created_at: str
    updated_at: str
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    viewport: WorkflowViewport | None = None
