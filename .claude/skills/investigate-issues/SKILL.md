---
name: investigate-issues
description: Investigate logs for bot and game server to identify root causes of issues. Use when user specifically asks for investigation of issues.
model: opus
allowed-tools: Read, Edit, Write, Grep, Glob, Bash(grep *), Bash(tail *), Bash(cat *), Bash(ls *)
---

## Step 1: Find errors in game and lobby server logs

The local servers write log files only when `LOBBY_LOG_DIR` / `GAME_LOG_DIR` are set (both default to
empty); `.env.local`, which `make run-local-server` sources, points them at `backend/logs/lobby` and
`backend/logs/game`. Grep those directories for errors, limiting output to avoid noise from old logs:
```
grep -r -i -n -E "exception|error|warning|traceback|critical" backend/logs/ | tail -50
```

If the directories are missing or empty, say so instead of treating that as "no errors". Production
logs go to journald on the server, not to files: `make -C deploy spot-check-logs-errors SINCE="1 day ago"`.

## Step 2: Find errors in bot logs

The bot lives in a separate repository (`mahjong-bot`, logs under `project/logs/`). If the user gave
its path or it is checked out next to this repo, grep its logs the same way; otherwise report that
bot logs were not available.

## Step 3: Read full context around errors

For each file and line number found in steps 1-2, use the `Read` tool with `offset` and `limit` to read the full context around the error (at least 50 lines before and after the error line). This ensures complete stack traces are captured, since grep with fixed context lines can truncate them.

## Step 4: Read source code from stack traces

For each source file mentioned in stack traces, use the `Read` tool to examine the relevant code at the line numbers from the traceback. This helps understand what the code was doing when the error occurred.

## Step 5: Correlate and analyze

- Correlate timestamps and game IDs between game server and bot logs to determine if the issue originated on the server side or bot side.
- Identify the root cause based on the full stack traces and source code.
- Summarize findings with potential root causes.

## Step 6: Fix

If there is not enough information in the logs, suggest adding additional logging or monitoring that could help diagnose the issues further.

Once everything was summarized:
1. If the root cause is in the game or lobby server, first reproduce it with a unit test (new or an existing one extended), then fix it.
2. If the root cause is on the bot side, report it with the evidence; change the bot repository only when the user asks for it. The bot's game logic has played thousands of games on tenhou.net, so its ronin client adapter is the likelier suspect, but let the logs decide.
