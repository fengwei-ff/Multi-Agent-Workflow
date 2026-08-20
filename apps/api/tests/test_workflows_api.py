from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import service
from app.main import app
from app.models import ThreadMeta
from app.service import backfill_missing_snapshots, get_thread_meta
from app.roles import store as roles_store
from app.workflows import store
from app.workflows.seed import BUILTIN_DEV_DELIVERY_ID
from app.workflows.store import ensure_seeded


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(store, '_META_PATH', tmp_path / 'workflows.json')
    monkeypatch.setattr(service, '_META_PATH', tmp_path / 'threads.json')
    monkeypatch.setattr(roles_store, '_META_PATH', tmp_path / 'roles.json')


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_list_workflows_includes_builtin(client: TestClient):
    response = client.get('/workflows')
    assert response.status_code == 200
    workflows = response.json()['workflows']
    assert any(item['id'] == BUILTIN_DEV_DELIVERY_ID for item in workflows)
    builtin = next(item for item in workflows if item['id'] == BUILTIN_DEV_DELIVERY_ID)
    assert builtin['builtin'] is True
    assert 'name' in builtin
    assert 'updated_at' in builtin


def test_builtin_put_403(client: TestClient):
    response = client.put(
        f'/workflows/{BUILTIN_DEV_DELIVERY_ID}',
        json={'name': 'x'},
    )
    assert response.status_code == 403


def test_duplicate_and_edit(client: TestClient):
    dup = client.post(f'/workflows/{BUILTIN_DEV_DELIVERY_ID}/duplicate')
    assert dup.status_code == 200
    copy = dup.json()
    assert copy['builtin'] is False
    assert copy['name'].endswith('(副本)')

    updated = client.put(f'/workflows/{copy["id"]}', json={'name': '可编辑模板'})
    assert updated.status_code == 200
    assert updated.json()['name'] == '可编辑模板'


def test_put_invalid_nodes_422(client: TestClient):
    dup = client.post(f'/workflows/{BUILTIN_DEV_DELIVERY_ID}/duplicate')
    assert dup.status_code == 200
    copy_id = dup.json()['id']

    response = client.put(
        f'/workflows/{copy_id}',
        json={
            'nodes': [
                {
                    'id': 'bad',
                    'type': 'not_a_real_node_type',
                    'position': {'x': 0, 'y': 0},
                    'data': {},
                }
            ],
        },
    )
    assert response.status_code == 422


def test_create_run_stores_snapshot(client: TestClient):
    dup = client.post(f'/workflows/{BUILTIN_DEV_DELIVERY_ID}/duplicate')
    assert dup.status_code == 200
    workflow_id = dup.json()['id']
    original_name = dup.json()['name']

    run = client.post(
        f'/workflows/{workflow_id}/runs',
        json={'user_request': '做一个登录页'},
    )
    assert run.status_code == 200
    thread_id = run.json()['thread_id']

    meta = get_thread_meta(thread_id)
    assert meta is not None
    assert meta.workflow_snapshot is not None
    assert meta.workflow_snapshot['id'] == workflow_id
    assert meta.workflow_snapshot['name'] == original_name

    renamed = client.put(f'/workflows/{workflow_id}', json={'name': '模板已改名'})
    assert renamed.status_code == 200
    assert renamed.json()['name'] == '模板已改名'

    meta_after = get_thread_meta(thread_id)
    assert meta_after is not None
    assert meta_after.workflow_snapshot is not None
    assert meta_after.workflow_snapshot['name'] == original_name
    assert meta_after.workflow_snapshot['name'] != '模板已改名'


def test_backfill_missing_snapshots_idempotent():
    ensure_seeded()
    now = datetime.now(timezone.utc).isoformat()
    legacy = ThreadMeta(
        thread_id='legacy-thread-1',
        title='旧线程',
        workflow_id=BUILTIN_DEV_DELIVERY_ID,
        workflow_name='',
        workflow_snapshot=None,
        created_at=now,
        updated_at=now,
    )
    service._save_meta({legacy.thread_id: legacy})

    first = backfill_missing_snapshots()
    assert first == 1
    meta = get_thread_meta('legacy-thread-1')
    assert meta is not None
    assert meta.workflow_snapshot is not None
    assert meta.workflow_snapshot['id'] == BUILTIN_DEV_DELIVERY_ID
    assert meta.workflow_name

    second = backfill_missing_snapshots()
    assert second == 0
