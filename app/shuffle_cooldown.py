"""In-memory cooldown tracker for recently shuffled recipes.

Tracks recipe IDs that the user has shuffled past so they are strongly
penalized / avoided for a configurable cooldown window (default 30 minutes),
then automatically expire back to full eligibility.
"""

import time
from typing import Callable, Dict, Iterable, Optional


class ShuffleCooldownTracker:
    """Tracks recently shuffled recipe IDs with an expiring TTL window."""

    def __init__(
        self,
        cooldown_seconds: float = 1800.0,
        time_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._time_fn = time_fn or time.time
        self._shuffled_at: Dict[str, float] = {}

    def _prune(self, now: float) -> None:
        """Remove entries whose cooldown window has elapsed."""
        if self.cooldown_seconds <= 0:
            self._shuffled_at.clear()
            return
        cutoff = now - self.cooldown_seconds
        expired = [rid for rid, ts in self._shuffled_at.items() if ts <= cutoff]
        for rid in expired:
            del self._shuffled_at[rid]

    def record_shuffled(self, recipe_ids: Iterable[str]) -> None:
        """Record recipe IDs that were just shuffled away."""
        if self.cooldown_seconds <= 0:
            return
        now = self._time_fn()
        self._prune(now)
        for raw_id in recipe_ids:
            rid = str(raw_id).strip() if raw_id is not None else ""
            if rid:
                self._shuffled_at[rid] = now

    def get_penalties(self) -> Dict[str, float]:
        """Return active penalized recipe IDs mapped to remaining cooldown fraction in (0, 1].

        A value close to 1.0 means the recipe was just shuffled away;
        a value close to 0.0 means its cooldown is almost expired.
        """
        if self.cooldown_seconds <= 0:
            return {}
        now = self._time_fn()
        self._prune(now)
        penalties: Dict[str, float] = {}
        for rid, ts in self._shuffled_at.items():
            elapsed = max(0.0, now - ts)
            remaining = (self.cooldown_seconds - elapsed) / self.cooldown_seconds
            if remaining > 0.0:
                penalties[rid] = min(1.0, remaining)
        return penalties

    def clear(self) -> None:
        """Clear all recorded shuffle cooldowns."""
        self._shuffled_at.clear()
