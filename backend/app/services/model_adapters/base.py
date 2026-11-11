"""
AI Compass - Base Model Adapter
Defines the interface all adapters must implement.
"""
from abc import ABC, abstractmethod
from typing import Optional
from app.schemas.model import ModelMetadata


class BaseModelAdapter(ABC):
    def __init__(self, model: ModelMetadata):
        self.model = model
        self._last_latency = None
        self._last_input_tokens = None
        self._last_output_tokens = None

    @abstractmethod
    def generate(self, query: str, max_tokens: int = 512) -> str:
        """Generate a response for the given query."""
        ...

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens + output_tokens) / 1000 * self.model.cost_per_1k_tokens

    def health_check(self) -> bool:
        return self.model.active

    def evaluate_availability(self) -> bool:
        return self.health_check()

    def get_model_metadata(self) -> ModelMetadata:
        return self.model

    def get_usage(self) -> dict:
        input_tokens = self._last_input_tokens
        output_tokens = self._last_output_tokens
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": (input_tokens + output_tokens) if input_tokens is not None and output_tokens is not None else None,
            "estimated_cost": self.estimate_cost(input_tokens, output_tokens) if input_tokens is not None and output_tokens is not None else None,
            "latency_ms": round(self._last_latency * 1000, 1) if self._last_latency is not None else None,
        }
