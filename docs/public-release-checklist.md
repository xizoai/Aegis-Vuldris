# Public Release Checklist

This repository has been developed privately. Changing its visibility to public
publishes the **entire commit history**, not only the current files. Removed
files, deleted branches, old tags, and past pull requests remain reachable.

A clean working tree is not evidence that the history is clean. Complete this
checklist and record the owner, date, and evidence for each item in the release
issue.

> **A cleanup pull request is not a history scrub.** Deleting a private file in
> a normal commit still shows its contents in the pull-request diff and keeps it
> in every earlier commit. Publish from a clean snapshot or rewrite history; do
> not rely on the deletion commit alone.

## 1. Choose the release model

- [ ] Choose one:
  - **Clean snapshot (recommended when the history or pull requests contain
    private notes).** Keep this repository private as the archive and publish a
    fresh repository from the current tree with a single initial commit.
  - **Rewrite this repository's history.** Remove private paths and exposed
    values, then flip visibility. Every commit SHA changes and a force-push is
    required.
- [ ] Confirm the choice with the maintainers. Do not flip visibility while the
      decision is open.

### Clean snapshot

```bash
# Export only tracked files from the current commit.
mkdir ../aegis-public && cd ../aegis-public
git -C <private-repo> archive HEAD | tar -x
git init -b main
git add .
git commit -m "Initial public release"
git remote add origin <public-repo-url>
git push -u origin main
```

The result has no private history. Keep the private repository for internal
notes and archaeology.

### History rewrite

Only use this path if the history itself is safe after rewriting.

- [ ] Make a mirror backup first:

  ```bash
  git clone --mirror <repository-url> aegis-private-backup.git
  ```

- [ ] Rewrite a fresh clone with `git filter-repo`:

  ```bash
  git filter-repo --invert-paths --path <private-path> --path <another-path>
  ```

  Repeat `--path` for each path to remove.

- [ ] Replace exposed values with `--replace-text <expressions-file>`.
- [ ] Re-run every check in sections 2 and 3 against the rewritten clone.
- [ ] Force-push all branches and tags, then ask collaborators to re-clone.
- [ ] Re-open or retarget pull requests that still point at old commits.
- [ ] If the removed material was sensitive, ask GitHub Support to purge cached
      views; old commits can remain reachable by SHA until GitHub garbage
      collects them.

## 2. Audit the current tree

- [ ] Review every tracked file:

  ```bash
  git ls-files
  ```

- [ ] Search for private material:

  ```bash
  git grep -n -I -E 'pricing|revenue|ARR|ICP|TAM|investor|customer|partner|roadmap|TODO|FIXME'
  ```

- [ ] Search for local paths and personal addresses:

  ```bash
  git grep -n -I -E 'C:\\Users|/home/|@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
  ```

- [ ] Inspect screenshots, fixtures, recordings, and demo data for real
      endpoints, credentials, customer names, or model output.
- [ ] Confirm `.env` files and key material are untracked:

  ```bash
  git ls-files | grep -E '(^|/)\.env|id_rsa|\.pem$|\.p12$'
  ```

- [ ] Confirm the README, the documentation index, and packaging metadata only
      reference files that belong in the public tree.
- [ ] Confirm `LICENSE`, `CITATION.cff`, and third-party attributions are
      current.
- [ ] Confirm internal working notes are excluded by `.gitignore` and are not
      tracked.

## 3. Audit the whole history

- [ ] Scan every commit for secrets:

  ```bash
  gitleaks detect --source . --log-opts="--all"
  ```

  TruffleHog is an acceptable alternative.
- [ ] Check author and committer identities:

  ```bash
  git log --all --format='%an <%ae> | %cn <%ce>' | sort -u
  ```

  Personal and agency addresses in commit metadata become public. Use a
  project identity or a GitHub noreply address for the public snapshot;
  `.mailmap` changes display only, not the stored metadata.
- [ ] List every path ever tracked and review the list:

  ```bash
  git log --all --name-only --pretty=format: | sort -u
  ```

- [ ] Check tags, releases, deleted branches, and workflow artifacts for
      private material.
- [ ] Review pull-request diffs and comments, not only commits. A pull request
      that deletes a private file displays that file's contents in its diff.
- [ ] If anything private appears, use the clean-snapshot path or complete the
      history rewrite before proceeding.

## 4. Rotate anything exposed

- [ ] Rotate every credential that was ever committed, even if it has since
      been removed: API keys, database passwords, `SECRET_KEY` values, webhook
      secrets, and tokens.
- [ ] Review GitHub Actions secrets, Dependabot secrets, environment secrets,
      deploy keys, and webhooks.
- [ ] Revoke old tokens and confirm no workflow prints secrets.

## 5. Review GitHub settings

- [ ] Set the repository description, topics, and social preview.
- [ ] Enable private vulnerability reporting under **Settings → Code security**.
- [ ] Enable secret scanning and push protection (free for public
      repositories).
- [ ] Enable Dependabot alerts and security updates; confirm the dependency
      graph is on.
- [ ] Confirm the `dependency-review` workflow can run. It needs the dependency
      graph and, while the repository is private, GitHub Advanced Security;
      both are free for public repositories.
- [ ] Set Actions permissions to read-only by default and grant write access
      only to workflows that need it.
- [ ] Review workflows for `pull_request_target`, untrusted input in `run`
      steps, and self-hosted runners with private network access.
- [ ] Protect `main`: required checks, a required review, and no force-push.
- [ ] Review collaborators, teams, deploy keys, GitHub Apps, environments, and
      webhooks.
- [ ] Review container packages and release assets for baked credentials or
      private files; set package visibility deliberately.
- [ ] Check Pages, releases, and old workflow artifacts for private data.

## 6. Verify from a clean clone

- [ ] Clone the exact tree that will be public into a new directory.
- [ ] Follow the documented quick start end to end:

  ```bash
  docker compose up --build
  docker compose exec backend aegis demo --email you@example.com
  ```

- [ ] Open the UI and confirm the demo project, finding, and evidence render.
- [ ] Run the backend tests, frontend tests, type checks, and production build.
- [ ] Click every link in the README and the documentation index; check images
      and badges.
- [ ] Confirm CI is green on `main`.
- [ ] Confirm GitHub detects the license as Apache-2.0.

## 7. Review the public narrative

- [ ] Every quantitative claim is linked to evidence or a reproducible command
      (for example, the committed judge-calibration recording).
- [ ] The scope and non-goals are accurate: model endpoints only, with agent and
      RAG cases marked experimental.
- [ ] The authorized-use warning and the private vulnerability-reporting path
      are prominent.
- [ ] `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`,
      issue templates, and the pull-request template are current.
- [ ] No links point to private files or a previous repository location.

## 8. Publish

- [ ] Announce the change and confirm nobody is mid-push.
- [ ] Change visibility (or push the clean snapshot) and accept the warning.
- [ ] Verify the repository while logged out: README images and badges,
      documentation links, license, issue templates, and the security advisory
      link.
- [ ] Open a test issue and pull request from an external account if possible.

## 9. After launch

- [ ] Watch the security inbox and new issues.
- [ ] Tag the first public release (`v0.1.0`) and publish release notes.
- [ ] Keep the private archive for internal notes and full history.
- [ ] Re-run this checklist before any future visibility change or repository
      migration.
