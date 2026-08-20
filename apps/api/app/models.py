from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from typing_extensions import Annotated, TypedDict
from langgraph.graph.message import add_messages


Phase = Literal['running', 'done', 'failed']


def merge_dicts(left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
    """LangGraph reducer: merge dicts with last-write-wins per key."""
    out = dict(left or {})
    out.update(right or {})
    return out


class ChatMessage(BaseModel):
    role: Literal['user', 'assistant', 'system']
    content: str
    timestamp: str | None = None


class InterruptPayload(BaseModel):
    kind: str = 'approval'
    title: str
    summary: str
    options: list[str]
    payload: dict[str, Any] = Field(default_factory=dict)


class HitlState(BaseModel):
    node_id: str
    action: str
    message: str = ''


class WorkflowState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    user_request: str
    phase: str
    active_node_id: str
    node_outputs: Annotated[dict[str, Any], merge_dicts]
    loop_counts: Annotated[dict[str, int], merge_dicts]
    workflow_id: str
    workspace_dir: str
    hitl: dict[str, Any]
    last_assistant_message: str


class ThreadMeta(BaseModel):
    thread_id: str
    title: str
    workflow_id: str = 'dev_delivery'
    workflow_name: str = '研发交付流'
    workflow_snapshot: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class CreateThreadBody(BaseModel):
    user_request: str = Field(min_length=1)
    workflow_id: str = 'dev_delivery'


class CreateWorkflowBody(BaseModel):
    name: str
    description: str | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None


class UpdateWorkflowBody(BaseModel):
    name: str | None = None
    description: str | None = None
    nodes: list[dict[str, Any]] | None = None
    edges: list[dict[str, Any]] | None = None
    viewport: dict[str, Any] | None = None


class CreateWorkflowRunBody(BaseModel):
    user_request: str = Field(min_length=1)


class UserMessageBody(BaseModel):
    message: str = Field(min_length=1)


class ResumeBody(BaseModel):
    action: str = Field(min_length=1)
    message: str | None = None
    feedback: str | None = None


class ThreadStateResponse(BaseModel):
    thread_id: str
    phase: str = 'running'
    workflow_id: str | None = None
    workflow_name: str | None = None
    workflow_nodes: list[dict[str, Any]] = Field(default_factory=list)
    user_request: str = ''
    active_node_id: str = ''
    node_outputs: dict[str, Any] = Field(default_factory=dict)
    hitl: dict[str, Any] | None = None
    workspace_dir: str = ''
    last_assistant_message: str = ''
    messages: list[ChatMessage] = Field(default_factory=list)
    interrupted: bool = False
    interrupt: InterruptPayload | None = None
    can_retry: bool = False
    pending_nodes: list[str] = Field(default_factory=list)
