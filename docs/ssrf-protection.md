# Outbound Network Policy and SSRF Protection

Aegis Vuldris connects outbound to AI model endpoints that users configure. Those
endpoints are untrusted input, so every connection is treated as a potential
server-side request forgery (SSRF) vector against the host running Aegis Vuldris.

This document describes the enforced policy, why it works, and what remains
open.

## Threat model

A user who can create a target can supply any URL. If Aegis Vuldris fetched it
without controls, they could:

- reach cloud metadata endpoints (`169.254.169.254`) to steal instance
  credentials;
- reach loopback and private services (databases, admin panels, the Docker
  network) that are not exposed to the Internet;
- use the server as a proxy to scan or attack internal infrastructure.

## Enforcement: resolve once, pin the socket

Validation alone is not sufficient. A hostname can resolve to a public address
during validation and to a private address a moment later when the connection
is actually opened. That is DNS rebinding, and it is a time-of-check /
time-of-use race.

Aegis Vuldris therefore does not hand the hostname to the HTTP client at all:

1. Parse the endpoint. Reject non-HTTP(S) schemes, embedded credentials, and
   known metadata hosts.
2. Resolve the hostname **exactly once**.
3. Check **every** returned address against the deny policy. If any address is
   restricted, the whole name is refused — a name that mixes public and private
   answers is itself suspicious.
4. Send the request to one of the validated addresses **by IP literal**.
5. Preserve the original hostname in the `Host` header and in TLS SNI
   (`sni_hostname`), so virtual hosting and certificate validation still work.

Because the socket can only be opened to an address that already passed
policy, a later DNS answer cannot change where the connection goes.

This is implemented in `resolve_target()` in
`backend/app/security/network.py` and applied in
`BaseTargetAdapter._post_json()`.

## Denied by default

| Category | Examples |
|---|---|
| Loopback | `127.0.0.0/8`, `::1` |
| Private | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, IPv6 ULA `fc00::/7` |
| Link-local | `169.254.0.0/16`, `fe80::/10` |
| Metadata | `169.254.169.254`, `metadata.google.internal` |
| Unspecified / multicast | `0.0.0.0`, `::`, multicast ranges |
| IPv4-mapped IPv6 | `::ffff:127.0.0.1` is treated as `127.0.0.1` |

Redirects are not followed (`follow_redirects=False`), so a permitted endpoint
cannot bounce the request to a blocked one.

## Opt-ins

| Setting | Effect |
|---|---|
| `ALLOW_LOCAL_TARGETS=true` | Permits loopback and private addresses. Required to test a model running on the same host. |
| `allowed_hosts` (parameter) | Glob patterns that bypass address policy, e.g. `*.trusted.example`. Still pinned. |

Both are opt-in. The default denies everything above.

## Residual risks

This control is necessary but not sufficient, and the following remain:

1. **Post-resolution reachability is not re-checked.** An approved public
   address could later be reassigned, or the host could be moved behind NAT to
   something internal. Pinning prevents DNS rebinding; it cannot prevent a
   network change under a stable address.

2. **Defence in depth is deployment-specific.** Blocking egress to private
   ranges at the container or host firewall layer would catch the case where
   application logic is bypassed. The production Compose file relies on an
   internal Docker network; adding host-level egress rules is recommended and
   is not yet implemented.

3. **An egress proxy would be stronger.** Routing all outbound traffic through a
   proxy that enforces policy at connect time centralises the control and makes
   it auditable. Not implemented; it adds infrastructure.

4. **The target itself is trusted after admission.** Once an endpoint is
   allowed, Aegis Vuldris will send it the attack prompts. That is the product's
   purpose, and the authorization attestation is what records the operator's
   claim to be permitted to do so.

## Verifying the control

```powershell
pytest tests/security/test_network_pinning.py
```

Covers pinning, the rebinding race, IPv4 and IPv6 policy matrices,
IPv4-mapped addresses, trailing-dot hostnames, embedded credentials, metadata
hosts, and the allow-list and `ALLOW_LOCAL_TARGETS` opt-ins.
