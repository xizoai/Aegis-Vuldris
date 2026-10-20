"""Provider-independent model adapter interface."""

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

import httpx2

from app.adapters.errors import ModelProviderError
from app.models.model import ModelRequest, ModelResponse
from app.models.target import Target, TargetProvider
from app.security.network import (
    NetworkPolicyError,
    PinnedTarget,
    resolve_target,
    validate_target_endpoint,
)

CredentialResolver = Callable[[str], Awaitable[str | None]]
EndpointValidator = Callable[[str], str]
TargetResolver = Callable[..., PinnedTarget]


def _host_header(pinned: PinnedTarget) -> str:
    """Return the Host header value for a pinned destination.

    The port is included when it is not the scheme default, matching what a
    client would otherwise have sent for the original URL.
    """

    host = pinned.hostname
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    return host


class BaseTargetAdapter(ABC):
    """Base implementation for provider-specific model adapters."""

    provider: TargetProvider

    def __init__(
        self,
        *,
        client: httpx2.AsyncClient | None = None,
        credential_resolver: CredentialResolver | None = None,
        max_response_bytes: int = 4 * 1024 * 1024,
        endpoint_validator: EndpointValidator | None = None,
        target_resolver: TargetResolver | None = None,
    ) -> None:
        self.client = client or httpx2.AsyncClient(
            follow_redirects=False,
            timeout=30.0,
        )
        self._owns_client = client is None
        self.credential_resolver = credential_resolver
        self.max_response_bytes = max_response_bytes
        self.endpoint_validator = endpoint_validator or validate_target_endpoint
        # Injectable for the same reason as endpoint_validator: tests need a
        # seam that does not perform real DNS. It defaults to the real policy,
        # so connection-time pinning cannot be silently skipped in production.
        self.target_resolver = target_resolver or resolve_target

    async def close(self) -> None:
        """Close an adapter-owned HTTP client."""

        if self._owns_client:
            await self.client.aclose()

    async def validate_target(self, target: Target) -> None:
        """Validate provider-specific target requirements."""

        if target.provider != self.provider:
            raise ValueError(
                f"adapter {self.provider.value} does not support target provider "
                f"{target.provider.value}"
            )
        if not target.endpoint:
            raise ValueError("target endpoint is required")
        try:
            self.endpoint_validator(target.endpoint)
        except NetworkPolicyError as exc:
            raise ValueError(str(exc)) from exc
        if (
            self.provider in {TargetProvider.OPENAI_COMPATIBLE, TargetProvider.OLLAMA}
            and not target.model
        ):
            raise ValueError(f"model is required for {self.provider.value} targets")

    async def generate(
        self,
        target: Target,
        request: ModelRequest,
        *,
        credentials: str | None = None,
    ) -> ModelResponse:
        """Generate a normalized model response."""

        await self.validate_target(target)
        return await self._generate(target, request, credentials=credentials)

    @abstractmethod
    async def _generate(
        self,
        target: Target,
        request: ModelRequest,
        *,
        credentials: str | None,
    ) -> ModelResponse:
        """Translate a normalized request and return a normalized response."""

    async def _resolve_credentials(self, target: Target, credentials: str | None) -> str | None:
        if credentials is not None:
            return credentials
        if self.credential_resolver is None:
            return None
        return await self.credential_resolver(str(target.id))

    async def list_models(
        self,
        target: Target,
        *,
        credentials: str | None = None,
    ) -> list[str]:
        """Fetch the model identifiers the provider advertises.

        Only providers with a standard listing API implement this. Providers
        without one raise instead of guessing, so the target chooser can fall
        back to manual entry with an honest message.
        """

        raise ModelProviderError(
            f"model discovery is not supported for {self.provider.value} targets"
        )

    async def _post_json(
        self,
        target: Target,
        path: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        credentials: str | None = None,
    ) -> dict[str, Any]:
        """Send a bounded JSON POST request and return a JSON object response."""

        return await self._request_json(
            "POST",
            target,
            path,
            payload=payload,
            headers=headers,
            credentials=credentials,
        )

    async def _get_json(
        self,
        target: Target,
        path: str,
        *,
        credentials: str | None = None,
    ) -> dict[str, Any]:
        """Send a bounded JSON GET request and return a JSON object response."""

        return await self._request_json("GET", target, path, credentials=credentials)

    async def _request_json(
        self,
        method: str,
        target: Target,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        credentials: str | None = None,
    ) -> dict[str, Any]:
        """Send a bounded JSON request and return a JSON object response.

        Every request is pinned to an address that already passed network
        policy, so even a read-only probe such as model discovery cannot be
        used to reach a host the outbound policy forbids.
        """

        resolved_credentials = await self._resolve_credentials(target, credentials)
        request_headers: dict[str, str] = {}
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)
        if resolved_credentials:
            request_headers["Authorization"] = f"Bearer {resolved_credentials}"

        # Pin the connection to an address that already passed network policy.
        # Letting the HTTP client resolve the name again would reopen a DNS
        # rebinding window between validation and connect.
        pinned = self.target_resolver(target.endpoint)
        url = f"{pinned.url.rstrip('/')}{path}"
        request_headers.setdefault("Host", _host_header(pinned))

        # Keep TLS SNI and certificate validation against the real name even
        # though the socket goes to the pinned address.
        extensions = {"sni_hostname": pinned.hostname} if pinned.hostname else None

        try:
            if method == "POST":
                response = await self.client.post(
                    url,
                    json=payload,
                    headers=request_headers,
                    timeout=target.timeout_seconds,
                    follow_redirects=False,
                    extensions=extensions,
                )
            else:
                response = await self.client.get(
                    url,
                    headers=request_headers,
                    timeout=target.timeout_seconds,
                    follow_redirects=False,
                    extensions=extensions,
                )
        except httpx2.TimeoutException as exc:
            raise ModelProviderError("model provider request timed out") from exc
        except httpx2.HTTPError as exc:
            raise ModelProviderError("model provider request failed") from exc

        if response.status_code >= 400:
            raise ModelProviderError(
                f"model provider returned HTTP {response.status_code}",
                provider_status=response.status_code,
            )

        if len(response.content) > self.max_response_bytes:
            raise ModelProviderError("model provider response is too large")

        try:
            body = response.json()
        except ValueError as exc:
            raise ModelProviderError("model provider returned invalid JSON") from exc

        if not isinstance(body, dict):
            raise ModelProviderError("model provider returned an invalid response")
        return body
