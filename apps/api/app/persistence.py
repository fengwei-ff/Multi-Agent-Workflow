from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar


T = TypeVar('T')


class JsonCollectionStore:
    def __init__(self, database_path: Path, collection: str, legacy_path: Path | None = None):
        self.database_path = database_path
        self.collection = collection
        self.legacy_path = legacy_path

    def load(self) -> dict[str, Any]:
        with self._connect() as connection:
            self._ensure_schema(connection)
            self._migrate_legacy(connection)
            return self._load(connection)

    def replace(self, items: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            self._ensure_schema(connection)
            self._migrate_legacy(connection)
            self._replace(connection, items)
            connection.commit()

    def mutate(self, callback: Callable[[dict[str, Any]], T]) -> T:
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            self._ensure_schema(connection)
            self._migrate_legacy(connection)
            items = self._load(connection)
            result = callback(items)
            self._replace(connection, items)
            connection.commit()
            return result

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.execute('PRAGMA busy_timeout = 30000')
        try:
            connection.execute('PRAGMA journal_mode = WAL')
        except sqlite3.OperationalError as exc:
            if 'locked' not in str(exc).lower():
                connection.close()
                raise
        connection.execute('PRAGMA synchronous = NORMAL')
        return connection

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            '''
            CREATE TABLE IF NOT EXISTS metadata_documents (
                collection TEXT NOT NULL,
                item_key TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (collection, item_key)
            )
            '''
        )

    def _load(self, connection: sqlite3.Connection) -> dict[str, Any]:
        rows = connection.execute(
            'SELECT item_key, payload FROM metadata_documents WHERE collection = ?',
            (self.collection,),
        ).fetchall()
        return {key: json.loads(payload) for key, payload in rows}

    def _replace(self, connection: sqlite3.Connection, items: dict[str, Any]) -> None:
        connection.execute(
            'DELETE FROM metadata_documents WHERE collection = ?',
            (self.collection,),
        )
        connection.executemany(
            'INSERT INTO metadata_documents (collection, item_key, payload) VALUES (?, ?, ?)',
            [
                (
                    self.collection,
                    key,
                    json.dumps(value, ensure_ascii=False, default=str),
                )
                for key, value in items.items()
            ],
        )

    def _migrate_legacy(self, connection: sqlite3.Connection) -> None:
        if self.legacy_path is None or not self.legacy_path.exists():
            return
        count = connection.execute(
            'SELECT COUNT(*) FROM metadata_documents WHERE collection = ?',
            (self.collection,),
        ).fetchone()[0]
        if count:
            return

        try:
            raw = json.loads(self.legacy_path.read_text(encoding='utf-8'))
        except Exception:
            return
        if isinstance(raw, list):
            items = {
                str(item.get('id') or item.get('thread_id')): item
                for item in raw
                if isinstance(item, dict) and (item.get('id') or item.get('thread_id'))
            }
        elif isinstance(raw, dict):
            items = raw
        else:
            return
        self._replace(connection, items)


def database_path_for(meta_path: Path) -> Path:
    if meta_path.suffix == '.json':
        return meta_path.with_suffix('.db')
    return meta_path
