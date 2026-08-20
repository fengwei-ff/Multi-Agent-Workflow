from __future__ import annotations

from typing import Any

# 条件表达式 left 路径的允许根（白名单，禁止 eval 任意代码）
ALLOWED_PATH_ROOTS: frozenset[str] = frozenset({
    'node_outputs',
    'hitl',
    'loop_counts',
    'user_request',
    'phase',
})

_OPS = ('eq', 'neq', 'in', 'contains', 'gt', 'lt', 'exists')


def resolve_path(state: dict[str, Any], path: str) -> Any:
    """Resolve a dot path like 'node_outputs.cr_1.verdict' against state. Missing → None."""
    if not path:
        return None
    current: Any = state
    for part in path.split('.'):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def validate_condition_path(path: str) -> str | None:
    """Return an error message if the path root is not whitelisted, else None."""
    root = path.split('.')[0] if path else ''
    if root not in ALLOWED_PATH_ROOTS:
        return f'条件路径根不在白名单内: {path} (允许: {sorted(ALLOWED_PATH_ROOTS)})'
    return None


def eval_condition(condition: dict[str, Any], state: dict[str, Any]) -> bool:
    """Evaluate a structured EdgeCondition {left, op, value?} against state."""
    left_path = str(condition.get('left') or '')
    op = str(condition.get('op') or '')
    if op not in _OPS:
        raise ValueError(f'不支持的条件操作符: {op}')
    err = validate_condition_path(left_path)
    if err:
        raise ValueError(err)

    actual = resolve_path(state, left_path)
    expected = condition.get('value')

    if op == 'exists':
        return actual is not None
    if op == 'eq':
        return actual == expected
    if op == 'neq':
        return actual != expected
    if op == 'in':
        if not isinstance(expected, (list, tuple, set)):
            raise ValueError('in 操作的 value 必须是数组')
        return actual in expected
    if op == 'contains':
        if actual is None:
            return False
        if isinstance(actual, (list, tuple, set, str, dict)):
            return expected in actual
        return False
    if op in ('gt', 'lt'):
        if actual is None or expected is None:
            return False
        try:
            return actual > expected if op == 'gt' else actual < expected
        except TypeError:
            return False
    return False
