"""OpenAI-compatible model adapter."""

from typing import Any

from app.adapters.base import BaseTargetAdapter, ModelProviderError
from app.models.model import ModelRequest, ModelResponse, ModelUsage
from app.models.target import Target, TargetProvider


class OpenAICompatibleAdapter(BaseTargetAdapter):
    """Adapter for OpenAI-compatible chat completion endpoints."""

    provider = TargetProvider.OPENAI_COMPATIBLE

    async def _generate(
        self,
        target: Target,
        request: ModelRequest,
        *,
        credentials: str | None,
    ) -> ModelResponse:
        payload = self._build_payload(target, request)
        body = await self._post_json(
            target,
            "/chat/completions",
            payload,
            credentials=credentials,
        )
        return self._parse_response(body, target.model)

    async def list_models(
        self,
        target: Target,
        *,
        credentials: str | None = None,
    ) -> list[str]:
        """Return the model identifiers from the provider's /models endpoint.

        The OpenAI listing response is ``{"data": [{"id": ...}, ...]}``.
        Entries without a usable string id are skipped rather than failing
        the whole listing, because some routers include placeholder rows.
        """

        body = await self._get_json(target, "/models", credentials=credentials)
        entries = body.get("data")
        if not isinstance(entries, list):
            raise ModelProviderError("model provider returned an unexpected model list")
        models: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            model_id = entry.get("id")
            if isinstance(model_id, str) and model_id and model_id not in models:
                models.append(model_id)
        return models

    def _build_payload(self, target: Target, request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model or target.model,
            "messages": self._messages(request),
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_tokens,
            "seed": request.seed,
        }
        if request.stop is not None:
            payload["stop"] = request.stop
        for key, value in request.provider_options.items():
            if key not in {
                "model",
                "messages",
                "temperature",
                "top_p",
                "max_tokens",
                "seed",
                "stop",
            }:
                payload[key] = value
        return {key: value for key, value in payload.items() if value is not None}

    @staticmethod
    def _messages(request: ModelRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(message.model_dump() for message in request.messages)
        return messages

    @classmethod
    def _parse_response(cls, body: dict[str, Any], fallback_model: str | None) -> ModelResponse:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelProviderError("model provider response has no choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ModelProviderError("model provider response choice is invalid")
        message = choice.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ModelProviderError("model provider response message is invalid")
        usage_body = body.get("usage")
        usage = None
        if isinstance(usage_body, dict):
            usage = ModelUsage(
                prompt_tokens=usage_body.get("prompt_tokens"),
                completion_tokens=usage_body.get("completion_tokens"),
                total_tokens=usage_body.get("total_tokens"),
            )
        return ModelResponse(
            output=message["content"],
            finish_reason=choice.get("finish_reason"),
            model=body.get("model") or fallback_model,
            usage=usage,
            provider_request_id=body.get("id"),
            metadata={"provider": "openai_compatible"},
        )


__all__ = ["OpenAICompatibleAdapter"]
