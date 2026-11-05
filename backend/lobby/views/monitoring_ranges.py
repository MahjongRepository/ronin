from datetime import timedelta
from enum import StrEnum

_HOURS_PER_UNIT = {"h": 1, "d": 24}


class MonitoringRange(StrEnum):
    """
    A look-back range of the monitoring page, its value an amount and a unit (``h`` hours, ``d`` days).
    """

    HOUR = "1h"
    DAY = "24h"
    WEEK = "7d"
    MONTH = "30d"
    QUARTER = "90d"

    @property
    def duration(self) -> timedelta:
        return timedelta(hours=int(self.value[:-1]) * _HOURS_PER_UNIT[self.value[-1]])

    @property
    def label_key(self) -> str:
        return f"monitoring.range.{self.value}"


DEFAULT_MONITORING_RANGE = MonitoringRange.DAY
