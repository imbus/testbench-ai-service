import pytest
from pydantic import ValidationError

from testbench_ai_service.llm.base import LLMProvider
from testbench_ai_service.models.config import LLMConfig


def test_timeout_zero_rejected():
    with pytest.raises(ValidationError):
        LLMConfig(provider=LLMProvider.OPENAI, timeout=0)


def test_timeout_negative_rejected():
    with pytest.raises(ValidationError):
        LLMConfig(provider=LLMProvider.OPENAI, timeout=-1)


def test_timeout_positive_accepted():
    config = LLMConfig(provider=LLMProvider.OPENAI, timeout=0.5)
    assert config.timeout == 0.5


def test_max_retries_negative_rejected():
    with pytest.raises(ValidationError):
        LLMConfig(provider=LLMProvider.OPENAI, max_retries=-1)


def test_max_retries_zero_accepted():
    config = LLMConfig(provider=LLMProvider.OPENAI, max_retries=0)
    assert config.max_retries == 0


def test_timeout_and_max_retries_default_to_none():
    config = LLMConfig(provider=LLMProvider.OPENAI)
    assert config.timeout is None
    assert config.max_retries is None
