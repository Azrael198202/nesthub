from __future__ import annotations

from abc import ABC, abstractmethod


class ModelProvider(ABC):
    @abstractmethod
    def is_available(self, model_name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def ensure(self, model_name: str) -> None:
        raise NotImplementedError
