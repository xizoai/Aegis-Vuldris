"""Custom REST model adapter."""

import re
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from app.adapters.base import BaseTargetAdapter, ModelProviderError
from app.models.model import ModelRequest, ModelResponse
from app.models.target import Target, TargetProvider

# Fields whose effective value must come from the normalized request, never
# from a test's provider_options. This keeps the run manifest honest about the
# settings that were actually used.
_RESERVED_PROVIDER_OPTIONS: frozenset[str] = frozenset(
    {"model", "messages", "temperature", "top_p", "max_tokens", "seed", "stop"}
)


class CustomRESTConfig(BaseModel):
    """Validated configuration for a custom REST model endpoint."""

    model_config = {"extra": "forbid"}

    method: str = "POST"
    path: str | None = None
    response_path: str = "output"
    response_path_fallbacks: list[str] = Field(
        default_factory=lambda: ["response", "message.content", "choices[0].message.content"]
    )
    auth_header_name: str = "Authorization"
    auth_scheme: str = "Bearer"
    headers: dict[str, str] = Field(default_factory=dict)


# Request paths that are inference calls, not a base URL. A custom endpoint is
# allowed to contain a full request path, so model discovery strips one of
# these before probing for a model list.
_INFERENCE_PATH_SUFFIXES: tuple[str, ...] = (
    "/chat/completions",
    "/completions",
    "/api/chat",
    "/api/generate",
)

# A trailing version segment (``/v1``, ``/v1beta``, ...) identifies an
# OpenAI-style API base rather than a request path: the chat route lives
# under it (``/v1/chat/completions``).
_VERSION_SEGMENT_RE = re.compile(r"/v\d+[a-z0-9]*$", re.IGNORECASE)


def generation_candidates(endpoint: str) -> list[tuple[str, bool]]:
    """Return candidate inference requests for a custom REST endpoint.

    Each candidate is ``(path_to_append, openai_style)``: the path is
    appended to the endpoint to build the request URL, and ``openai_style``
    selects the top-level OpenAI chat payload shape instead of the nested
    custom ``parameters`` block.

    A custom endpoint may be a full inference URL, but a commonly stored
    value is the API base: posting to it directly returns HTTP 405/404. The
    most likely correct request is tried first:

    * a path already ending in an inference suffix (``/chat/completions``,
      ``/api/chat``, ...) is used as given;
    * a path ending in a version segment (``/v1``) gets the conventional
      OpenAI chat path appended;
    * anything else is tried as given first, then with the chat path
      appended.
    """

    base = endpoint.rstrip("/")
    path = urlsplit(base).path

    if path.endswith(_INFERENCE_PATH_SUFFIXES):
        return [("", path.endswith("/chat/completions"))]

    if _VERSION_SEGMENT_RE.search(path):
        return [("/chat/completions", True), ("", False)]

    return [("", False), ("/chat/completions", True)]


def model_list_candidates(endpoint: str) -> list[str]:
    """Return candidate model-listing URLs for a custom REST endpoint.

    Custom endpoints have no standard listing API, so the usual conventions
    are probed in order: an OpenAI-compatible ``/models`` (LM Studio, vLLM,
    LocalAI), a versioned ``/v1/models`` (bare hosts and path-based bases),
    and Ollama's ``/api/tags``. When the endpoint itself is an inference URL
    — a commonly pasted value ending in ``/chat/completions`` or ``/api/chat``
    — that request path is stripped first so the base can be probed.
    """

    parsed = urlsplit(endpoint)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    base = parsed.path.rstrip("/")
    for suffix in _INFERENCE_PATH_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break

    candidates: list[str] = []

    def add(url_path: str) -> None:
        candidate = f"{origin}{url_path}"
        if candidate not in candidates:
            candidates.append(candidate)

    if base.endswith("/v1"):
        add(f"{base}/models")
    else:
        add(f"{base}/v1/models")
        add(f"{base}/models")
    add(f"{base}/api/tags")
    return candidates


def _extract_model_ids(body: dict[str, Any]) -> list[str]:
    """Pull model identifiers from the common listing payload shapes."""

    models: list[str] = []

    def add(identifier: Any) -> None:
        if isinstance(identifier, str) and identifier and identifier not in models:
            models.append(identifier)

    data = body.get("data")
    if isinstance(data, list):
        for entry in data:
            if isinstance(entry, str):
                add(entry)
            elif isinstance(entry, dict):
                add(entry.get("id") or entry.get("name") or entry.get("model"))

    entries = body.get("models")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, str):
                add(entry)
            elif isinstance(entry, dict):
                add(entry.get("name") or entry.get("id") or entry.get("model"))

    return models


class CustomRESTAdapter(BaseTargetAdapter):
    """Adapter for a configured JSON REST inference endpoint."""

    provider = TargetProvider.CUSTOM_REST

    def __init__(
        self,
        *,
        client: Any | None = None,
        credential_resolver: Any | None = None,
        config: CustomRESTConfig | None = None,
        max_response_bytes: int = 4 * 1024 * 1024,
        endpoint_validator: Any | None = None,
        target_resolver: Any | None = None,
    ) -> None:
        super().__init__(
            client=client,
            credential_resolver=credential_resolver,
            max_response_bytes=max_response_bytes,
            endpoint_validator=endpoint_validator,
            target_resolver=target_resolver,
        )
        self.config = config or CustomRESTConfig()
        # The request path (and payload style) that last worked, so the rest
        # of a run skips the probing requests.
        self._resolved_candidate: tuple[str, bool] | None = None

    async def _generate(
        self,
        target: Target,
        request: ModelRequest,
        *,
        credentials: str | None,
    ) -> ModelResponse:
        headers = dict(self.config.headers)
        resolved_credentials = await self._resolve_credentials(target, credentials)
        if resolved_credentials:
            headers[self.config.auth_header_name] = (
                f"{self.config.auth_scheme} {resolved_credentials}"
            )

        if self.config.path is not None:
            # An explicitly configured request path is honored as given.
            response = await self._post_json(
                target,
                self.config.path,
                self._custom_payload(target, request),
                headers=headers,
                credentials=None,
            )
            return self._parse_response(response, target.model)

        if self._resolved_candidate is not None:
            candidates = [self._resolved_candidate]
        else:
            candidates = generation_candidates(target.endpoint)

        last_error: ModelProviderError | None = None
        for path, openai_style in candidates:
            payload = (
                self._openai_payload(target, request)
                if openai_style
                else self._custom_payload(target, request)
            )
            try:
                response = await self._post_json(
                    target,
                    path,
                    payload,
                    headers=headers,
                    credentials=None,
                )
            except ModelProviderError as error:
                last_error = error
                # A 404/405 means the URL cannot serve this POST, so the next
                # candidate is tried; anything else is a real provider answer.
                if error.provider_status not in (404, 405):
                    raise
                continue
            self._resolved_candidate = (path, openai_style)
            return self._parse_response(response, target.model)

        assert last_error is not None
        if last_error.provider_status in (404, 405):
            raise ModelProviderError(
                f"{last_error} — the endpoint may be a base URL missing its "
                "request path; use the full inference URL (for example "
                "https://host/v1/chat/completions)",
                provider_status=last_error.provider_status,
            )
        raise last_error

    def _custom_payload(self, target: Target, request: ModelRequest) -> dict[str, Any]:
        # Reserved fields are set from the normalized request. Provider options
        # may add unrelated parameters but may not silently override the
        # values the run manifest claims were effective.
        provider_options = {
            key: value
            for key, value in request.provider_options.items()
            if key not in _RESERVED_PROVIDER_OPTIONS
        }
        payload: dict[str, Any] = {
            "model": request.model or target.model,
            "messages": self._messages(request),
            "parameters": {
                "temperature": request.temperature,
                "top_p": request.top_p,
                "max_tokens": request.max_tokens,
                "seed": request.seed,
                "stop": request.stop,
                **provider_options,
            },
        }
        return {key: value for key, value in payload.items() if value is not None}

    def _openai_payload(self, target: Target, request: ModelRequest) -> dict[str, Any]:
        provider_options = {
            key: value
            for key, value in request.provider_options.items()
            if key not in _RESERVED_PROVIDER_OPTIONS
        }
        payload: dict[str, Any] = {
            "model": request.model or target.model,
            "messages": self._messages(request),
            "temperature": request.temperature,
            "top_p": request.top_p,
            "max_tokens": request.max_tokens,
            "seed": request.seed,
            "stop": request.stop,
            **provider_options,
        }
        return {key: value for key, value in payload.items() if value is not None}

    async def list_models(
        self,
        target: Target,
        *,
        credentials: str | None = None,
    ) -> list[str]:
        """Best-effort model discovery for custom REST endpoints.

        Custom endpoints have no standard listing API, so the usual
        conventions are probed in order (see :func:`model_list_candidates`).
        An error or a non-listing response on one candidate simply moves to
        the next; only when every candidate fails does discovery give up, so
        the tester can still enter the model name manually. Every probe goes
        through the same pinned network policy as a real run.
        """

        for candidate in model_list_candidates(target.endpoint):
            probe = Target(
                provider=target.provider,
                endpoint=candidate,
                model=None,
                timeout_seconds=target.timeout_seconds,
            )
            try:
                body = await self._request_json(
                    "GET",
                    probe,
                    "",
                    headers=dict(self.config.headers) or None,
                    credentials=credentials,
                )
            except ModelProviderError:
                continue
            models = _extract_model_ids(body)
            if models:
                return models

        raise ModelProviderError(
            "custom REST endpoint does not expose a model list at the usual "
            "paths (/v1/models, /models, /api/tags)"
        )

    @staticmethod
    def _messages(request: ModelRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(message.model_dump() for message in request.messages)
        return messages

    def _parse_response(self, body: dict[str, Any], fallback_model: str | None) -> ModelResponse:
        output = self._extract_string(body, self.config.response_path)
        if output is None:
            for fallback in self.config.response_path_fallbacks:
                output = self._extract_string(body, fallback)
                if output is not None:
                    break
        if output is None:
            raise ModelProviderError("custom REST response has no output")
        return ModelResponse(
            output=output,
            model=body.get("model") or fallback_model,
            metadata={"provider": "custom_rest"},
        )

    @classmethod
    def _extract_string(cls, body: dict[str, Any], path: str) -> str | None:
        current: Any = body
        for part in cls._path_parts(path):
            if isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    return None
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        if isinstance(current, str):
            return current
        if isinstance(current, (dict, list)):
            return str(current)
        return None

    @staticmethod
    def _path_parts(path: str) -> list[str]:
        return [part for part in path.replace("[", ".").replace("]", "").split(".") if part]


__all__ = [
    "CustomRESTAdapter",
    "CustomRESTConfig",
    "generation_candidates",
    "model_list_candidates",
]
