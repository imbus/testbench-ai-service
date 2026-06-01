from datetime import datetime
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Europe/Berlin")
_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def current_time() -> str:
    return datetime.now(_TZ).strftime(_DATETIME_FORMAT)
