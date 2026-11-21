"""
Play an external tournament manager against a running lobby: wait for the players, start their games, follow them.

Connect the tournament's events socket, wait until every given player is online, shuffle them into tables of four and
start those through the tournament API, then wait for a ``game_started`` and a ``game_ended`` of every started game
and read the snapshot. Every API response and every event goes to the log. Exits 1 when a table fails to start, a
``game_started`` names other players or another order than submitted, a game does not end as completed, its
``game_ended`` seats do not hold the table in submitted turn order (each player one engine seat after the one before;
the event names no dealer, so which seat is East is not checked), the snapshot read fails, or a deadline passes.

Usage: uv run --project backend/lobby python bin/tournament_manager.py --lobby-url URL --tournament ID --api-key KEY
    --log PATH <player>...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from websockets.asyncio.client import connect

if TYPE_CHECKING:
    from websockets.asyncio.client import ClientConnection

TABLE_SIZE = 4
ONLINE_TIMEOUT_SECONDS = 60.0
GAMES_TIMEOUT_SECONDS = 900.0
COMPLETED = "completed"

logger = logging.getLogger("tournament_manager")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start and follow a tournament's games as its external manager.")
    parser.add_argument("--lobby-url", required=True)
    parser.add_argument("--tournament", required=True, help="the tournament id")
    parser.add_argument("--api-key", required=True, help="the tournament owner's API token")
    parser.add_argument("--log", required=True, type=Path, help="the file every response and event is written to")
    parser.add_argument("players", nargs="+", help=f"the usernames to seat, a multiple of {TABLE_SIZE}")
    args = parser.parse_args()
    if len(args.players) % TABLE_SIZE:
        parser.error(f"{len(args.players)} players do not fill tables of {TABLE_SIZE}")

    return args


def set_up_logging(log_path: Path) -> None:
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(log_path)):
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)


async def receive_event(events: ClientConnection) -> dict[str, object]:
    event = json.loads(await events.recv())
    logger.info("event %s", json.dumps(event))
    return event


async def wait_until_online(events: ClientConnection, players: list[str]) -> None:
    async with asyncio.timeout(ONLINE_TIMEOUT_SECONDS):
        while True:
            event = await receive_event(events)
            if event["type"] == "presence" and set(players) <= set(event["players"]):
                return


def seat_tables(players: list[str]) -> list[list[str]]:
    shuffled = random.sample(players, k=len(players))
    return [shuffled[start : start + TABLE_SIZE] for start in range(0, len(shuffled), TABLE_SIZE)]


async def start_games(http: httpx.AsyncClient, tournament_id: str, tables: list[list[str]]) -> dict[str, list[str]]:
    """
    Submit the tables and return each started game's id with its submitted players; empty when any table failed.
    """
    logger.info("submit tables (East, South, West, North) %s", json.dumps(tables))
    response = await http.post(f"/api/tournaments/{tournament_id}/games", json={"games": tables})
    logger.info("POST /api/tournaments/%s/games -> %s %s", tournament_id, response.status_code, response.text)
    if response.status_code != httpx.codes.OK:
        return {}

    results = response.json()["results"]
    if any("game_id" not in result for result in results):
        logger.error("a table did not start")
        return {}

    return {result["game_id"]: table for result, table in zip(results, tables, strict=True)}


def check_started(event: dict[str, object], submitted: dict[str, list[str]]) -> bool:
    game_id = event["game_id"]
    if submitted.get(game_id) != event["players"]:
        logger.error("game %s started as %s, submitted %s", game_id, event["players"], submitted.get(game_id))
        return False

    logger.info("game %s started with the submitted table %s", game_id, event["players"])
    return True


def check_seating(event: dict[str, object], table: list[str]) -> bool:
    """
    Return whether the game's engine seats hold the table in submitted turn order, each player one seat after the one
    before; whether the first sits at the dealer seat is not checked, as the event names no dealer.
    """
    seats = {entry["name"]: entry["seat"] for entry in event["result"]}
    east_seat = seats[table[0]]
    expected = {name: (east_seat + wind) % TABLE_SIZE for wind, name in enumerate(table)}
    if seats != expected:
        logger.error("game %s seated %s, the submitted table needs %s", event["game_id"], seats, expected)
        return False

    logger.info("game %s seated in submitted turn order, engine seats %s", event["game_id"], seats)
    return True


async def follow_games(events: ClientConnection, submitted: dict[str, list[str]]) -> bool:
    """
    Wait for a game_started and a game_ended of every submitted game; return whether all matched, completed and kept
    the submitted seating.
    """
    started: dict[str, bool] = {}
    ended: dict[str, bool] = {}
    async with asyncio.timeout(GAMES_TIMEOUT_SECONDS):
        while set(ended) != set(submitted):
            event = await receive_event(events)
            if event["type"] == "game_started":
                started[event["game_id"]] = check_started(event, submitted)
            elif event["type"] == "game_ended" and event["game_id"] in submitted:
                completed = event["end_reason"] == COMPLETED
                ended[event["game_id"]] = completed and check_seating(event, submitted[event["game_id"]])

    all_started = all(started.get(game_id, False) for game_id in submitted)
    logger.info("games ended completed and seated in submitted turn order: %s", json.dumps(ended))
    return all_started and all(ended.values())


async def manage(args: argparse.Namespace) -> bool:
    events_url = f"{args.lobby_url.replace('http', 'ws', 1)}/ws/tournaments/{args.tournament}/events"
    headers = {"X-API-Key": args.api_key}
    async with (
        connect(events_url, additional_headers=headers) as events,
        httpx.AsyncClient(base_url=args.lobby_url, headers=headers, timeout=30.0) as http,
    ):
        logger.info("events socket open, waiting for %d players", len(args.players))
        await wait_until_online(events, args.players)

        submitted = await start_games(http, args.tournament, seat_tables(args.players))
        if not submitted:
            return False

        succeeded = await follow_games(events, submitted)
        response = await http.get(f"/api/tournaments/{args.tournament}")
        logger.info("GET /api/tournaments/%s -> %s %s", args.tournament, response.status_code, response.text)
        return succeeded and response.status_code == httpx.codes.OK


def main() -> None:
    args = parse_args()
    set_up_logging(args.log)
    try:
        succeeded = asyncio.run(manage(args))
    except TimeoutError:
        logger.exception("deadline passed")
        succeeded = False

    logger.info("tournament run %s", "succeeded" if succeeded else "FAILED")
    sys.exit(0 if succeeded else 1)


if __name__ == "__main__":
    main()
