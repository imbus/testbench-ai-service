from datetime import datetime

from pydantic import BaseModel, Field


class Result(BaseModel):
    execStatus: str
    status: str
    verdict: str
    timestamp: str = Field(default=datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"))  # noqa: DTZ005


class TestCase(BaseModel):
    testCaseExecutionKey: str
    durationMillis: int
    uniqueID: str
    result: Result


class Comments(BaseModel):
    html: str | None


class TestCaseSetProtocol(BaseModel):
    testCaseSetKey: str
    durationMillis: int
    executionKey: str
    comments: Comments
    testCases: list[TestCase]
