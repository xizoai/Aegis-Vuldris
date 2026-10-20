"""Model adapter registry and exports."""

from typing import Any

from app.adapters.custom_rest import CustomRESTAdapter, CustomRESTConfig
from app.adapters.errors import UnknownProviderError
from app.adapters.ollama import OllamaAdapter
from app.adapters.openai_compatible import OpenAICompatibleAdapter
from app.models.model import ModelRequest, ModelResponse
from app.models.target import TargetProvider

ModelAdapter = Any


class AdapterRegistry:
    """Select a model adapter by provider type.

    Third-party factories (discovered through the ``aegis.adapters``
    entry-point group) can override the built-in adapter for a provider value;
    they are consulted before the static registrations so an operator can
    substitute an instrumented adapter without forking the registry.
    """

    def __init__(
        self,
        *,
        client: Any | None = None,
        credential_resolver: Any | None = None,
    ) -> None:
        self.client = client
        self.credential_resolver = credential_resolver
        self._overrides: dict[str, Any] = {}

    def register_override(self, provider_value: str, factory: Any) -> None:
        """Register a third-party factory for an existing provider value."""

        if not provider_value:
            raise ValueError("provider value must not be empty")
        if not callable(factory):
            raise ValueError("factory must be callable")
        self._overrides[provider_value] = factory

    def create(
        self,
        provider: TargetProvider,
        *,
        config: CustomRESTConfig | None = None,
    ) -> ModelAdapter:
        """Create an adapter without accepting runtime import paths."""

        override = self._overrides.get(provider.value)
        if override is not None:
            return override(credential_resolver=self.credential_resolver, client=self.client)
        if provider == TargetProvider.OPENAI_COMPATIBLE:
            return OpenAICompatibleAdapter(
                client=self.client,
                credential_resolver=self.credential_resolver,
            )
        if provider == TargetProvider.OLLAMA:
            return OllamaAdapter(
                client=self.client,
                credential_resolver=self.credential_resolver,
            )
        if provider == TargetProvider.CUSTOM_REST:
            return CustomRESTAdapter(
                client=self.client,
                credential_resolver=self.credential_resolver,
                config=config,
            )
        raise UnknownProviderError(f"unsupported model provider: {provider.value}")


def create_model_adapter(
    provider: TargetProvider,
    *,
    client: Any | None = None,
    credential_resolver: Any | None = None,
    config: CustomRESTConfig | None = None,
) -> ModelAdapter:
    """Create a provider adapter through the static registry."""

    return AdapterRegistry(
        client=client,
        credential_resolver=credential_resolver,
    ).create(provider, config=config)


__all__ = [
    "AdapterRegistry",
    "CustomRESTAdapter",
    "CustomRESTConfig",
    "ModelAdapter",
    "ModelRequest",
    "ModelResponse",
    "OllamaAdapter",
    "OpenAICompatibleAdapter",
    "create_model_adapter",
]
