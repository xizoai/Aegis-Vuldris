"""OpenAI `chat/completions` shape <-> Aegis `ModelRequest`/`ModelResponse`.

Pure translation, no I/O. The shim's security properties live elsewhere (the
route binds the target from the scan token, the adapter enforces network
policy); these functions deliberately accept no target so a URL or host can
never smuggle itself in through a "model" field here.
"""

from typing import Any

from app.adapters.errors import ModelProviderError
from app.models.model import ModelMessage, ModelRequest, ModelResponse

_MAX_MESSAGES = 100
_MAX_TOKENS = 100_000
_VALID_ROLES = {"system", "user", "assistant", "tool"}


def to_model_request(body: dict[str, Any]) -> ModelRequest:
    """Convert an OpenAI chat-completions request body.

    ``model`` is deliberately dropped rather than forwarded: the target's
    configured model is authoritative, and honoring a caller-supplied model
    name would let a tool address a different deployment on the same endpoint.
    """

    if not isinstance(body, dict):
        raise ModelProviderError("request body must be a JSON object")

    raw_messages = body.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise ModelProviderError("messages must be a non-empty list")
    if len(raw_messages) > _MAX_MESSAGES:
        raise ModelProviderError("too many messages")

    messages: list[ModelMessage] = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            raise ModelProviderError("each message must be an object")
        role = raw.get("role")
        content = raw.get("content")
        if role not in _VALID_ROLES or not isinstance(content, str):
            raise ModelProviderError("message role and string content are required")
        messages.append(ModelMessage(role=role, content=content))

    temperature = body.get("temperature")
    if temperature is not None and not isinstance(temperature, (int, float)):
        raise ModelProviderError("temperature must be a number")

    max_tokens = body.get("max_tokens")
    if max_tokens is not None and not isinstance(max_tokens, int):
        raise ModelProviderError("max_tokens must be an integer")

    stop = body.get("stop")
    if stop is not None:
        if isinstance(stop, str):
            stop = [stop]
        if not isinstance(stop, list) or not all(isinstance(item, str) for item in stop):
            raise ModelProviderError("stop must be a string or a list of strings")

    try:
        return ModelRequest(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise ModelProviderError(str(exc)) from exc


def to_chat_completion(response: ModelResponse, *, model: str | None) -> dict[str, Any]:
    """Render a normalized response in the OpenAI `chat.completions` shape."""

    usage: dict[str, Any] | None = None
    if response.usage is not None:
        usage = {
            "prompt_tokens": response.usage.prompt_tokens or 0,
            "completion_tokens": response.usage.completion_tokens or 0,
            "total_tokens": response.usage.total_tokens or 0,
        }

    return {
        "id": response.provider_request_id or "chatcmpl-aegis-shim",
        "object": "chat.completion",
        "created": 0,
        "model": response.model or model or "unknown",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response.output},
                "finish_reason": response.finish_reason or "stop",
            }
        ],
        "usage": usage,
    }


__all__ = ["to_chat_completion", "to_model_request"]
