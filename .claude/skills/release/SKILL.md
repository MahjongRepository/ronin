---
name: release
description: Create a release with grouped changelog, summary, and code stats. Use when user wants to make a new release.
model: opus
disable-model-invocation: true
allowed-tools: Read, Edit, Write, Grep, Glob, Bash(git *), Bash(gh *), Bash(grep *), Bash(sed *), Bash(wc *), Bash(rm *), Bash(uv lock *), Bash(make run-all-checks), Bash(bash .claude/skills/release/scripts/*)
---

Automate the full release process: generate a grouped changelog with AI summary and code stats, fast-forward the release branch, create a GitHub release with tag, and bump the version for the next cycle. Pushing the release branch starts the image build (`.github/workflows/release.yml`); the skill links that build and stops there — deploying is manual.

## Step 1: Pre-flight checks

Verify all preconditions before starting:

1. Verify on `main` branch: `git branch --show-current` must output `main`
2. Verify working tree is clean: `git status --porcelain` must be empty
3. Verify `gh auth status` succeeds
4. Verify `origin/release` branch exists: `git ls-remote --heads origin release` must return a result
5. Fetch and compare local `main` with `origin/main`:
   ```bash
   git fetch origin --tags --prune
   git rev-list --left-right --count main...origin/main   # "<ahead> <behind>"
   ```
   If `behind > 0`, abort and ask the user to pull. If `ahead > 0`, record `AHEAD=<ahead>`: Step 8 pushes those commits to `main` before the release branch.
6. If a leftover `release-tmp.md` exists from a previous failed run, ask the user for confirmation, then delete it
7. Run `make run-all-checks`. It always exits 0, so it passed only if its output ends with `All checks are good`; on `❌ CHECK FAILED`, abort and report the failing gate's output. It also runs the formatters, so run `git status --porcelain` again: if it is not empty, abort — the formatted files are not part of the commit that would be released, and the user must review and commit them first.

If any check fails, abort with a clear error message explaining what's wrong and how to fix it.

## Step 2: Detect version and latest tag

1. Read the version from `backend/pyproject.toml` (the `version = "X.Y.Z"` line)
2. Validate the version matches `^\d+\.\d+\.\d+$` format — abort with error if not
3. Get the latest version-formatted tag (Step 1 already fetched the tags):
   ```
   git tag -l '[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -1
   ```
4. If the tag equals the version, abort — "Version X.Y.Z was already released"
5. If no commits exist between the tag and HEAD (`git log <tag>..HEAD --oneline` is empty), abort — "No commits to release"
6. Capture the release commit SHA:
   ```
   RELEASE_SHA=$(git rev-parse HEAD)
   ```

## Step 3: Generate grouped commit list

Run the grouping script:
```bash
bash .claude/skills/release/scripts/group-commits.sh <tag>
```

This outputs markdown-formatted sections (Features, Bug Fixes, Maintenance, Other) with original commit messages and links to each commit on GitHub. Save the output for use in Step 6.

## Step 4: Read architecture diffs for context

1. Run `git diff <tag>..HEAD -- '*AGENTS.md' docs/game-rules.md` to get diffs of the architecture notes and the ruleset
2. Read the diffs to understand what changed at a high level
3. The architecture lives in the nested `AGENTS.md` files (`backend/`, `backend/game/` and its `logic/`, `session/`, `messaging/`, `backend/lobby/` and `rooms/`, `frontend/` and its `src/shared/protocol/`, `src/entities/table/`)

Use this context to write the summary in Step 6.

## Step 5: Compute code stats

Run:
```
git diff <tag>..HEAD --shortstat -- ':!*.lock' ':!bun.lock' ':!*.svg'
```

This gives line change stats excluding lock files and SVG assets.

## Step 6: Build release-tmp.md

Write a file `release-tmp.md` in the project root with this structure:

```markdown
# Release <version>

## Summary

<AI-generated bulleted summary grouped by area (e.g., Architecture, Security, Frontend, Performance, Infrastructure). Each bullet is a bold area label followed by a concise one-line description. Omit areas with no relevant changes.>

## Features
- <grouped feat: commits>

## Bug Fixes
- <grouped bug: commits>

## Maintenance
- <grouped chore: commits>

## Other
- <ungrouped commits>

## Stats

- Code changes (lock files and SVG assets excluded): X files changed, Y insertions(+), Z deletions(-)
```

Omit empty sections (e.g., if there are no bug fixes, omit the "Bug Fixes" section entirely).

## Step 7: User review

1. Tell the user to review `release-tmp.md`. With `AHEAD > 0`, also list the unpushed commits (`git log origin/main..main --oneline`) and state that confirming pushes them to `main`.
2. Wait for confirmation before proceeding
3. If the user wants changes, edit the file and re-present

Do NOT proceed until the user explicitly confirms.

## Step 8: Push main and fast-forward release branch

```bash
git push origin main            # only when AHEAD > 0
git push origin main:release
```

The remote rejects a push to `release` that is not a fast-forward. If it does, abort and explain why (likely the release branch has diverged from main).

## Step 9: Create GitHub release and tag

```bash
gh release create <version> --target <RELEASE_SHA> --title "<version>" --notes-file release-tmp.md
```

The `--target` flag pins the tag to the exact commit SHA captured in Step 2, preventing race conditions if other commits are pushed between steps.

## Step 10: Bump version for next cycle

1. Parse current version (e.g., `0.2.0`), increment the minor component → `0.3.0`
2. Edit the version line in `backend/pyproject.toml`, then refresh the lock — without `--upgrade` it only restamps the root package's version and does not move dependency pins:
   ```bash
   uv lock --directory backend
   ```
3. Commit the change (without co-authors) and push it:
   ```bash
   git add backend/pyproject.toml backend/uv.lock && git commit -m "chore: bump version to <new_version>"
   git push origin main
   ```

**Recovery note**: If the skill fails between Steps 9 and 10 (release created but version not bumped), the next run will see the tag matches the version and abort. In that case, manually bump the version in `backend/pyproject.toml`, run `uv lock --directory backend`, commit and push, then the next `/release` invocation will work normally.

## Step 11: Clean up and report

1. Delete `release-tmp.md`:
   ```bash
   rm release-tmp.md
   ```
2. Look up the image build that the Step 8 push started:
   ```bash
   gh run list --workflow=release.yml --branch release --commit <RELEASE_SHA> --limit 1 --json url,status,conclusion
   ```
   If it returns nothing, link the workflow's runs page instead: `https://github.com/<owner>/<repo>/actions/workflows/release.yml` (`gh repo view --json nameWithOwner -q .nameWithOwner`).
3. Report success: the GitHub release link, the build run link with its current status, and that deploying is manual — once the build succeeds, `make -C deploy spot-deploy`
