"""Model adapter behavior tests for Aegis Vuldris."""

import asyncio
import json
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import uuid4

import httpx2
import pytest
from app.adapters.custom_rest import CustomRESTAdapter
from app.adapters.errors import ModelProviderError
from app.adapters.ollama import OllamaAdapter
from app.adapters.openai_compatible import OpenAICompatibleAdapter
from app.adapters.registry import AdapterRegistry
from app.models.model import ModelMessage, ModelRequest
from app.models.target import Target, TargetProvider
from app.security.network import PinnedTarget


class FakeResponse:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self.content = json.dumps(body).encode("utf-8")

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


def _bypass_resolver(endpoint: str) -> PinnedTarget:
    """Pin without DNS; these tests use unroutable example domains."""

    return PinnedTarget(url=endpoint, hostname="model.example.com", address="127.0.0.1")


class FakeClient:
    """Minimal async httpx2 client double for adapter tests."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        body: Any = None,
        exc: Exception | None = None,
        max_bytes_override: int | None = None,
        by_path: dict[str, tuple[int, Any]] | None = None,
    ) -> None:
        self.status_code = status_code
        self.body = body if body is not None else {}
        self.exc = exc
        self.calls: list[dict[str, Any]] = []
        self._max_bytes_override = max_bytes_override
        self.by_path = by_path

    async def post(
        self,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        follow_redirects: bool = False,
        extensions: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
                "follow_redirects": follow_redirects,
            }
        )
        if self.exc is not None:
            raise self.exc
        if self.by_path is not None:
            path = urlsplit(url).path
            if path in self.by_path:
                status, body = self.by_path[path]
                return FakeResponse(status, body)
        return FakeResponse(self.status_code, self.body)

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        follow_redirects: bool = False,
        extensions: dict[str, Any] | None = None,
    ) -> Any:
        self.calls.append(
            {
                "url": url,
                "json": None,
                "headers": headers,
                "timeout": timeout,
                "follow_redirects": follow_redirects,
            }
        )
        if self.exc is not None:
            raise self.exc
        if self.by_path is not None:
            path = urlsplit(url).path
            if path in self.by_path:
                status, body = self.by_path[path]
                return FakeResponse(status, body)
        return FakeResponse(self.status_code, self.body)

    async def aclose(self) -> None:
        pass


def _make_target(
    *,
    provider: TargetProvider,
    endpoint: str = "https://model.example.com/v1",
    model: str | None = "test-model",
    timeout_seconds: float = 30.0,
) -> Target:
    return Target(
        id=uuid4(),
        project_id=uuid4(),
        name="test-target",
        provider=provider,
        endpoint=endpoint,
        model=model,
        capabilities=["chat"],
        timeout_seconds=timeout_seconds,
        rate_limit_per_minute=60,
    )


def _make_request() -> ModelRequest:
    return ModelRequest(
        messages=[
            ModelMessage(role="system", content="you are helpful"),
            ModelMessage(role="user", content="hello"),
        ]
    )


def _bypass_validator(url: str) -> str:
    return url


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_registry_creates_adapter_per_provider() -> None:
    registry = AdapterRegistry()
    assert isinstance(registry.create(TargetProvider.OPENAI_COMPATIBLE), OpenAICompatibleAdapter)
    assert isinstance(registry.create(TargetProvider.OLLAMA), OllamaAdapter)
    assert isinstance(registry.create(TargetProvider.CUSTOM_REST), CustomRESTAdapter)


def test_validate_target_rejects_missing_endpoint() -> None:
    adapter = OpenAICompatibleAdapter(
        client=cast(Any, FakeClient()),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OPENAI_COMPATIBLE, endpoint="")
    with pytest.raises(ValueError):
        _run(adapter.validate_target(target))


def test_generate_rejects_provider_mismatch() -> None:
    adapter = OpenAICompatibleAdapter(
        client=cast(Any, FakeClient()),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OLLAMA)
    with pytest.raises(ValueError):
        _run(adapter.generate(target, _make_request()))


def test_generate_rejects_missing_model() -> None:
    adapter = OpenAICompatibleAdapter(
        client=cast(Any, FakeClient()),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OPENAI_COMPATIBLE, model=None)
    with pytest.raises(ValueError):
        _run(adapter.generate(target, _make_request()))


def test_openai_compatible_adapter_returns_normalized_output() -> None:
    fake = FakeClient(
        body={
            "id": "chatcmpl-1",
            "model": "gpt-4o",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "hello there"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 3,
                "total_tokens": 8,
            },
        }
    )
    adapter = OpenAICompatibleAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OPENAI_COMPATIBLE)
    response = _run(adapter.generate(target, _make_request(), credentials="secret"))

    assert response.output == "hello there"
    assert response.model == "gpt-4o"
    assert response.finish_reason == "stop"
    assert response.provider_request_id == "chatcmpl-1"
    assert response.usage is not None
    assert response.usage.total_tokens == 8
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer secret"


def test_adapters_forward_generation_profile_without_provider_override() -> None:
    request = _make_request().model_copy(
        update={
            "temperature": 0.3,
            "top_p": 0.8,
            "max_tokens": 128,
            "seed": 42,
            # Provider options must not silently replace normalized values,
            # including the model identifier and the message list.
            "provider_options": {
                "top_p": 0.1,
                "seed": 1,
                "num_ctx": 2048,
                "model": "attacker-model",
                "messages": [],
            },
        }
    )

    openai_fake = FakeClient(body={"choices": [{"message": {"content": "ok"}}]})
    openai_adapter = OpenAICompatibleAdapter(
        client=cast(Any, openai_fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    _run(openai_adapter.generate(_make_target(provider=TargetProvider.OPENAI_COMPATIBLE), request))
    openai_payload = openai_fake.calls[0]["json"]
    assert openai_payload["temperature"] == 0.3
    assert openai_payload["top_p"] == 0.8
    assert openai_payload["max_tokens"] == 128
    assert openai_payload["seed"] == 42
    assert openai_payload["num_ctx"] == 2048
    assert openai_payload["model"] == "test-model"
    assert openai_payload["messages"][0]["content"] == "you are helpful"

    ollama_fake = FakeClient(body={"model": "llama3", "done": True, "message": {"content": "ok"}})
    ollama_adapter = OllamaAdapter(
        client=cast(Any, ollama_fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    _run(ollama_adapter.generate(_make_target(provider=TargetProvider.OLLAMA), request))
    ollama_options = ollama_fake.calls[0]["json"]["options"]
    assert ollama_options["temperature"] == 0.3
    assert ollama_options["top_p"] == 0.8
    assert ollama_options["num_predict"] == 128
    assert ollama_options["seed"] == 42
    assert ollama_options["num_ctx"] == 2048

    custom_adapter = CustomRESTAdapter(
        client=cast(Any, FakeClient(body={"output": "ok"})),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    custom_payload = custom_adapter._custom_payload(
        _make_target(provider=TargetProvider.CUSTOM_REST), request
    )
    parameters = custom_payload["parameters"]
    assert parameters["temperature"] == 0.3
    assert parameters["top_p"] == 0.8
    assert parameters["max_tokens"] == 128
    assert parameters["seed"] == 42
    assert parameters["num_ctx"] == 2048
    assert "model" not in parameters
    assert "messages" not in parameters

    custom_openai_payload = custom_adapter._openai_payload(
        _make_target(provider=TargetProvider.CUSTOM_REST), request
    )
    assert custom_openai_payload["model"] == "test-model"
    assert custom_openai_payload["messages"][0]["content"] == "you are helpful"
    assert custom_openai_payload["num_ctx"] == 2048


def test_ollama_adapter_parses_message_content() -> None:
    fake = FakeClient(
        body={
            "model": "llama3",
            "done": True,
            "total_duration": 1_000_000,
            "message": {"role": "assistant", "content": "hi from ollama"},
        }
    )
    adapter = OllamaAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OLLAMA)
    response = _run(adapter.generate(target, _make_request()))

    assert response.output == "hi from ollama"
    assert response.model == "llama3"
    assert response.metadata["provider"] == "ollama"
    assert response.metadata["done"] is True


def test_ollama_adapter_disables_streaming() -> None:
    """Ollama replies with NDJSON unless streaming is explicitly disabled.

    Without ``"stream": False`` the provider returns one JSON object per line,
    which the shared response parser cannot decode, so every execution fails
    with "model provider returned invalid JSON".
    """

    fake = FakeClient(
        body={
            "model": "llama3",
            "done": True,
            "message": {"role": "assistant", "content": "ok"},
        }
    )
    adapter = OllamaAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OLLAMA)
    _run(adapter.generate(target, _make_request()))

    assert fake.calls[0]["json"]["stream"] is False


def test_request_model_overrides_target_model_for_all_providers() -> None:
    """A per-request model override is sent instead of the target's model.

    This is how judge-model grading pins the judge to a specific model on the
    judge target's endpoint without registering a second target.
    """

    request = ModelRequest(
        messages=[ModelMessage(role="user", content="hello")],
        model="override-model",
    )

    openai_fake = FakeClient(
        body={
            "model": "override-model",
            "choices": [
                {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
            ],
        }
    )
    openai_adapter = OpenAICompatibleAdapter(
        client=cast(Any, openai_fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    _run(openai_adapter.generate(_make_target(provider=TargetProvider.OPENAI_COMPATIBLE), request))
    assert openai_fake.calls[0]["json"]["model"] == "override-model"

    ollama_fake = FakeClient(
        body={"model": "override-model", "done": True, "message": {"content": "ok"}}
    )
    ollama_adapter = OllamaAdapter(
        client=cast(Any, ollama_fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    _run(ollama_adapter.generate(_make_target(provider=TargetProvider.OLLAMA), request))
    assert ollama_fake.calls[0]["json"]["model"] == "override-model"

    custom_fake = FakeClient(body={"output": "ok"})
    custom_adapter = CustomRESTAdapter(
        client=cast(Any, custom_fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    _run(
        custom_adapter.generate(
            _make_target(provider=TargetProvider.CUSTOM_REST), request, credentials="tok"
        )
    )
    assert custom_fake.calls[0]["json"]["model"] == "override-model"


def test_request_without_model_override_uses_target_model() -> None:
    """Without an override the target's model is unchanged (the default path)."""

    fake = FakeClient(
        body={
            "model": "test-model",
            "choices": [
                {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
            ],
        }
    )
    adapter = OpenAICompatibleAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    _run(adapter.generate(_make_target(provider=TargetProvider.OPENAI_COMPATIBLE), _make_request()))

    assert fake.calls[0]["json"]["model"] == "test-model"


def test_custom_rest_adapter_uses_configured_response_path() -> None:
    fake = FakeClient(body={"output": "custom rest reply"})
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.CUSTOM_REST)
    response = _run(adapter.generate(target, _make_request(), credentials="tok"))

    assert response.output == "custom rest reply"
    assert response.metadata["provider"] == "custom_rest"
    # A version base like /v1 receives the conventional chat route.
    assert fake.calls[0]["url"] == "https://model.example.com/v1/chat/completions"
    assert fake.calls[0]["headers"]["Authorization"].startswith("Bearer tok")


def test_custom_rest_adapter_falls_back_on_unexpected_shape() -> None:
    fake = FakeClient(body={"response": "fallback output"})
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.CUSTOM_REST)
    response = _run(adapter.generate(target, _make_request()))

    assert response.output == "fallback output"


def test_openai_compatible_adapter_raises_on_missing_choices() -> None:
    fake = FakeClient(body={"unexpected": "shape"})
    adapter = OpenAICompatibleAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OPENAI_COMPATIBLE)
    with pytest.raises(ModelProviderError):
        _run(adapter.generate(target, _make_request()))


def test_custom_rest_adapter_raises_on_no_output() -> None:
    fake = FakeClient(body={"nothing": "here"})
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.CUSTOM_REST)
    with pytest.raises(ModelProviderError):
        _run(adapter.generate(target, _make_request()))


def test_custom_rest_adapter_appends_chat_path_for_a_version_base() -> None:
    fake = FakeClient(
        by_path={"/v1/chat/completions": (200, {"choices": [{"message": {"content": "hi"}}]})},
    )
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.CUSTOM_REST)
    response = _run(adapter.generate(target, _make_request()))

    assert response.output == "hi"
    assert fake.calls[0]["url"] == "https://model.example.com/v1/chat/completions"
    # The OpenAI chat shape uses top-level options, not the nested custom block.
    assert "parameters" not in fake.calls[0]["json"]


def test_custom_rest_adapter_falls_back_to_the_endpoint_as_given() -> None:
    fake = FakeClient(
        by_path={
            "/v1/chat/completions": (404, {"error": "not found"}),
            "/v1": (200, {"output": "direct"}),
        },
    )
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.CUSTOM_REST)
    response = _run(adapter.generate(target, _make_request()))

    assert response.output == "direct"
    assert [call["url"] for call in fake.calls] == [
        "https://model.example.com/v1/chat/completions",
        "https://model.example.com/v1",
    ]


def test_custom_rest_adapter_reuses_the_resolved_url() -> None:
    fake = FakeClient(
        by_path={
            "/v1/chat/completions": (405, {"error": "method not allowed"}),
            "/v1": (200, {"output": "direct"}),
        },
    )
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.CUSTOM_REST)

    _run(adapter.generate(target, _make_request()))
    _run(adapter.generate(target, _make_request()))

    assert [call["url"] for call in fake.calls] == [
        "https://model.example.com/v1/chat/completions",
        "https://model.example.com/v1",
        "https://model.example.com/v1",
    ]


def test_custom_rest_adapter_keeps_full_inference_urls_as_given() -> None:
    fake = FakeClient(body={"choices": [{"message": {"content": "ok"}}]})
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(
        provider=TargetProvider.CUSTOM_REST,
        endpoint="https://model.example.com/v1/chat/completions",
    )
    response = _run(adapter.generate(target, _make_request()))

    assert response.output == "ok"
    assert fake.calls[0]["url"] == "https://model.example.com/v1/chat/completions"
    assert len(fake.calls) == 1


def test_custom_rest_adapter_hints_when_only_base_urls_fail() -> None:
    fake = FakeClient(status_code=405, body={"error": "method not allowed"})
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.CUSTOM_REST)
    with pytest.raises(ModelProviderError, match="missing its request path"):
        _run(adapter.generate(target, _make_request()))


def test_base_adapter_raises_on_http_error_status() -> None:
    fake = FakeClient(status_code=502, body={"error": "bad gateway"})
    adapter = OpenAICompatibleAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OPENAI_COMPATIBLE)
    with pytest.raises(ModelProviderError, match="HTTP 502"):
        _run(adapter.generate(target, _make_request()))


def test_base_adapter_raises_on_timeout_exception() -> None:
    fake = FakeClient(exc=httpx2.TimeoutException("slow"))
    adapter = OpenAICompatibleAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OPENAI_COMPATIBLE)
    with pytest.raises(ModelProviderError, match="timed out"):
        _run(adapter.generate(target, _make_request()))


def test_openai_compatible_adapter_lists_models() -> None:
    fake = FakeClient(
        body={
            "object": "list",
            "data": [
                {"id": "alpha-model"},
                {"id": "beta-model"},
                {"id": ""},
                {"object": "model"},
                "not-a-dict",
                {"id": "alpha-model"},
            ],
        },
    )
    adapter = OpenAICompatibleAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OPENAI_COMPATIBLE)
    models = _run(adapter.list_models(target))

    assert models == ["alpha-model", "beta-model"]
    assert fake.calls[0]["url"] == "https://model.example.com/v1/models"
    assert fake.calls[0]["headers"].get("Authorization") is None


def test_openai_compatible_adapter_lists_models_with_credentials() -> None:
    fake = FakeClient(body={"data": [{"id": "alpha-model"}]})
    adapter = OpenAICompatibleAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OPENAI_COMPATIBLE)
    models = _run(adapter.list_models(target, credentials="tok"))

    assert models == ["alpha-model"]
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer tok"


def test_ollama_adapter_lists_models() -> None:
    fake = FakeClient(
        body={"models": [{"name": "llama3:8b"}, {"model": "mistral"}, {"name": ""}]},
    )
    adapter = OllamaAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OLLAMA)
    models = _run(adapter.list_models(target))

    assert models == ["llama3:8b", "mistral"]
    assert fake.calls[0]["url"] == "https://model.example.com/v1/api/tags"


def test_list_models_rejects_unexpected_payload() -> None:
    fake = FakeClient(body={"data": "not-a-list"})
    adapter = OpenAICompatibleAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(provider=TargetProvider.OPENAI_COMPATIBLE)
    with pytest.raises(ModelProviderError, match="unexpected model list"):
        _run(adapter.list_models(target))


def test_custom_rest_adapter_discovers_models_behind_an_inference_path() -> None:
    fake = FakeClient(body={"data": [{"id": "alpha-model"}, {"id": "beta-model"}]})
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(
        provider=TargetProvider.CUSTOM_REST,
        endpoint="https://model.example.com/v1/chat/completions",
    )
    models = _run(adapter.list_models(target, credentials="tok"))

    assert models == ["alpha-model", "beta-model"]
    # The inference path is stripped before the conventional list path.
    assert fake.calls[0]["url"] == "https://model.example.com/v1/models"
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer tok"


def test_custom_rest_adapter_falls_back_across_conventional_paths() -> None:
    fake = FakeClient(
        by_path={
            "/v1/models": (404, {"error": "not found"}),
            "/models": (200, {"data": [{"id": "local-model"}]}),
        },
    )
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(
        provider=TargetProvider.CUSTOM_REST,
        endpoint="https://model.example.com",
    )
    models = _run(adapter.list_models(target))

    assert models == ["local-model"]
    assert [call["url"] for call in fake.calls] == [
        "https://model.example.com/v1/models",
        "https://model.example.com/models",
    ]


def test_custom_rest_adapter_parses_ollama_style_tags() -> None:
    fake = FakeClient(by_path={"/api/tags": (200, {"models": [{"name": "llama3:8b"}]})})
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(
        provider=TargetProvider.CUSTOM_REST,
        endpoint="https://model.example.com/api/chat",
    )
    models = _run(adapter.list_models(target))

    assert models == ["llama3:8b"]
    assert fake.calls[-1]["url"] == "https://model.example.com/api/tags"


def test_custom_rest_adapter_reports_when_no_listing_api_exists() -> None:
    fake = FakeClient(status_code=404)
    adapter = CustomRESTAdapter(
        client=cast(Any, fake),
        endpoint_validator=_bypass_validator,
        target_resolver=_bypass_resolver,
    )
    target = _make_target(
        provider=TargetProvider.CUSTOM_REST,
        endpoint="https://model.example.com/infer",
    )
    with pytest.raises(ModelProviderError, match="usual paths"):
        _run(adapter.list_models(target))
