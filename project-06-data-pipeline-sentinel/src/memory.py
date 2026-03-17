"""
memory.py
~~~~~~~~~
Episodic memory management for the sentinel agent.
Uses LangGraph Store with namespace isolation per data source.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.store.base import BaseStore

logger = logging.getLogger(__name__)


class SentinelMemory:
    """
    Episodic memory for the data pipeline sentinel.

    Memories are organized in namespace trees:
    ("sentinel", "source_name") → isolation per data source

    This means recall is scoped — searching orders_topic memories
    won't return results from payments_topic.
    """

    def __init__(self, store: BaseStore) -> None:
        self._store = store

    async def store_event(
        self,
        source: str,
        event_type: str,
        severity: str,
        changes: list[dict],
        resolution: str,
        summary: str,
        outcome: str = "pending",
    ) -> None:
        """Record a drift event in episodic memory."""
        namespace = ("sentinel", source)
        key = f"event_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        memory = {
            "source": source,
            "event_type": event_type,
            "severity": severity,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "changes": changes,
            "resolution": resolution,
            "summary": summary,
            "outcome": outcome,
        }

        self._store.put(namespace, key=key, value=memory)
        logger.info("Stored %s event in episodic memory: %s/%s", severity, namespace, key)

    async def update_outcome(self, source: str, event_key: str, outcome: str) -> None:
        """Update the outcome of a stored event (e.g., 'downstream unaffected' after resolution)."""
        namespace = ("sentinel", source)
        items = self._store.search(namespace, query=event_key, limit=1)
        if items:
            item = items[0]
            updated_value = {**item.value, "outcome": outcome}
            self._store.put(namespace, key=item.key, value=updated_value)

    async def recall_similar(
        self,
        source: str,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search over past events for this data source."""
        namespace = ("sentinel", source)
        memories = self._store.search(namespace, query=query, limit=limit)
        return [m.value for m in memories]

    async def get_source_history(self, source: str, limit: int = 20) -> list[dict]:
        """Get chronological history for a data source."""
        namespace = ("sentinel", source)
        all_items = self._store.search(namespace, query="", limit=limit)
        history = [item.value for item in all_items]
        # Sort by timestamp descending
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return history

    async def get_drift_frequency(self, source: str) -> dict[str, int]:
        """Count how often each drift type occurs for a source."""
        history = await self.get_source_history(source, limit=100)
        counts: dict[str, int] = {}
        for event in history:
            event_type = event.get("event_type", "unknown")
            counts[event_type] = counts.get(event_type, 0) + 1
        return counts
