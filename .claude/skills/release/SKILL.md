---
name: release
description: Create a release with grouped changelog, summary, and code stats. Use when user wants to make a new release.
model: opus
disable-model-invocation: true
allowed-tools: Read, Edit, Write, Grep, Glob, Bash(git *), Bash(gh *), Bash(grep *), Bash(rm *), Bash(make run-all-checks), Bash(bash bin/set-version.sh *)
---

Choose the release version, set it on `main`, write the release summary and hand both to the `Create Release` workflow (`.github/workflows/create-release.yml`). The workflow never commits to `main`: it refuses a version that differs from `backend/pyproject.toml` on `origin/main`, builds the notes (`bin/release-notes.sh`: the summary, commits grouped by prefix, code stats), fast-forwards `release`, creates the GitHub release and tag, and builds the image (`release.yml`). Between releases `main` stays at the last released version. Deploying stays manual.

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
   If `behind > 0`, abort and ask the user to pull. If `ahead > 0`, record `AHEAD=<ahead>`: the workflow releases `origin/main`, so Step 6 pushes those commits first.
5. If a leftover `release-tmp.md` exists from a previous failed run, delete it
6. Run `make run-all-checks`. It always exits 0, so it passed only if its output ends with `All checks are good`; on `❌ CHECK FAILED`, abort and report the failing gate's output. It also runs the formatters, so run `git status --porcelain` again: if it is not empty, abort — the formatted files are not part of the commit that would be released, and the user must review and commit them first.

If any check fails, abort with a clear error message explaining what's wrong and how to fix it.

## Step 2: Find the latest tag

1. Get the latest version-formatted tag:
   ```
   git tag -l '[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -1
   ```
2. If no commits exist between the tag and HEAD (`git log <tag>..HEAD --oneline` is empty), abort — "No commits to release"

## Step 3: Read the changes for context

1. `git log <tag>..HEAD --format='%s%n%b'` for the commits
2. `git diff <tag>..HEAD -- '*AGENTS.md' docs/game-rules.md` for the architecture notes and the ruleset; the architecture lives in the nested `AGENTS.md` files (`backend/`, `backend/game/` and its `logic/`, `session/`, `messaging/`, `backend/lobby/` and `rooms/`, `frontend/`, `frontend/lobby/`, `frontend/game_v2/`)

## Step 4: Choose the version

A version, or a bump level (`major`, `minor`, `patch`), the user named wins. Otherwise decide from the changes, bumping the latest tag `X.Y.Z`:

* **Minor** (`X.(Y+1).0`) is the default: any new feature a player or operator notices, a ruleset change, an architecture change, a data migration, or a release of more than a handful of commits.
* **Patch** (`X.Y.(Z+1)`) only when the change is too small for a minor: a few bug fixes, small tweaks to existing behaviour, chores, with nothing a player would call new.
* **Major** only when the user asks.

When in doubt, choose minor. Say which level you chose and why in one line of the final report.

Then set it on `main`:

```bash
bash bin/set-version.sh <version>
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore: set version to <version>"
```

When `backend/pyproject.toml` is already at that version, the script changes nothing and `git status --porcelain` stays empty: skip the commit.

## Step 5: Write the summary

Write `release-tmp.md` in the project root with only the summary body: a bulleted list grouped by area (e.g., Architecture, Security, Frontend, Performance, Infrastructure). Each bullet is a bold area label followed by a concise description. Omit areas with no relevant changes. No heading — the workflow adds `# Release <version>` and `## Summary` around it.

## Step 6: Start the workflow

```bash
git push origin main            # when AHEAD > 0 or Step 4 committed the version
gh workflow run create-release.yml --ref main -f version=<version> -F summary=@release-tmp.md
```

For a release too large to list commit by commit (when the user asks, or past roughly a hundred commits), add `-f commits=false`: the notes then carry the summary, the commit count per group and a full-changelog compare link instead of every commit. The summary carries the release's story then, so write it to stand on its own.

It prints the URL of the run it started, ending in `/actions/runs/<run-id>`. Watch that run, never the newest one in `gh run list`, which can be an earlier or concurrent dispatch:
```bash
gh run watch <run-id> --exit-status
```

If it prints no run URL, stop and give the user the workflow's runs page (`https://github.com/<owner>/<repo>/actions/workflows/create-release.yml`, from `gh repo view --json nameWithOwner -q .nameWithOwner`) instead of guessing the run.

If the run fails, report the failing step's log (`gh run view <run-id> --log-failed`) and keep `release-tmp.md`. A failed job is safe to re-run from the run page (`gh run rerun <run-id> --failed`): `release` checks out the current `main` and refuses a version already tagged or one `main` is no longer at, and `build` rebuilds the released commit. A failure in `build` leaves the release published.

## Step 7: Clean up and report

1. Delete `release-tmp.md`
2. Report success: the version and why that level, the GitHub release link (`gh release view <version> --json url -q .url`), the workflow run link, and that deploying is manual — `make -C deploy spot-deploy`
