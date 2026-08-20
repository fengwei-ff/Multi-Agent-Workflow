from __future__ import annotations

import pytest

from app.workflows.conditions import eval_condition, resolve_path, validate_condition_path


STATE = {
    'user_request': '做一个待办应用',
    'phase': 'running',
    'node_outputs': {
        'cr': {'verdict': 'reject', 'issues': [{'file': 'a.py'}]},
        'pm': {'summary': '包含 API 设计'},
    },
    'hitl': {'node_id': 'hitl_1', 'action': 'approve', 'message': '可以'},
    'loop_counts': {'e1': 3},
}


def test_resolve_path_nested():
    assert resolve_path(STATE, 'node_outputs.cr.verdict') == 'reject'
    assert resolve_path(STATE, 'node_outputs.missing.verdict') is None
    assert resolve_path(STATE, 'hitl.action') == 'approve'


def test_eq_neq():
    assert eval_condition({'left': 'hitl.action', 'op': 'eq', 'value': 'approve'}, STATE)
    assert not eval_condition({'left': 'node_outputs.cr.verdict', 'op': 'neq', 'value': 'reject'}, STATE)


def test_in_contains_exists():
    assert eval_condition({'left': 'hitl.action', 'op': 'in', 'value': ['approve', 'ok']}, STATE)
    assert eval_condition({'left': 'node_outputs.pm.summary', 'op': 'contains', 'value': 'API'}, STATE)
    assert eval_condition({'left': 'node_outputs.cr.issues', 'op': 'exists'}, STATE)
    assert not eval_condition({'left': 'node_outputs.nope', 'op': 'exists'}, STATE)


def test_gt_lt():
    assert eval_condition({'left': 'loop_counts.e1', 'op': 'gt', 'value': 2}, STATE)
    assert not eval_condition({'left': 'loop_counts.e1', 'op': 'lt', 'value': 2}, STATE)
    # 缺失值不参与比较，返回 False 而非抛错
    assert not eval_condition({'left': 'loop_counts.missing', 'op': 'gt', 'value': 0}, STATE)


def test_path_whitelist():
    assert validate_condition_path('node_outputs.cr.verdict') is None
    assert validate_condition_path('hitl.action') is None
    assert validate_condition_path('__import__("os")') is not None
    assert validate_condition_path('messages') is not None


def test_eval_rejects_bad_path_and_op():
    with pytest.raises(ValueError):
        eval_condition({'left': 'messages', 'op': 'eq', 'value': 1}, STATE)
    with pytest.raises(ValueError):
        eval_condition({'left': 'phase', 'op': 'regex', 'value': 'run'}, STATE)
