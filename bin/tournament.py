"""
Run a Ronin online tournament whose registration, seating and results live on the mahjong portal.

The portal's autobot API keeps the tournament's state: it seats each round, writes the notification texts and uploads
every finished game to Pantheon. This script connects it to Ronin and Telegram: it answers ``/me <nickname>`` and
``/status`` in Telegram, posts the portal's notifications to the chat, starts each round's tables through Ronin's
tournament API once their players are online on the tournament page, and hands every finished game's Tenhou XML to the
portal. Once no game it started is still running and the portal's ``end_break_time`` (the games start time for the
first round, the end of the break after the previous one for the others; null for no wait) has passed, it asks the
portal for the next round, which the portal refuses while the round's games are unfinished or no rounds are left.
The run ends with the portal's ``tournament_finished`` notification.

Configuration comes from the environment: PORTAL_URL, PORTAL_API_TOKEN, PORTAL_TOURNAMENT_ID, PORTAL_LOBBY_ID,
RONIN_URL, RONIN_TOURNAMENT_ID, RONIN_API_KEY, and optionally TG_BOT_TOKEN and TG_CHAT_ID (without them Telegram
messages only go to the log).

Usage: uv run --project backend python bin/tournament.py open-registration | close-registration
    | confirm NICKNAME [TELEGRAM_USERNAME] | run
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

POLL_SECONDS = 5.0
ONLINE_TIMEOUT_SECONDS = 300.0
GAME_DEADLINE_SECONDS = 3 * 60 * 60.0
TELEGRAM_LONG_POLL_SECONDS = 25
HTTP_TIMEOUT_SECONDS = TELEGRAM_LONG_POLL_SECONDS + 15.0
TOURNAMENT_FINISHED = "tournament_finished"
TELEGRAM_DESTINATION = 0
GAME_STARTED = 1
GAME_FAILED = 2
PLAYERS_MISSING = 3
COMPLETED = "completed"
NO_ROUND = -1
TOO_MANY_REQUESTS = 429

logger = logging.getLogger("tournament")


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} is not set")

    return value


def is_break_over(end_break_time: str | None) -> bool:
    if end_break_time is None:
        return True

    moment = datetime.fromisoformat(end_break_time)
    return datetime.now(UTC) >= (moment if moment.tzinfo else moment.replace(tzinfo=UTC))


class Portal:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        self._fields = {
            "api_token": env("PORTAL_API_TOKEN"),
            "tournament_id": env("PORTAL_TOURNAMENT_ID"),
            "lobby_id": env("PORTAL_LOBBY_ID"),
        }

    async def call(self, action: str, **fields: object) -> dict:
        response = await self._http.post(
            f"{env('PORTAL_URL').rstrip('/')}/api/v0/autobot/{action}", json={**self._fields, **fields}
        )
        response.raise_for_status()
        answer = response.json()
        logger.info("portal %s %s -> %s", action, json.dumps(fields)[:200], json.dumps(answer, ensure_ascii=False))
        return answer


class Telegram:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        self._token = os.environ.get("TG_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TG_CHAT_ID", "")
        self.enabled = bool(self._token and self.chat_id)

    async def call(self, method: str, payload: dict[str, object]) -> dict:
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        while True:
            response = await self._http.post(url, json=payload)
            answer = response.json()
            retry_after = answer.get("parameters", {}).get("retry_after")
            if answer.get("error_code") != TOO_MANY_REQUESTS or retry_after is None:
                break

            logger.info("telegram %s rate limited, retrying in %ss", method, retry_after)
            await asyncio.sleep(retry_after)

        if not answer.get("ok"):
            logger.warning("telegram %s failed: %s", method, answer)

        return answer

    async def send(self, text: str, chat_id: object = None, reply_to: object = None) -> None:
        logger.info("telegram message: %s", text)
        if not self.enabled:
            return

        message: dict[str, object] = {
            "chat_id": chat_id or self.chat_id,
            "text": text,
            "link_preview_options": {"is_disabled": True},
        }
        if reply_to:
            message["reply_to_message_id"] = reply_to

        answer = await self.call("sendMessage", {**message, "parse_mode": "Markdown"})
        if not answer.get("ok"):
            await self.call("sendMessage", message)

    async def updates(self, offset: int | None) -> list[dict]:
        answer = await self.call(
            "getUpdates",
            {"offset": offset, "timeout": TELEGRAM_LONG_POLL_SECONDS, "allowed_updates": ["message"]},
        )
        return answer.get("result", [])


class Tournament:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.portal = Portal(http)
        self.telegram = Telegram(http)
        self.ronin_url = env("RONIN_URL").rstrip("/")
        self.ronin_tournament = env("RONIN_TOURNAMENT_ID")
        self.ronin_headers = {"X-API-Key": env("RONIN_API_KEY")}
        self.http = http
        self.lock = asyncio.Lock()
        self.online_folded: set[str] = set()
        self.presence_changed = asyncio.Event()
        self.reported: set[str] = set()
        self.pending: dict[str, tuple[int, int, float]] = {}
        self.finished = False

    async def run(self) -> None:
        loops = [self.relay_notifications(), self.follow_events()]
        if self.telegram.enabled:
            loops.append(self.answer_commands())

        async with asyncio.TaskGroup() as group:
            background = [group.create_task(loop) for loop in loops]
            await self.drive_rounds()
            for task in background:
                task.cancel()

    async def relay_notifications(self) -> None:
        while True:
            try:
                await self.drain_notifications()
            except httpx.HTTPError, ValueError:
                logger.exception("relaying notifications failed")

            await asyncio.sleep(POLL_SECONDS)

    async def drain_notifications(self) -> None:
        while notifications := [n for n in (await self.portal.call("check_notifications"))["notifications"] if n]:
            for notification in notifications:
                if notification["destination"] == TELEGRAM_DESTINATION:
                    await self.telegram.send(notification["message"])

                await self.portal.call("process_notification", notification_id=notification["notification_id"])

                if notification["type"] == TOURNAMENT_FINISHED:
                    self.finished = True

    async def answer_commands(self) -> None:
        offset = None
        while True:
            try:
                for update in await self.telegram.updates(offset):
                    offset = update["update_id"] + 1
                    await self.answer(update.get("message") or {})
            except httpx.HTTPError, ValueError:
                logger.exception("telegram update failed")
                await asyncio.sleep(POLL_SECONDS)

    async def answer(self, message: dict) -> None:
        command, _, argument = (message.get("text") or "").partition(" ")
        command = command.split("@")[0]
        if command == "/me":
            answer = await self.portal.call(
                "confirm_player",
                nickname=argument.strip(),
                telegram_username=message.get("from", {}).get("username"),
                lang="ru",
            )
        elif command == "/status":
            answer = await self.portal.call("get_tournament_status", lang="ru")
        else:
            return

        await self.telegram.send(answer["message"], chat_id=message["chat"]["id"], reply_to=message["message_id"])

    async def drive_rounds(self) -> None:
        while not self.finished:
            try:
                await self.reconcile()
                await self.expire_games()
                status = await self.portal.call("get_tournament_status", lang="en")
                if not self.pending and is_break_over(status["end_break_time"]):
                    await self.play_round()
            except httpx.HTTPError, ValueError:
                logger.exception("round step failed")

            await asyncio.sleep(POLL_SECONDS)

    async def play_round(self) -> None:
        prepared = await self.portal.call("prepare_next_round")
        round_number = prepared["round"]
        if round_number == NO_ROUND:
            return

        tables = [[player["ronin_username"] for player in table["players"]] for table in prepared["tables"]]
        await self.wait_online({name.casefold() for table in tables for name in table})

        async with self.lock:
            startable = []
            for number, table in enumerate(tables, start=1):
                missing = [name for name in table if name.casefold() not in self.online_folded]
                if missing:
                    await self.notify_start(round_number, number, PLAYERS_MISSING, missing)
                else:
                    startable.append((number, table))

            results = await self.start_games([table for _, table in startable])
            for (number, table), result in zip(startable, results, strict=True):
                if "game_id" in result:
                    self.pending[result["game_id"]] = (round_number, number, time.monotonic())
                    await self.notify_start(round_number, number, GAME_STARTED)
                else:
                    logger.error("table %d %s did not start: %s", number, table, result)
                    await self.notify_start(round_number, number, GAME_FAILED)

    async def wait_online(self, folded_names: set[str]) -> None:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(ONLINE_TIMEOUT_SECONDS):
                while not folded_names <= self.online_folded:
                    self.presence_changed.clear()
                    await self.presence_changed.wait()

    async def start_games(self, tables: list[list[str]]) -> list[dict]:
        if not tables:
            return []

        response = await self.http.post(
            f"{self.ronin_url}/api/tournaments/{self.ronin_tournament}/games",
            json={"games": tables},
            headers=self.ronin_headers,
        )
        logger.info("ronin start %s -> %s %s", tables, response.status_code, response.text)
        if response.status_code != httpx.codes.OK:
            return [{"error": response.text} for _ in tables]

        return response.json()["results"]

    async def notify_start(self, round_number: int, table: int, kind: int, missing: list[str] | None = None) -> None:
        await self.portal.call(
            "create_start_game_notification",
            tour=round_number,
            table_number=table,
            type=kind,
            missed_players=missing or [],
        )

    async def expire_games(self) -> None:
        now = time.monotonic()
        for game_id, (round_number, table, started) in list(self.pending.items()):
            if now - started > GAME_DEADLINE_SECONDS:
                logger.error("game %s of table %d has no end after %.0fs", game_id, table, GAME_DEADLINE_SECONDS)
                del self.pending[game_id]
                await self.notify_start(round_number, table, GAME_FAILED)

    async def follow_events(self) -> None:
        url = f"{self.ronin_url.replace('http', 'ws', 1)}/ws/tournaments/{self.ronin_tournament}/events"
        while True:
            try:
                async with connect(url, additional_headers=self.ronin_headers) as events:
                    await self.reconcile()
                    async for raw in events:
                        await self.on_event(json.loads(raw))
            except (OSError, WebSocketException, httpx.HTTPError, ValueError) as e:
                logger.warning("events socket lost: %r", e)

            await asyncio.sleep(POLL_SECONDS)

    async def reconcile(self) -> None:
        response = await self.http.get(
            f"{self.ronin_url}/api/tournaments/{self.ronin_tournament}", headers=self.ronin_headers
        )
        response.raise_for_status()
        snapshot = response.json()
        self.online_folded = {name.casefold() for name in snapshot["online"]}
        self.presence_changed.set()
        for game in snapshot["games"]:
            if game["ended_at"] is not None and game["game_id"] not in self.reported:
                await self.finish_game(game["game_id"], game["players"], game["end_reason"], game["ended_at"])

    async def on_event(self, event: dict) -> None:
        logger.info("event %s", json.dumps(event))
        if event["type"] == "presence":
            self.online_folded = {name.casefold() for name in event["players"]}
            self.presence_changed.set()
        elif event["type"] == "game_ended" and event["game_id"] not in self.reported:
            await self.finish_game(event["game_id"], event["players"], event["end_reason"], time.time())

    async def finish_game(self, game_id: str, players: list[str], end_reason: str, ended_at: float) -> None:
        self.reported.add(game_id)
        if end_reason != COMPLETED:
            await self.telegram.send(f"Game {game_id} ({', '.join(players)}) ended as {end_reason}, not added.")
            self.pending.pop(game_id, None)
            return

        try:
            response = await self.http.get(f"{self.ronin_url}/api/replays/{game_id}/tenhou.xml")
            response.raise_for_status()
            async with self.lock:
                answer = await self.portal.call(
                    "game_finish",
                    log_id=game_id,
                    players=players,
                    log_content=response.text,
                    log_time=int(ended_at),
                    lang="ru",
                )
        except httpx.HTTPError, ValueError:
            logger.exception("reporting game %s failed", game_id)
            self.reported.discard(game_id)
            return

        if answer.get("added") is not True:
            logger.error("the portal did not add game %s: %s", game_id, answer.get("message"))
            self.reported.discard(game_id)
            return

        self.pending.pop(game_id, None)


async def admin(command: argparse.Namespace) -> None:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
        portal = Portal(http)
        if command.command == "open-registration":
            await portal.call("open_registration")
        elif command.command == "close-registration":
            await portal.call("close_registration")
        elif command.command == "confirm":
            contact = {"telegram_username": command.telegram_username} if command.telegram_username else {}
            answer = await portal.call("admin_confirm_player", nickname=command.nickname, **contact)
            if answer.get("confirmed") is not True:
                sys.exit(f"the portal refused to confirm {command.nickname}: {answer['message']}")
        else:
            await Tournament(http).run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Ronin online tournament for the mahjong portal.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("open-registration", help="open the portal's confirmation stage")
    commands.add_parser("close-registration", help="close the portal's confirmation stage")
    confirm = commands.add_parser("confirm", help="confirm a registered player as the admin")
    confirm.add_argument("nickname", help="the player's Ronin nickname")
    confirm.add_argument("telegram_username", nargs="?", help="the player's Telegram username, if any")
    commands.add_parser("run", help="play the tournament's rounds until the portal says it is finished")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(admin(parser.parse_args()))


if __name__ == "__main__":
    main()
