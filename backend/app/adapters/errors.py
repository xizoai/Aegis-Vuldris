"""Normalized errors raised by model adapters."""


class ModelAdapterError(RuntimeError):
    """Base error for adapter and provider failures."""

    code = "MODEL_ADAPTER_ERROR"
    status_code = 502

    def __init__(self, message: str, *, provider_status: int | None = None) -> None:
        super().__init__(message)
        # HTTP status the model provider itself returned, when known. This is
        # distinct from ``status_code``, which is the HTTP status this API
        # responds with when the error reaches a request handler.
        self.provider_status = provider_status


class UnknownProviderError(ModelAdapterError):
    """Raised when an adapter registry receives an unsupported provider."""

    code = "UNKNOWN_PROVIDER"


class TargetConfigurationError(ModelAdapterError):
    """Raised when a target cannot be used by an adapter."""

    code = "TARGET_CONFIGURATION_ERROR"


class ModelProviderError(ModelAdapterError):
    """Raised when a provider returns an invalid or unsuccessful response."""

    code = "MODEL_PROVIDER_ERROR"
