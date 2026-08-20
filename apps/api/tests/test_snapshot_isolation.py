"""Snapshot isolation: editing a template must not mutate existing run snapshots."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import service
from app.main import app
from app.service import get_thread_meta
from app.roles import store as roles_store
from app.workflows import store
from app.workflows.seed import BUILTIN_DEV_DELIVERY_ID


@pytest.fixture(autouse=True)
def _isolate_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(store, '_META_PATH', tmp_path / 'workflows.json')
    monkeypatch.setattr(service, '_META_PATH', tmp_path / 'threads.json')
    monkeypatch.setattr(roles_store, '_META_PATH', tmp_path / 'roles.json')


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_edit_template_does_not_change_snapshot(client: TestClient):
    dup = client.post(f'/workflows/{BUILTIN_DEV_DELIVERY_ID}/duplicate')
    assert dup.status_code == 200
    workflow_id = dup.json()['id']
    original_name = dup.json()['name']
    original_nodes = dup.json()['nodes']

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
    assert meta.workflow_snapshot['nodes'] == original_nodes

    renamed = client.put(
        f'/workflows/{workflow_id}',
        json={
            'name': '模板已改名',
            'nodes': [
                {
                    'id': 'only_start',
                    'type': 'start',
                    'position': {'x': 0, 'y': 0},
                    'data': {},
                },
                {
                    'id': 'only_end',
                    'type': 'end',
                    'position': {'x': 200, 'y': 0},
                    'data': {},
                },
            ],
            'edges': [
                {
                    'id': 'e1',
                    'source': 'only_start',
                    'target': 'only_end',
                },
            ],
        },
    )
    assert renamed.status_code == 200
    assert renamed.json()['name'] == '模板已改名'

    meta_after = get_thread_meta(thread_id)
    assert meta_after is not None
    assert meta_after.workflow_snapshot is not None
    assert meta_after.workflow_snapshot['name'] == original_name
    assert meta_after.workflow_snapshot['name'] != '模板已改名'
    assert meta_after.workflow_snapshot['nodes'] == original_nodes

    state = client.get(f'/threads/{thread_id}')
    assert state.status_code == 200
    body = state.json()
    assert body['workflow_id'] == workflow_id
    assert body['workflow_name'] == original_name
    assert isinstance(body.get('workflow_nodes'), list)
    assert len(body['workflow_nodes']) == len(original_nodes)
    assert {n['id'] for n in body['workflow_nodes']} == {n['id'] for n in original_nodes}
