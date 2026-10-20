# Branch Protection Setup

`main` must not accept a commit that has not passed CI. Branch protection is
configured in repository settings rather than in the repository, so these steps
have to be applied once per repository (and re-applied if settings are reset).

## Required status checks

Set **Settings → Branches → Branch protection rules → Add rule** for `main`.

Enable **Require status checks to pass before merging**, and add exactly these
checks. The names must match the job names in the workflow files or the checks
will never be satisfied and every PR will hang:

- `Backend quality / Lint & format`
- `Backend quality / Type check`
- `Backend quality / Tests`
- `Frontend quality / Lint, typecheck, test, build`
- `Container images / Build & smoke test`

A common failure mode is adding a check name that does not exist. If a PR shows
a check that never reports, the name is wrong — run the workflow once and copy
the exact name from the PR checks list.

## Other recommended settings

| Setting | Value | Why |
|---|---|---|
| Require a pull request before merging | On | Keeps `main` buildable and reviewable |
| Require approvals | 1+ | At least one reviewer; 2 for security-sensitive changes |
| Dismiss stale approvals | On | New pushes re-trigger review |
| Require conversation resolution | On | No unresolved review comments at merge |
| Require branches to be up to date | On | Prevents merging stale, untested commits |
| Require signed commits | On | Attributable, tamper-evident history |
| Require linear history | On | Keeps `git bisect` and reverts predictable |
| Do not allow bypassing the above settings | On | No admin override without intent |
| Restrict deletions | On | `main` cannot be deleted |
| Restrict force pushes | On | History cannot be rewritten |

## Rulesets (recommended over branch protection)

GitHub **Settings → Rules → Rulesets** can express the same policy, plus merge
queue and required linear history, in one place. If you enable both, the more
restrictive applies.

## Verifying the setup

1. Open a pull request with a deliberate lint error. The PR should be blocked.
2. Fix the error. The PR should become mergeable.
3. Confirm the merge button is disabled until all five checks report success.

## Emergency bypass

If production needs an emergency fix, the correct path is still a pull request.
If that is genuinely impossible, disable the rule temporarily via
`gh api` or the settings UI, merge, and re-enable it immediately. Note the
bypass in the incident log.

```bash
# Check the current protection rules
gh api repos/:owner/:repo/branches/main/protection
```
