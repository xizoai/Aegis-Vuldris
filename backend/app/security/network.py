"""Outbound network policy and SSRF protection for Aegis Vuldris.

User-configured target endpoints are untrusted input. Before any outbound
target connection is established, the endpoint is parsed, its scheme is
validated, embedded credentials are rejected, the hostname is resolved, and
every resolved address is checked against an allow/deny policy.

Resolving and validating is not sufficient on its own. A name that resolves
to a public address during validation can resolve to a private address when
the connection is actually made, which is DNS rebinding. Validation alone
therefore leaves a time-of-check/time-of-use window.

The connection is pinned instead: the hostname is resolved once, every
address is checked, and the request is sent to one of the validated addresses
by IP literal. The original hostname is preserved in the ``Host`` header and
in TLS SNI, so virtual hosting and certificate validation still work, but the
socket can only ever be opened to an address that already passed policy.

Model adapters also disable automatic redirects, so policy cannot be bypassed
by redirection.
"""

import ipaddress
import socket
from dataclasses import dataclass
from fnmatch import fnmatch
from urllib.parse import urlsplit, urlunsplit

from app.core.config import get_settings


class NetworkPolicyError(ValueError):
    """Raised when a target endpoint violates outbound network policy."""


_LINK_LOCAL_CIDR = ipaddress.ip_network("169.254.0.0/16")
_LOOPBACK_CIDR = ipaddress.ip_network("127.0.0.0/8")
_PRIVATE_CIDRS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]
_METADATA_HOSTS = {"metadata.google.internal", "169.254.169.254"}


def _is_restricted_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return True
    if ip.version == 4:
        if ip in _LINK_LOCAL_CIDR:
            return True
        return any(ip in cidr for cidr in _PRIVATE_CIDRS)
    if ip.version == 6:
        if ip == ipaddress.ip_address("::1"):
            return True
        return ip.is_link_local or ip.is_private
    return True


def _resolved_addresses(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise NetworkPolicyError(f"target hostname could not be resolved: {hostname}") from exc
    resolved: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address not in resolved:
            resolved.append(address)
    return resolved


def _validate_endpoint_shape(endpoint: str):
    """Validate everything about an endpoint that does not require DNS."""

    parsed = urlsplit(endpoint)

    if parsed.scheme not in {"http", "https"}:
        raise NetworkPolicyError("target endpoint must use an http or https scheme")
    if not parsed.hostname:
        raise NetworkPolicyError("target endpoint must include a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise NetworkPolicyError("target endpoint must not contain credentials")

    if (parsed.hostname or "").lower() in _METADATA_HOSTS:
        raise NetworkPolicyError("cloud metadata endpoints are not permitted")

    return parsed


def validate_target_endpoint(
    endpoint: str,
    *,
    allow_local: bool | None = None,
    allowed_hosts: list[str] | None = None,
) -> str:
    """Validate a user-configured target endpoint against outbound policy.

    Returns the validated endpoint URL. Raises NetworkPolicyError when the
    endpoint violates scheme, credential, host, or address policy.

    This resolves DNS once for validation only. It is the right check for
    configuration time; anything that then opens a socket must use
    :func:`resolve_target` instead so the address cannot change in between.
    """

    parsed = _validate_endpoint_shape(endpoint)
    hostname = parsed.hostname or ""

    if allowed_hosts and any(fnmatch(hostname, pattern) for pattern in allowed_hosts):
        return endpoint

    if allow_local is None:
        allow_local = get_settings().allow_local_targets

    if _is_ip_literal(hostname):
        candidate = ipaddress.ip_address(hostname)
        if _is_restricted_address(candidate) and not allow_local:
            raise NetworkPolicyError("local and private target addresses are not permitted")
        return endpoint

    for ip in _resolved_addresses(hostname):
        if _is_restricted_address(ip) and not allow_local:
            raise NetworkPolicyError(f"resolved target address {ip} is not permitted")

    return endpoint


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def is_restricted_endpoint_literal(endpoint: str) -> bool:
    """Return whether the endpoint host is a restricted IP literal.

    This is deliberately DNS-free so it is safe to call on the request path
    when a target is created or updated. A literal loopback, private,
    link-local, or otherwise restricted address can never pass the
    connection-time policy, so refusing it early fails fast instead of storing
    a target that silently cannot run. Hostnames are left to
    :func:`resolve_target` at connection time, which resolves and pins them.
    """

    hostname = urlsplit(endpoint).hostname or ""
    if not _is_ip_literal(hostname):
        return False
    return _is_restricted_address(ipaddress.ip_address(hostname))


@dataclass(frozen=True)
class PinnedTarget:
    """A validated destination that can be connected to without re-resolving.

    ``url`` points at a literal address that already passed policy. ``hostname``
    is the original name, which must be sent in the ``Host`` header and used for
    TLS SNI so virtual hosting and certificate validation behave normally.
    """

    url: str
    hostname: str
    address: str


def _endpoint_with_address(endpoint: str, address: str) -> str:
    """Return ``endpoint`` with its host replaced by a literal address."""

    parsed = urlsplit(endpoint)
    if parsed.port is not None:
        netloc = f"[{address}]:{parsed.port}" if ":" in address else f"{address}:{parsed.port}"
    else:
        netloc = f"[{address}]" if ":" in address else address
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def resolve_target(
    endpoint: str,
    *,
    allow_local: bool | None = None,
    allowed_hosts: list[str] | None = None,
) -> PinnedTarget:
    """Validate an endpoint and pin the connection to an approved address.

    This is the connection-time control, and it resolves the hostname exactly
    once. The single answer is validated and then used for the socket, so there
    is no window in which a later DNS answer could send the connection
    somewhere else.

    Note that this deliberately does not call ``validate_target_endpoint``:
    doing so would resolve once for validation and again here, reintroducing the
    very race this function exists to close.
    """

    parsed = _validate_endpoint_shape(endpoint)
    hostname = parsed.hostname or ""

    if allow_local is None:
        allow_local = get_settings().allow_local_targets

    if _is_ip_literal(hostname):
        address = hostname
        if _is_restricted_address(ipaddress.ip_address(address)) and not allow_local:
            raise NetworkPolicyError("local and private target addresses are not permitted")
    else:
        # Resolve once. If *any* answer is restricted the whole name is refused
        # rather than quietly using a favourable one. A hostname that mixes
        # public and private answers is itself suspicious, and failing closed
        # keeps this function safe even if pinning is ever weakened.
        answers = _resolved_addresses(hostname)
        if not allow_local:
            for ip in answers:
                if _is_restricted_address(ip):
                    raise NetworkPolicyError(f"resolved target address {ip} is not permitted")
        if not answers:
            raise NetworkPolicyError(f"no permitted address for target hostname: {hostname}")
        address = str(answers[0])

    return PinnedTarget(
        url=_endpoint_with_address(endpoint, address),
        hostname=hostname,
        address=address,
    )
