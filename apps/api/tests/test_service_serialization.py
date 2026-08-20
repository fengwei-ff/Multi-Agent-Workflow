from __future__ import annotations

from app.service import _serialize_update


class CustomValue:
    def __str__(self) -> str:
        return 'custom-value'


def test_serialize_update_handles_nested_non_json_values():
    result = _serialize_update({
        'node_outputs': {
            'backend': {
                'details': CustomValue(),
                'items': [CustomValue()],
            },
        },
    })

    assert result['node_outputs']['backend']['details'] == 'custom-value'
    assert result['node_outputs']['backend']['items'] == ['custom-value']
