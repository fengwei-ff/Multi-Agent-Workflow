from __future__ import annotations

import copy
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from app.persistence import JsonCollectionStore, database_path_for
from app.roles.schema import RoleDef
from app.roles.seed import BUILTIN_ROLES

logger = logging.getLogger('workflow_agent.roles.store')

_DATA_DIR = Path(__file__).resolve().parents[2] / '.data'
_DEFAULT_META_PATH = _DATA_DIR / 'metadata.db'
_LEGACY_META_PATH = _DATA_DIR / 'roles.json'
_META_PATH = _DEFAULT_META_PATH
T = TypeVar('T')


def set_meta_path(path: Path) -> None:
    global _META_PATH
    _META_PATH = path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_meta() -> dict[str, RoleDef]:
    return _parse_meta(_store().load())


def _save_meta(meta: dict[str, RoleDef]) -> None:
    _store().replace({key: value.model_dump() for key, value in meta.items()})


def _store() -> JsonCollectionStore:
    legacy_path = _LEGACY_META_PATH if _META_PATH == _DEFAULT_META_PATH else _META_PATH
    return JsonCollectionStore(database_path_for(_META_PATH), 'roles', legacy_path)


def _parse_meta(raw: dict[str, object]) -> dict[str, RoleDef]:
    items: dict[str, RoleDef] = {}
    for entry in raw.values():
        try:
            item = RoleDef.model_validate(entry)
        except Exception:
            logger.warning('Skipping invalid role entry: %s', str(entry)[:120])
            continue
        items[item.id] = item
    return items


def _mutate_meta(callback: Callable[[dict[str, RoleDef]], T]) -> T:
    def mutate(raw: dict[str, object]) -> T:
        meta = _parse_meta(raw)
        result = callback(meta)
        raw.clear()
        raw.update({key: value.model_dump() for key, value in meta.items()})
        return result

    return _store().mutate(mutate)


def ensure_seeded() -> None:
    """Always refresh builtin roles from code (read-only, owned by seed)."""
    def seed(meta: dict[str, RoleDef]) -> None:
        for role in BUILTIN_ROLES:
            meta[role.id] = role.model_copy(deep=True)

    _mutate_meta(seed)


def list_roles() -> list[RoleDef]:
    meta = _load_meta()
    return sorted(meta.values(), key=lambda item: (not item.builtin, item.updated_at), reverse=False)


def get_role(role_id: str) -> RoleDef | None:
    return _load_meta().get(role_id)


def create_role(
    name: str,
    system_prompt: str = '',
    output_schema: dict | None = None,
    max_steps: int | None = None,
) -> RoleDef:
    now = _now()
    role_id = str(uuid.uuid4())
    item = RoleDef(
        id=role_id,
        name=name,
        builtin=False,
        system_prompt=system_prompt,
        output_schema=output_schema or {},
        max_steps=max_steps,
        created_at=now,
        updated_at=now,
    )
    _mutate_meta(lambda meta: meta.__setitem__(role_id, item))
    return item


def update_role(role_id: str, **fields) -> RoleDef:
    def update(meta: dict[str, RoleDef]) -> RoleDef:
        item = meta.get(role_id)
        if item is None:
            raise KeyError(role_id)
        if item.builtin:
            raise PermissionError(f'Builtin role cannot be updated: {role_id}')

        data = item.model_dump()
        for key in ('name', 'system_prompt', 'output_schema', 'max_steps'):
            if key in fields and fields[key] is not None:
                data[key] = fields[key]
        data['updated_at'] = _now()
        updated = RoleDef.model_validate(data)
        meta[role_id] = updated
        return updated

    return _mutate_meta(update)


def delete_role(role_id: str) -> None:
    def delete(meta: dict[str, RoleDef]) -> None:
        item = meta.get(role_id)
        if item is None:
            raise KeyError(role_id)
        if item.builtin:
            raise PermissionError(f'Builtin role cannot be deleted: {role_id}')
        del meta[role_id]

    _mutate_meta(delete)


def duplicate_role(role_id: str) -> RoleDef:
    def duplicate(meta: dict[str, RoleDef]) -> RoleDef:
        item = meta.get(role_id)
        if item is None:
            raise KeyError(role_id)

        now = _now()
        new_id = str(uuid.uuid4())
        copy_item = RoleDef(
            id=new_id,
            name=f'{item.name} (副本)',
            builtin=False,
            system_prompt=item.system_prompt,
            output_schema=copy.deepcopy(item.output_schema),
            max_steps=item.max_steps,
            created_at=now,
            updated_at=now,
        )
        meta[new_id] = copy_item
        return copy_item

    return _mutate_meta(duplicate)
