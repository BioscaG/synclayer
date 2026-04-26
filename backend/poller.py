"""Periodic background sync for configured team sources.

The poller iterates every configured team's repositories at a fixed interval
and calls ``sync_repo`` on each one. It picks up new commits / PRs without
requiring anyone to click "Sync sources" — the demo feels live: push a commit,
wait one tick, and new entities show up in memory.

Design choices:

* **Repos only.** Slack and tickets are still synced manually (per-team
  button) or via ``/sync/all``; commits are the cadence-sensitive source
  that benefits most from background polling.
* **Never triggers conflict analysis.** Meetings remain the only natural
  checkpoint. The poller just keeps memory current.
* **Per-source errors are isolated** so one broken repo doesn't stall the
  others.
* **Cooperative cancellation** via an asyncio.Event so FastAPI lifespan
  shutdown is fast.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from backend.storage import get_store
from backend.sync import sync_repo

log = logging.getLogger(__name__)


class BackgroundPoller:
    def __init__(self, interval_seconds: int = 60):
        # Floor at 10s so a misconfigured env var can't hammer GitHub.
        self.interval = max(10, interval_seconds)
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

        self.last_poll_at: Optional[datetime] = None
        self.last_poll_duration_ms: Optional[int] = None
        self.last_poll_error: Optional[str] = None
        self.last_new_entities: int = 0
        self.ticks: int = 0
        self.enabled: bool = False

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval,
            "last_poll_at": self.last_poll_at.isoformat() if self.last_poll_at else None,
            "last_poll_duration_ms": self.last_poll_duration_ms,
            "last_poll_error": self.last_poll_error,
            "last_new_entities": self.last_new_entities,
            "ticks": self.ticks,
            "is_running": self._task is not None and not self._task.done(),
        }

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self.enabled = True
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="synclayer-poller")
        log.info("Background poller started (every %ds)", self.interval)

    async def stop(self) -> None:
        self.enabled = False
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
            self._task = None
        log.info("Background poller stopped")

    async def trigger_now(self) -> dict:
        """Run a single tick on demand. Used by /sync/all-style endpoints."""
        await self._tick_once()
        return self.status()

    async def _run(self) -> None:
        # Small grace period before the first tick so FastAPI startup logs
        # finish cleanly. Bail out early if shutdown was requested.
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=5.0)
            return
        except asyncio.TimeoutError:
            pass

        while not self._stop.is_set():
            try:
                await self._tick_once()
            except Exception as exc:  # noqa: BLE001
                # Defensive: never let an unexpected error kill the loop.
                self.last_poll_error = f"tick crashed: {exc}"
                log.exception("Poller tick crashed")

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
                return
            except asyncio.TimeoutError:
                continue

    async def _tick_once(self) -> None:
        store = get_store()
        cfg = store.company_config()
        teams = cfg.get("teams", {}) or {}

        started = datetime.utcnow()
        new_total = 0
        errors: list[str] = []
        loop = asyncio.get_running_loop()

        for team_name, t_cfg in teams.items():
            for repo in t_cfg.get("repos") or []:
                try:
                    r = await loop.run_in_executor(None, sync_repo, team_name, repo)
                    new_total += int(r.get("new_entities", 0))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{team_name}/{repo}: {exc}")
                    log.warning("Poller repo sync failed for %s/%s: %s", team_name, repo, exc)

        self.last_poll_at = started
        self.last_poll_duration_ms = int(
            (datetime.utcnow() - started).total_seconds() * 1000
        )
        self.last_poll_error = "; ".join(errors) if errors else None
        self.last_new_entities = new_total
        self.ticks += 1

        if new_total > 0:
            log.info(
                "Poller tick #%d: +%d new entities across %d team(s)",
                self.ticks, new_total, len(teams),
            )


_poller_singleton: Optional[BackgroundPoller] = None


def get_poller() -> BackgroundPoller:
    global _poller_singleton
    if _poller_singleton is None:
        from backend.config import POLL_INTERVAL_SECONDS

        _poller_singleton = BackgroundPoller(POLL_INTERVAL_SECONDS)
    return _poller_singleton
