from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import settings


def quota_day() -> dt.date:
    try:
        timezone = ZoneInfo(settings.quota_timezone)
    except ZoneInfoNotFoundError:
        timezone = dt.timezone.utc
    return dt.datetime.now(timezone).date()

