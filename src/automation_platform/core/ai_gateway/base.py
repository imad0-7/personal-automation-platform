from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AIRequest:
    task_type: str
    content: str
    requirements: dict[str, Any] = field(default_factory=dict)
    max_cost_eur: float | None = None
    priority: str = "normal"
    max_tokens: int | None = None
    allowed_models: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AIResult:
    output: str
    provider: str
    model: str
    estimated_cost_eur: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class AIGateway(Protocol):
    def analyze(self, request: AIRequest) -> AIResult: ...
