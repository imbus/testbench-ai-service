from pydantic import BaseModel


class AdminUiConfig(BaseModel):
    """Configuration for the browser console served at /admin."""

    enabled: bool = True
    require_loopback: bool = False
