from __future__ import annotations

import pytest

from app.workflows import store
from app.workflows.seed import BUILTIN_DEV_DELIVERY_ID
from app.workflows.store import (
    delete_workflow,
    duplicate_workflow,
    ensure_seeded,
    list_workflows,
    update_workflow,
)


@pytest.fixture(autouse=True)
def _isolate_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, '_META_PATH', tmp_path / 'workflows.json')


def test_seed_idempotent():
    ensure_seeded()
    ensure_seeded()
    items = list_workflows()
    assert sum(1 for w in items if w.id == BUILTIN_DEV_DELIVERY_ID) == 1
    assert any(w.builtin for w in items if w.id == BUILTIN_DEV_DELIVERY_ID)


def test_cannot_update_builtin():
    ensure_seeded()
    try:
        update_workflow(BUILTIN_DEV_DELIVERY_ID, name='x')
        assert False
    except PermissionError:
        pass


def test_cannot_delete_builtin():
    ensure_seeded()
    try:
        delete_workflow(BUILTIN_DEV_DELIVERY_ID)
        assert False
    except PermissionError:
        pass


def test_duplicate_is_editable():
    ensure_seeded()
    copy = duplicate_workflow(BUILTIN_DEV_DELIVERY_ID)
    assert copy.builtin is False
    assert copy.name.endswith('(副本)')
    updated = update_workflow(copy.id, name='可编辑')
    assert updated.name == '可编辑'
