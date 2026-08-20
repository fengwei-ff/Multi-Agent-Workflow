from __future__ import annotations

import copy
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

from app.persistence import JsonCollectionStore, database_path_for
from app.workflows.schema import (
    WorkflowDef,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodePosition,
    WorkflowViewport,
)
from app.workflows.seed import BUILTIN_DEV_DELIVERY_ID, DEV_DELIVERY_WORKFLOW
from app.workflows.validate import validate_workflow

logger = logging.getLogger('workflow_agent.workflows.store')

_DATA_DIR = Path(__file__).resolve().parents[2] / '.data'
_DEFAULT_META_PATH = _DATA_DIR / 'metadata.db'
_LEGACY_META_PATH = _DATA_DIR / 'workflows.json'
_META_PATH = _DEFAULT_META_PATH
T = TypeVar('T')


def set_meta_path(path: Path) -> None:
    global _META_PATH
    _META_PATH = path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_meta() -> dict[str, WorkflowDef]:
    return _parse_meta(_store().load())


def _parse_meta(raw: dict[str, object]) -> dict[str, WorkflowDef]:
    items: dict[str, WorkflowDef] = {}
    for entry in raw.values():
        try:
            item = WorkflowDef.model_validate(entry)
        except Exception:
            logger.warning('Skipping legacy/invalid workflow entry: %s', str(entry)[:120])
            continue
        items[item.id] = item
    return items


def _save_meta(meta: dict[str, WorkflowDef]) -> None:
    _store().replace({key: value.model_dump() for key, value in meta.items()})


def _store() -> JsonCollectionStore:
    legacy_path = _LEGACY_META_PATH if _META_PATH == _DEFAULT_META_PATH else _META_PATH
    return JsonCollectionStore(database_path_for(_META_PATH), 'workflows', legacy_path)


def _mutate_meta(callback: Callable[[dict[str, WorkflowDef]], T]) -> T:
    def mutate(raw: dict[str, object]) -> T:
        meta = _parse_meta(raw)
        result = callback(meta)
        raw.clear()
        raw.update({key: value.model_dump() for key, value in meta.items()})
        return result

    return _store().mutate(mutate)


def ensure_seeded() -> None:
    """Always refresh builtin from code (read-only template owned by seed)."""
    _mutate_meta(
        lambda meta: meta.__setitem__(
            BUILTIN_DEV_DELIVERY_ID,
            DEV_DELIVERY_WORKFLOW.model_copy(deep=True),
        )
    )


def list_workflows() -> list[WorkflowDef]:
    meta = _load_meta()
    return sorted(meta.values(), key=lambda item: item.updated_at, reverse=True)


def get_workflow(workflow_id: str) -> WorkflowDef | None:
    return _load_meta().get(workflow_id)


def _default_start_end_nodes() -> list[WorkflowNode]:
    return [
        WorkflowNode(id='start', type='start', position=WorkflowNodePosition(x=0, y=160), data={}),
        WorkflowNode(id='end', type='end', position=WorkflowNodePosition(x=180, y=160), data={}),
    ]


def create_workflow(
    name: str,
    description: str | None = None,
    nodes: list[WorkflowNode] | None = None,
    edges: list[WorkflowEdge] | None = None,
) -> WorkflowDef:
    now = _now()
    workflow_id = str(uuid.uuid4())
    item = WorkflowDef(
        id=workflow_id,
        name=name,
        description=description,
        builtin=False,
        created_at=now,
        updated_at=now,
        nodes=nodes if nodes is not None else _default_start_end_nodes(),
        edges=edges if edges is not None else [],
    )
    _mutate_meta(lambda meta: meta.__setitem__(workflow_id, item))
    return item


def update_workflow(workflow_id: str, **fields: Any) -> WorkflowDef:
    def update(meta: dict[str, WorkflowDef]) -> WorkflowDef:
        item = meta.get(workflow_id)
        if item is None:
            raise KeyError(workflow_id)
        if item.builtin:
            raise PermissionError(f'Builtin workflow cannot be updated: {workflow_id}')

        data = item.model_dump()
        if 'name' in fields and fields['name'] is not None:
            data['name'] = fields['name']
        if 'description' in fields:
            data['description'] = fields['description']
        if 'nodes' in fields and fields['nodes'] is not None:
            data['nodes'] = fields['nodes']
        if 'edges' in fields and fields['edges'] is not None:
            data['edges'] = fields['edges']
        if 'viewport' in fields:
            viewport = fields['viewport']
            if isinstance(viewport, dict):
                data['viewport'] = WorkflowViewport.model_validate(viewport).model_dump()
            elif viewport is None:
                data['viewport'] = None
            else:
                data['viewport'] = viewport.model_dump() if hasattr(viewport, 'model_dump') else viewport

        data['updated_at'] = _now()
        updated = WorkflowDef.model_validate(data)
        if 'nodes' in fields or 'edges' in fields:
            errors = validate_workflow(updated)
            if errors:
                raise ValueError(errors)
        meta[workflow_id] = updated
        return updated

    return _mutate_meta(update)


def delete_workflow(workflow_id: str) -> None:
    def delete(meta: dict[str, WorkflowDef]) -> None:
        item = meta.get(workflow_id)
        if item is None:
            raise KeyError(workflow_id)
        if item.builtin:
            raise PermissionError(f'Builtin workflow cannot be deleted: {workflow_id}')
        del meta[workflow_id]

    _mutate_meta(delete)


def duplicate_workflow(workflow_id: str) -> WorkflowDef:
    def duplicate(meta: dict[str, WorkflowDef]) -> WorkflowDef:
        item = meta.get(workflow_id)
        if item is None:
            raise KeyError(workflow_id)

        now = _now()
        new_id = str(uuid.uuid4())
        copy_item = WorkflowDef(
            id=new_id,
            name=f'{item.name} (副本)',
            description=item.description,
            builtin=False,
            created_at=now,
            updated_at=now,
            nodes=copy.deepcopy(item.nodes),
            edges=copy.deepcopy(item.edges),
            viewport=copy.deepcopy(item.viewport) if item.viewport is not None else None,
        )
        meta[new_id] = copy_item
        return copy_item

    return _mutate_meta(duplicate)
