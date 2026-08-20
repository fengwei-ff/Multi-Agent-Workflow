from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RoleDef(BaseModel):
    id: str
    name: str
    builtin: bool
    system_prompt: str
    output_schema: dict[str, Any] = Field(default_factory=dict)
    max_steps: int | None = None
    created_at: str
    updated_at: str


class CreateRoleBody(BaseModel):
    name: str = Field(min_length=1)
    system_prompt: str = ''
    output_schema: dict[str, Any] = Field(default_factory=dict)
    max_steps: int | None = None


class UpdateRoleBody(BaseModel):
    name: str | None = None
    system_prompt: str | None = None
    output_schema: dict[str, Any] | None = None
    max_steps: int | None = None
