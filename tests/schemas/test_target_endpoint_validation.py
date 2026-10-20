"""Endpoint base-URL validation.

Aegis Vuldris appends a provider-specific path to the configured endpoint. An
endpoint that already ends with that path produces a doubled URL and an opaque
HTTP 404 at run time, so it is rejected when the target is created or updated.
"""

import pytest
from app.models.target import TargetProvider
from app.schemas import TargetCreate, TargetUpdate

ATTEST = {"authorization_attestation": True}


def _create(**overrides) -> TargetCreate:
    payload = {
        "project_id": "00000000-0000-0000-0000-000000000001",
        "name": "Example",
        "provider": TargetProvider.OPENAI_COMPATIBLE,
        "endpoint": "https://api.example.com/v1",
        "model": "test-model",
        **ATTEST,
    }
    payload.update(overrides)
    return TargetCreate(**payload)


class TestAcceptsValidBaseUrls:
    @pytest.mark.parametrize(
        "endpoint",
        [
            "https://api.openai.com/v1",
            "https://api.groq.com/openai/v1",
            "https://openrouter.ai/api/v1",
            "https://openrouter.ai/api/v1",
            "https://api.example.com",
            "https://api.example.com/v1/",
            "http://host.docker.internal:8000/v1",
        ],
    )
    def test_openai_compatible_base_urls(self, endpoint: str) -> None:
        assert _create(endpoint=endpoint).endpoint == endpoint

    def test_ollama_base_url(self) -> None:
        target = _create(
            provider=TargetProvider.OLLAMA,
            endpoint="http://aegis-ollama:11434",
            model="qwen2.5:1.5b",
        )
        assert target.endpoint == "http://aegis-ollama:11434"

    def test_custom_rest_is_not_path_checked(self) -> None:
        """custom_rest appends nothing by default, so the rule does not apply."""

        target = _create(
            provider=TargetProvider.CUSTOM_REST,
            endpoint="https://api.example.com/v1/chat/completions",
            model=None,
        )
        assert target.endpoint.endswith("/chat/completions")

    def test_path_merely_containing_chat_is_fine(self) -> None:
        """A base like /openai/v1 is a normal vendor path, not a mistake."""

        assert _create(endpoint="https://api.groq.com/openai/v1").endpoint


class TestRejectsFullRequestPaths:
    @pytest.mark.parametrize(
        "endpoint",
        [
            "https://openrouter.ai/api/v1/chat/completions",
            "https://openrouter.ai/api/v1/chat/completions/",
            "https://api.openai.com/v1/chat/completions",
        ],
    )
    def test_openai_compatible_full_path_rejected(self, endpoint: str) -> None:
        with pytest.raises(ValueError, match="base URL"):
            _create(endpoint=endpoint)

    def test_ollama_full_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="base URL"):
            _create(
                provider=TargetProvider.OLLAMA,
                endpoint="http://aegis-ollama:11434/api/chat",
                model="qwen2.5:1.5b",
            )

    def test_error_explains_the_appended_path(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            _create(endpoint="https://openrouter.ai/api/v1/chat/completions")
        message = str(excinfo.value)
        assert "/chat/completions" in message
        assert "base URL" in message
        # The message must show a usable example, not just name the problem.
        assert "https://api.example.com/v1" in message

    def test_real_world_mistake_is_caught(self) -> None:
        """The exact shape that produced HTTP 404s for a real user."""

        with pytest.raises(ValueError, match="base URL"):
            _create(
                provider=TargetProvider.OLLAMA,
                endpoint="https://openrouter.ai/api/v1/chat/completions",
                model="NVIDIA: Nemotron",
            )


class TestUpdateValidation:
    def test_update_rejects_full_path_when_provider_supplied(self) -> None:
        with pytest.raises(ValueError, match="base URL"):
            TargetUpdate(
                provider=TargetProvider.OPENAI_COMPATIBLE,
                endpoint="https://api.example.com/v1/chat/completions",
            )

    def test_update_rejects_full_path_for_ollama(self) -> None:
        with pytest.raises(ValueError, match="base URL"):
            TargetUpdate(
                provider=TargetProvider.OLLAMA,
                endpoint="http://host:11434/api/chat",
            )

    def test_update_accepts_valid_base_url(self) -> None:
        update = TargetUpdate(
            provider=TargetProvider.OPENAI_COMPATIBLE,
            endpoint="https://openrouter.ai/api/v1",
        )
        assert update.endpoint == "https://openrouter.ai/api/v1"

    def test_update_endpoint_only_is_accepted(self) -> None:
        """Provider may be unchanged, so a lone endpoint cannot be validated."""

        assert TargetUpdate(endpoint="https://api.example.com/v1").endpoint


class TestRejectsRestrictedAddressLiterals:
    """A literal loopback/private/link-local address can never pass the
    connection-time policy, so it is refused when the target is configured
    rather than only when a run is attempted. Hostnames are still validated at
    connection time by ``resolve_target``.
    """

    @pytest.mark.parametrize(
        "endpoint",
        [
            "http://127.0.0.1:11434",
            "http://10.0.0.5:8000/v1",
            "http://192.168.1.10:8000",
            "http://169.254.169.254/latest/meta-data",
            "http://[::1]:8000/v1",
        ],
    )
    def test_create_rejects_restricted_literals(self, endpoint: str) -> None:
        with pytest.raises(ValueError, match="not permitted"):
            _create(endpoint=endpoint)

    def test_update_rejects_restricted_literal(self) -> None:
        with pytest.raises(ValueError, match="not permitted"):
            TargetUpdate(
                provider=TargetProvider.OPENAI_COMPATIBLE,
                endpoint="http://127.0.0.1:11434",
            )

    def test_hostnames_are_still_deferred_to_run_time(self) -> None:
        """A hostname is not resolved on the request path (no DNS on create)."""

        assert _create(endpoint="http://aegis-ollama:11434", model="x").endpoint

    def test_public_literal_is_accepted(self) -> None:
        # 192.0.2.1 is documentation space, outside the blocked private ranges.
        assert _create(endpoint="https://192.0.2.1/v1").endpoint
