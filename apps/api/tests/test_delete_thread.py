from __future__ import annotations

from fastapi.testclient import TestClient

from app import service
from app.main import app
from app.roles import store as roles_store
from app.workflows import store


def test_delete_thread_removes_meta_and_breaks_detail(tmp_path, monkeypatch):
    monkeypatch.setattr(store, '_META_PATH', tmp_path / 'workflows.json')
    monkeypatch.setattr(service, '_META_PATH', tmp_path / 'threads.json')
    monkeypatch.setattr(roles_store, '_META_PATH', tmp_path / 'roles.json')

    with TestClient(app) as client:
        created = client.post(
            '/threads',
            json={'user_request': '删除这个实例', 'workflow_id': 'dev_delivery'},
        )
        assert created.status_code == 200
        thread_id = created.json()['thread_id']

        listed_before = client.get('/threads')
        assert listed_before.status_code == 200
        assert any(item['thread_id'] == thread_id for item in listed_before.json()['threads'])

        removed = client.delete(f'/threads/{thread_id}')
        assert removed.status_code == 200
        assert removed.json()['status'] == 'deleted'

        listed_after = client.get('/threads')
        assert listed_after.status_code == 200
        assert all(item['thread_id'] != thread_id for item in listed_after.json()['threads'])

        detail = client.get(f'/threads/{thread_id}')
        assert detail.status_code == 404
