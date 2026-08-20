from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings
from app.graph.compiler import compile_workflow_builder
from app.workflows.schema import WorkflowDef

logger = logging.getLogger('workflow_agent.runtime')

_checkpointer: Any = None
_sqlite_cm: Any = None
_graph_cache: OrderedDict[str, Any] = OrderedDict()


def _snapshot_cache_key(snapshot: WorkflowDef) -> str:
    payload = json.dumps(
        snapshot.model_dump(),
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    return f'{snapshot.id}:{digest}'


def _resolve_checkpoint_db_path() -> Path:
    settings = get_settings()
    db_path = Path(settings.checkpoint_db_path)
    if not db_path.is_absolute():
        db_path = Path(__file__).resolve().parents[2] / db_path
    return db_path


async def ensure_checkpointer() -> Any:
    global _checkpointer, _sqlite_cm
    if _checkpointer is not None:
        return _checkpointer

    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        db_path = _resolve_checkpoint_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _sqlite_cm = AsyncSqliteSaver.from_conn_string(str(db_path))
        _checkpointer = await _sqlite_cm.__aenter__()
        logger.info('Using SQLite checkpointer at %s', db_path)
    except Exception:
        settings = get_settings()
        if not settings.checkpoint_allow_memory_fallback:
            logger.exception('SQLite checkpointer unavailable')
            raise
        logger.exception('SQLite checkpointer unavailable; using explicitly enabled MemorySaver fallback')
        _checkpointer = MemorySaver()
        _sqlite_cm = None

    return _checkpointer


async def get_graph_for_snapshot(snapshot: WorkflowDef) -> Any:
    key = _snapshot_cache_key(snapshot)
    cached = _graph_cache.get(key)
    if cached is not None:
        _graph_cache.move_to_end(key)
        return cached

    checkpointer = await ensure_checkpointer()
    builder = compile_workflow_builder(snapshot)
    compiled = builder.compile(checkpointer=checkpointer)
    _graph_cache[key] = compiled
    cache_size = max(1, get_settings().graph_cache_size)
    while len(_graph_cache) > cache_size:
        _graph_cache.popitem(last=False)
    return compiled


async def shutdown_runtime() -> None:
    global _checkpointer, _sqlite_cm, _graph_cache
    if _sqlite_cm is not None:
        try:
            await _sqlite_cm.__aexit__(None, None, None)
        except Exception:
            logger.exception('Failed to close sqlite checkpointer')
    _sqlite_cm = None
    _checkpointer = None
    _graph_cache = OrderedDict()
