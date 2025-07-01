from collections import defaultdict
from datetime import datetime
from typing import Optional


class StatsReporter:
    """Centralize all counters."""

    def __init__(self):
        self.stats = defaultdict(int)
        self.per_domain = defaultdict(lambda: defaultdict(int))
        self.start_time: Optional[datetime] = None

    def set_start_time(self, start_time: datetime):
        self.start_time = start_time

    def get_start_time_iso(self) -> Optional[str]:
        if self.start_time:
            return self.start_time.isoformat()
        return None

    def bump(self, key: str, domain: str = None, n: int = 1):
        self.stats[key] += n
        if domain:
            self.per_domain[domain][key] += n
