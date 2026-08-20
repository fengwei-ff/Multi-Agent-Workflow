from __future__ import annotations

import logging

logger = logging.getLogger('workflow_agent.graph')


async def shutdown_graph() -> None:
    from app.graph.runtime import shutdown_runtime

    await shutdown_runtime()
