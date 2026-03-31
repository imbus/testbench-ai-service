import unittest
from unittest.mock import AsyncMock, patch

from testbench_ai_service.llm.openai import CHAT_MODELS, REASONING_MODELS, OpenAIClient
from testbench_ai_service.models.prompt import Message


class TestModelSets(unittest.TestCase):
    """Sanity checks for the declared model sets."""

    def test_chat_models_is_non_empty_frozenset(self):
        self.assertIsInstance(CHAT_MODELS, frozenset)
        self.assertTrue(len(CHAT_MODELS) > 0)

    def test_reasoning_models_is_non_empty_frozenset(self):
        self.assertIsInstance(REASONING_MODELS, frozenset)
        self.assertTrue(len(REASONING_MODELS) > 0)

    def test_sets_are_disjoint(self):
        """No model should appear in both CHAT_MODELS and REASONING_MODELS."""
        overlap = CHAT_MODELS & REASONING_MODELS
        self.assertEqual(overlap, frozenset(), f"Overlapping models: {overlap}")

    def test_known_chat_model_is_in_chat_models(self):
        self.assertIn("gpt-4o", CHAT_MODELS)

    def test_known_reasoning_model_is_in_reasoning_models(self):
        self.assertIn("o1", REASONING_MODELS)


class TestOpenAIClientQueryLlm(unittest.IsolatedAsyncioTestCase):
    """Tests for ``OpenAIClient.query_llm``."""

    def _make_client(self):
        with patch("testbench_ai_service.llm.openai.AsyncOpenAI"):
            return OpenAIClient(api_key="test-key")

    async def test_chat_model_uses_chat_completions(self):
        """Chat models call _create_response which routes through client.responses.create."""
        client = self._make_client()
        mock_response = AsyncMock()
        mock_response.output_text = "Chat response"
        client.client.responses.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        result = await client.query_llm("gpt-4o", messages)
        self.assertEqual(result, "Chat response")
        client.client.responses.create.assert_awaited_once()

    async def test_reasoning_model_uses_responses_api(self):
        client = self._make_client()
        mock_response = AsyncMock()
        mock_response.output_text = "Reasoning response"
        client.client.responses.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Reason about this")]
        result = await client.query_llm("o1", messages)
        self.assertEqual(result, "Reasoning response")
        client.client.responses.create.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
