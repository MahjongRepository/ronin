---
name: release
description: Create a release with grouped changelog, summary, and code stats. Use when user wants to make a new release.
model: opus
disable-model-invocation: true
allowed-tools: Read, Edit, Write, Grep, Glob, Bash(git *), Bash(gh *), Bash(grep *), Bash(rm *), Bash(make run-all-checks)
---

Write the release summary and hand it, with the version, to the `Create Release` workflow (`.github/workflows/create-release.yml`). The workflow does the rest on `origin/main`: it sets the version if it differs from `backend/pyproject.toml`, builds the notes (`bin/release-notes.sh`: the summary, commits grouped by prefix, code stats), fast-forwards `release`, creates the GitHub release and tag, bumps the version to the next minor, and builds the image (`release.yml`). Deploying stays manual.

Run every step through to the end without asking the user for confirmation; stop only when a check fails.

## Step 1: Pre-flight checks

Verify all preconditions before starting:

1. Verify on `main` branch: `git branch --show-current` must output `main`
2. Verify working tree is clean: `git status --porcelain` must be empty
3. Verify `gh auth status` succeeds
4. Fetch and compare local `main` with `origin/main`:
   ```bash
   git fetch origin --tags --prune
   git rev-list --left-right --count main...origin/main   # "<ahead> <behind>"
   ```
   If `behind > 0`, abort and ask the user to pull. If `ahead > 0`, record `AHEAD=<ahead>`: the workflow releases `origin/main`, so Step 5 pushes those commits first.
5. If a leftover `release-tmp.md` exists from a previous failed run, delete it
6. Run `make run-all-checks`. It always exits 0, so it passed only if its output ends with `All checks are good`; on `❌ CHECK FAILED`, abort and report the failing gate's output. It also runs the formatters, so run `git status --porcelain` again: if it is not empty, abort — the formatted files are not part of the commit that would be released, and the user must review and commit them first.

If any check fails, abort with a clear error message explaining what's wrong and how to fix it.

## Step 2: Detect version and latest tag

1. Read the version from `backend/pyproject.toml` (the `version = "X.Y.Z"` line). Release that version unless the user named another one.
2. Get the latest version-formatted tag:
   ```
   git tag -l '[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -1
   ```
3. If the tag equals the version, abort — "Version X.Y.Z was already released"
4. If no commits exist between the tag and HEAD (`git log <tag>..HEAD --oneline` is empty), abort — "No commits to release"

The workflow repeats these checks, so they only fail early here.

## Step 3: Read the changes for context

1. `git log <tag>..HEAD --format='%s%n%b'` for the commits
2. `git diff <tag>..HEAD -- '*AGENTS.md' docs/game-rules.md` for the architecture notes and the ruleset; the architecture lives in the nested `AGENTS.md` files (`backend/`, `backend/game/` and its `logic/`, `session/`, `messaging/`, `backend/lobby/` and `rooms/`, `frontend/`, `frontend/lobby/`, `frontend/game/`)

## Step 4: Write the summary

Write `release-tmp.md` in the project root with only the summary body: a bulleted list grouped by area (e.g., Architecture, Security, Frontend, Performance, Infrastructure). Each bullet is a bold area label followed by a concise description. Omit areas with no relevant changes. No heading — the workflow adds `# Release <version>` and `## Summary` around it.

## Step 5: Start the workflow

```bash
git push origin main            # only when AHEAD > 0
gh workflow run create-release.yml --ref main -f version=<version> -F summary=@release-tmp.md
```

It prints the URL of the run it started, ending in `/actions/runs/<run-id>`. Watch that run, never the newest one in `gh run list`, which can be an earlier or concurrent dispatch:
```bash
gh run watch <run-id> --exit-status
```

If it prints no run URL, stop and give the user the workflow's runs page (`https://github.com/<owner>/<repo>/actions/workflows/create-release.yml`, from `gh repo view --json nameWithOwner -q .nameWithOwner`) instead of guessing the run.

If the run fails, report the failing step's log (`gh run view <run-id> --log-failed`) and keep `release-tmp.md`. A failed job is safe to re-run from the run page (`gh run rerun <run-id> --failed`): `release` checks out the current `main` and refuses a version already tagged, `bump` skips a bump already on `main` and refuses one that a newer release has overtaken, and `build` rebuilds the released commit. A failure in `bump` or `build` leaves the release published.

## Step 6: Clean up and report

1. Delete `release-tmp.md`
2. Run `git pull --ff-only` so local `main` has the version bump
3. Report success: the GitHub release link (`gh release view <version> --json url -q .url`), the workflow run link, and that deploying is manual — `make -C deploy spot-deploy`
