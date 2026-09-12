from .base import AIRequest, AIResult


class DisabledAIGateway:
    """Stable V1 seam; no model or provider is configured."""

    def analyze(self, request: AIRequest) -> AIResult:
        raise RuntimeError(f"AI Gateway is disabled; task '{request.task_type}' was not executed")
