"""Connection-time outbound enforcement.

Validating a hostname and then letting the HTTP client resolve it again leaves
a time-of-check/time-of-use window: a name that resolves to a public address
during validation can resolve to a private address when the socket opens. That
is DNS rebinding.

These tests cover the pinning behaviour and the encoding forms the roadmap
lists: IPv4 and IPv6 policy, IPv4-mapped IPv6, trailing-dot names, embedded
credentials, metadata hosts, and the rebinding race itself.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

import pytest
from app.security import network as net
from app.security.network import (
    NetworkPolicyError,
    resolve_target,
    validate_target_endpoint,
)


class _FakeGetAddrInfo:
    """Replace socket.getaddrinfo with a scripted sequence of answers."""

    def __init__(self, answers: list[list[str]]) -> None:
        self.answers = answers
        self.calls = 0

    def __call__(self, hostname, port, *args, **kwargs):  # noqa: ANN001
        answer = self.answers[min(self.calls, len(self.answers) - 1)]
        self.calls += 1
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                (ip, port or 0),
            )
            for ip in answer
        ]


@pytest.fixture
def no_local(monkeypatch):
    monkeypatch.setattr(net, "allow_local_targets", False, raising=False)
    return monkeypatch


# --------------------------------------------------------------------- pinning


def test_pinning_uses_a_validated_address(monkeypatch) -> None:
    """The pinned URL must point at an address that passed policy."""

    fake = _FakeGetAddrInfo([["93.184.216.34"]])
    monkeypatch.setattr(net.socket, "getaddrinfo", fake)

    pinned = resolve_target("https://model.example.com/v1", allow_local=False)

    assert pinned.address == "93.184.216.34"
    assert pinned.hostname == "model.example.com"
    # URL carries the literal address, Host/SNI carry the name.
    assert urlsplit(pinned.url).hostname == "93.184.216.34"
    assert pinned.url.startswith("https://93.184.216.34/v1")


def test_pinning_rejects_if_any_resolved_address_is_private(monkeypatch) -> None:
    """A single private answer poisons the name; there is no picking a good one."""

    fake = _FakeGetAddrInfo([["93.184.216.34", "127.0.0.1"]])
    monkeypatch.setattr(net.socket, "getaddrinfo", fake)

    with pytest.raises(NetworkPolicyError):
        resolve_target("https://evil.example.com/v1", allow_local=False)


def test_dns_rebinding_second_lookup_cannot_change_destination(monkeypatch) -> None:
    """The core regression.

    The hostname resolves to a public address during validation and to a
    private one on every later lookup. Because the request is pinned to the
    validated address, the later answer is never consulted for the socket.
    """

    fake = _FakeGetAddrInfo([["93.184.216.34"], ["127.0.0.1"], ["127.0.0.1"]])
    monkeypatch.setattr(net.socket, "getaddrinfo", fake)

    pinned = resolve_target("https://rebind.example.com/v1", allow_local=False)

    # Exactly one lookup happened, and the destination is the public address.
    assert fake.calls == 1
    assert pinned.address == "93.184.216.34"
    assert "127.0.0.1" not in pinned.url


def test_ip_literal_endpoint_is_pinned_to_itself() -> None:
    pinned = resolve_target("https://93.184.216.34/v1", allow_local=False)
    assert pinned.address == "93.184.216.34"
    assert pinned.hostname == "93.184.216.34"


def test_port_is_preserved_when_pinning() -> None:
    pinned = resolve_target("https://93.184.216.34:8443/v1", allow_local=False)
    assert urlsplit(pinned.url).port == 8443


def test_ipv6_address_is_bracketed_when_pinned() -> None:
    """An IPv6 literal must not produce an ambiguous URL."""

    resolved = net._resolved_addresses
    monkey_target = "https://[2606:2800:220:1:248:1893:25c8:1946]/v1"
    try:
        net._resolved_addresses = lambda hostname: [  # type: ignore[assignment]
            ipaddress.ip_address("2606:2800:220:1:248:1893:25c8:1946")
        ]
        pinned = resolve_target(monkey_target, allow_local=False)
    finally:
        net._resolved_addresses = resolved  # type: ignore[assignment]

    assert pinned.address == "2606:2800:220:1:248:1893:25c8:1946"
    assert pinned.url.startswith("https://[2606:")


# ---------------------------------------------------------------- address forms


@pytest.mark.parametrize(
    "address,expected_restricted",
    [
        ("127.0.0.1", True),
        ("10.0.0.5", True),
        ("172.16.4.4", True),
        ("192.168.1.1", True),
        ("169.254.169.254", True),
        ("0.0.0.0", True),
        ("::1", True),
        ("::", True),
        ("fd00::1", True),
        # IPv4-mapped IPv6 must be treated as the IPv4 address it wraps.
        ("::ffff:127.0.0.1", True),
        ("::ffff:169.254.169.254", True),
        ("93.184.216.34", False),
        ("2606:2800:220:1:248:1893:25c8:1946", False),
    ],
)
def test_restricted_address_matrix(address: str, expected_restricted: bool) -> None:
    assert net._is_restricted_address(ipaddress.ip_address(address)) is expected_restricted


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:8080/v1",
        "http://LOCALHOST./v1",
        "http://[::1]:11434/v1",
        "http://169.254.169.254/latest/meta-data",
        "http://metadata.google.internal/computeMetadata/v1/",
        "https://user:password@example.com/v1",
        "ftp://example.com/v1",
    ],
)
def test_blocked_endpoints(endpoint: str) -> None:
    with pytest.raises(NetworkPolicyError):
        validate_target_endpoint(endpoint, allow_local=False)


def test_allow_local_permits_loopback_when_opted_in() -> None:
    """The opt-in still works, which the local-model workflow depends on."""

    assert (
        validate_target_endpoint("http://localhost:11434", allow_local=True)
        == "http://localhost:11434"
    )


def test_allowed_host_pattern_bypasses_address_policy() -> None:
    """An explicit allow-list is honoured, by configuration not by default."""

    allowed_hosts = ["*.trusted.example"]
    assert (
        validate_target_endpoint("https://a.trusted.example/v1", allowed_hosts=allowed_hosts)
        == "https://a.trusted.example/v1"
    )
    with pytest.raises(NetworkPolicyError):
        validate_target_endpoint("https://a.untrusted.example/v1", allowed_hosts=allowed_hosts)


def test_redirects_are_not_followed_by_adapters() -> None:
    """Redirects are the other way policy gets bypassed; confirm the guard."""

    import inspect

    from app.adapters.base import BaseTargetAdapter

    # POST and GET share one transport method, so the redirect guard lives
    # there; confirm it does and that the helpers really delegate to it
    # instead of calling the HTTP client themselves.
    assert "follow_redirects=False" in inspect.getsource(BaseTargetAdapter._request_json)

    for helper in (BaseTargetAdapter._post_json, BaseTargetAdapter._get_json):
        assert "_request_json" in inspect.getsource(helper)
