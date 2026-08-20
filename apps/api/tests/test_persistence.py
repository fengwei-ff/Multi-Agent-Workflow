from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from app.persistence import JsonCollectionStore


def test_json_collection_store_migrates_legacy_json(tmp_path):
    legacy_path = tmp_path / 'workflows.json'
    database_path = tmp_path / 'workflows.db'
    legacy_path.write_text(
        json.dumps({'one': {'id': 'one', 'name': 'legacy'}}),
        encoding='utf-8',
    )

    store = JsonCollectionStore(database_path, 'workflows', legacy_path)

    assert store.load() == {'one': {'id': 'one', 'name': 'legacy'}}
    assert database_path.exists()


def test_json_collection_store_serializes_concurrent_updates(tmp_path):
    store = JsonCollectionStore(tmp_path / 'metadata.db', 'threads')

    def add_item(index: int) -> None:
        def mutate(items: dict[str, object]) -> None:
            items[str(index)] = {'thread_id': str(index)}

        store.mutate(mutate)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(add_item, range(40)))

    assert len(store.load()) == 40
