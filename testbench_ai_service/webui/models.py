from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class SessionResponse(BaseModel):
    """Identity of the current console user. Deliberately carries no token."""

    username: str
    roles: list[str]
    is_admin: bool
    tb_server_url: str


class MetaResponse(BaseModel):
    """The only unauthenticated payload: which TestBench this service signs into.

    The login screen needs it before a session can exist. Nothing else belongs
    here.
    """

    tb_server_url: str
