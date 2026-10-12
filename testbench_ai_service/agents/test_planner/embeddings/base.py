from abc import ABC, abstractmethod

import numpy as np


class EmbeddingClient(ABC):
    """Turns texts into embedding vectors."""

    @abstractmethod
    async def embed(self, texts: list[str]) -> np.ndarray:
        """
        Embed the texts.

        Returns:
            A float32 matrix with one row per text, in the order of ``texts``.
        """

    async def close(self) -> None:  # noqa: B027 - optional hook, no-op by default
        """Release connections or credentials held by the client."""
