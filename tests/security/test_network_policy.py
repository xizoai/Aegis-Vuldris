"""Outbound network policy and SSRF protection tests for Aegis Vuldris."""

import pytest
from app.security.network import NetworkPolicyError, validate_target_endpoint


def _bypass_settings(monkeypatch, allow_local: bool = False):
    class _Settings:
        allow_local_targets = allow_local

    monkeypatch.setattr("app.security.network.get_settings", lambda: _Settings())


def test_rejects_unsupported_scheme(monkeypatch):
    _bypass_settings(monkeypatch)
    with pytest.raises(NetworkPolicyError):
        validate_target_endpoint("ftp://example.com")


def test_rejects_file_scheme(monkeypatch):
    _bypass_settings(monkeypatch)
    with pytest.raises(NetworkPolicyError):
        validate_target_endpoint("file:///etc/passwd")


def test_rejects_endpoint_with_credentials(monkeypatch):
    _bypass_settings(monkeypatch)
    with pytest.raises(NetworkPolicyError):
        validate_target_endpoint("https://user:pass@example.com/v1")


def test_rejects_missing_hostname(monkeypatch):
    _bypass_settings(monkeypatch)
    with pytest.raises(NetworkPolicyError):
        validate_target_endpoint("https://")


def test_rejects_loopback_by_default(monkeypatch):
    _bypass_settings(monkeypatch)
    with pytest.raises(NetworkPolicyError):
        validate_target_endpoint("http://127.0.0.1/v1")


def test_rejects_private_ip_by_default(monkeypatch):
    _bypass_settings(monkeypatch)
    with pytest.raises(NetworkPolicyError):
        validate_target_endpoint("http://192.168.1.1/v1")


def test_rejects_metadata_host(monkeypatch):
    _bypass_settings(monkeypatch)
    with pytest.raises(NetworkPolicyError):
        validate_target_endpoint("http://169.254.169.254/latest/meta-data/")


def test_blocks_local_when_enabled(monkeypatch):
    _bypass_settings(monkeypatch, allow_local=True)
    with pytest.raises(NetworkPolicyError):
        validate_target_endpoint("http://169.254.169.254/latest/meta-data/")


def test_allows_private_when_local_enabled(monkeypatch):
    _bypass_settings(monkeypatch, allow_local=True)
    assert (
        validate_target_endpoint("http://192.168.1.1/v1", allow_local=True)
        == "http://192.168.1.1/v1"
    )


def test_allows_explicit_allowed_host(monkeypatch):
    _bypass_settings(monkeypatch)
    assert (
        validate_target_endpoint("http://localhost:8080", allowed_hosts=["localhost"])
        == "http://localhost:8080"
    )
