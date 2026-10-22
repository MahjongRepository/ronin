import json

from game.logic.enums import CallType, GameErrorCode, MeldViewType, WindName
from game.logic.events import (
    CallPromptEvent,
    DiscardEvent,
    DoraRevealedEvent,
    DrawEvent,
    ErrorEvent,
    EventType,
    FuritenEvent,
    GameEndedEvent,
    GameStartedEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    RoundStartedEvent,
    SeatTarget,
    ServiceEvent,
)
from game.logic.rng import RNG_VERSION
from game.logic.types import (
    AvailableActionItem,
    ExhaustiveDrawResult,
    GamePlayerInfo,
    PlayerStanding,
    PlayerView,
    TenpaiHand,
)
from game.messaging.event_payload import service_event_payload
from game.session.replay_collector import ReplayCollector
from game.wire.compact import encode_discard, encode_draw
from game.wire.events import EVENT_TYPE_INT
from game.wire.replay_format import REPLAY_VERSION


class FakeStorage:
    def __init__(self) -> None:
        self.saved: dict[str, str] = {}

    def save_replay(self, game_id: str, content: str) -> None:
        self.saved[game_id] = content


class FailingStorage:
    def save_replay(self, game_id: str, content: str) -> None:
        raise OSError("disk full")


def _parse_saved_replay(content: str) -> list[dict]:
    events = [json.loads(line) for line in content.strip().split("\n") if line]
    assert len(events) >= 1
    assert events[0] == {"version": REPLAY_VERSION}
    return events[1:]


# Per-seat tile assignments for 4-player round_started merge tests.
_SEAT_TILES = {
    0: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
    1: [14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26],
    2: [27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39],
    3: [40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52],
}


def _make_discard_event(seat: int = 0, tile_id: int = 10) -> ServiceEvent:
    return ServiceEvent(
        data=DiscardEvent(seat=seat, tile_id=tile_id),
    )


def _make_meld_event() -> ServiceEvent:
    return ServiceEvent(
        data=MeldEvent(
            meld_type=MeldViewType.PON,
            caller_seat=1,
            from_seat=0,
            tile_ids=[10, 11, 12],
            called_tile_id=10,
        ),
    )


def _make_riichi_event(seat: int = 0) -> ServiceEvent:
    return ServiceEvent(
        data=RiichiDeclaredEvent(seat=seat),
    )


def _make_dora_event() -> ServiceEvent:
    return ServiceEvent(
        data=DoraRevealedEvent(tile_id=5),
    )


def _make_game_started_event(game_id: str = "game1") -> ServiceEvent:
    return ServiceEvent(
        data=GameStartedEvent(
            game_id=game_id,
            players=[GamePlayerInfo(seat=i, name=f"P{i}", is_ai_player=False) for i in range(4)],
            dealer_seat=0,
            dealer_dice=((1, 1), (1, 1)),
        ),
    )


def _make_game_ended_event() -> ServiceEvent:
    return ServiceEvent(
        data=GameEndedEvent(
            winner_seat=0,
            standings=[PlayerStanding(seat=0, score=25000, final_score=0)],
        ),
    )


def _make_round_end_event() -> ServiceEvent:
    return ServiceEvent(
        data=RoundEndEvent(
            result=ExhaustiveDrawResult(
                tempai_seats=[0],
                noten_seats=[1, 2, 3],
                tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
                scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
                score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
            ),
        ),
    )


def _make_draw_event(seat: int = 0, tile_id: int = 1) -> ServiceEvent:
    return ServiceEvent(
        data=DrawEvent(seat=seat, tile_id=tile_id, target=SeatTarget(seat=seat)),
    )


def _make_call_prompt_event(seat: int = 1) -> ServiceEvent:
    return ServiceEvent(
        data=CallPromptEvent(
            call_type=CallType.MELD,
            tile_id=10,
            from_seat=0,
            callers=[seat],
            target=SeatTarget(seat=seat),
        ),
    )


def _make_error_event(seat: int = 0) -> ServiceEvent:
    return ServiceEvent(
        data=ErrorEvent(code=GameErrorCode.INVALID_ACTION, message="nope", target=SeatTarget(seat=seat)),
    )


def _make_furiten_event(seat: int = 0) -> ServiceEvent:
    return ServiceEvent(
        data=FuritenEvent(is_furiten=True, target=SeatTarget(seat=seat)),
    )


def _make_round_started_event(seat: int = 0) -> ServiceEvent:
    players = [PlayerView(seat=s, score=25000) for s in range(4)]
    return ServiceEvent(
        data=RoundStartedEvent(
            seat=seat,
            round_wind=WindName.EAST,
            round_number=1,
            dealer_seat=0,
            current_player_seat=0,
            dora_indicators=[],
            honba_sticks=0,
            riichi_sticks=0,
            my_tiles=_SEAT_TILES[seat],
            players=players,
            target=SeatTarget(seat=seat),
        ),
    )


def _make_all_round_started_events() -> list[ServiceEvent]:
    return [_make_round_started_event(seat) for seat in range(4)]


class TestReplayCollectorLifecycle:
    async def test_replay_collector__when_events_collected_and_saved__should_store_one_record_per_event(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event()])
        collector.collect_events("game1", [_make_meld_event()])

        await collector.save("game1", collector.detach_game("game1"))
        assert "game1" in storage.saved
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 2
        record0 = lines[0]
        assert record0["t"] == EVENT_TYPE_INT[EventType.DISCARD]
        record1 = lines[1]
        assert record1["t"] == EVENT_TYPE_INT[EventType.MELD]

    def test_replay_collector__when_game_cleaned_up__should_discard_buffer_without_saving(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event()])
        collector.cleanup_game("game1")
        assert "game1" not in storage.saved

    async def test_replay_collector__when_saved_twice__should_save_only_once(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event()])
        await collector.save("game1", collector.detach_game("game1"))

        # second save is a no-op (buffer already removed)
        await collector.save("game1", collector.detach_game("game1"))
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 1

    async def test_replay_collector__when_events_collected_before_start__should_ignore_them(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        # no start_game call
        collector.collect_events("game1", [_make_discard_event()])
        await collector.save("game1", collector.detach_game("game1"))
        assert "game1" not in storage.saved


class TestReplayCollectorFiltering:
    async def test_replay_collector__when_broadcast_and_seat_target_events__should_collect_them(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events(
            "game1",
            [
                _make_discard_event(),  # broadcast - collected
                _make_draw_event(),  # seat-target DrawEvent - collected
                _make_round_started_event(),  # seat-target RoundStartedEvent - merged
            ],
        )

        await collector.save("game1", collector.detach_game("game1"))
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 3
        types = [event["t"] for event in lines]
        assert types == [
            EVENT_TYPE_INT[EventType.DISCARD],
            EVENT_TYPE_INT[EventType.DRAW],
            EVENT_TYPE_INT[EventType.ROUND_STARTED],
        ]

    async def test_replay_collector__when_excluded_event_types__should_filter_them_out(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events(
            "game1",
            [
                _make_call_prompt_event(),
                _make_error_event(),
                _make_furiten_event(),
                _make_discard_event(),  # only this should survive
            ],
        )

        await collector.save("game1", collector.detach_game("game1"))
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 1
        assert lines[0]["t"] == EVENT_TYPE_INT[EventType.DISCARD]

    async def test_replay_collector__when_draw_has_available_actions__should_strip_them(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        draw_with_actions = ServiceEvent(
            data=DrawEvent(
                seat=0,
                tile_id=42,
                target=SeatTarget(seat=0),
                available_actions=[AvailableActionItem(action="discard", tiles=[42])],
            ),
        )

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [draw_with_actions])

        await collector.save("game1", collector.detach_game("game1"))
        record = _parse_saved_replay(storage.saved["game1"])[0]
        assert record["t"] == EVENT_TYPE_INT[EventType.DRAW]
        assert record["d"] == encode_draw(0, 42)
        assert "aa" not in record

    async def test_replay_collector__when_broadcast_gameplay_events__should_collect_all_in_order(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events(
            "game1",
            [
                _make_game_started_event(),
                _make_discard_event(),
                _make_meld_event(),
                _make_riichi_event(),
                _make_dora_event(),
                _make_round_end_event(),
                _make_game_ended_event(),
            ],
        )

        await collector.save("game1", collector.detach_game("game1"))
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 7
        types = [event["t"] for event in lines]
        expected = [
            EVENT_TYPE_INT[EventType.GAME_STARTED],
            EVENT_TYPE_INT[EventType.DISCARD],
            EVENT_TYPE_INT[EventType.MELD],
            EVENT_TYPE_INT[EventType.RIICHI_DECLARED],
            EVENT_TYPE_INT[EventType.DORA_REVEALED],
            EVENT_TYPE_INT[EventType.ROUND_END],
            EVENT_TYPE_INT[EventType.GAME_END],
        ]
        assert types == expected


class TestReplayCollectorRoundStartedMerge:
    async def test_replay_collector__when_four_round_started_events__should_merge_into_one_record(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", _make_all_round_started_events())

        await collector.save("game1", collector.detach_game("game1"))
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 1
        record = lines[0]
        assert record["t"] == EVENT_TYPE_INT[EventType.ROUND_STARTED]
        players = record["p"]
        assert len(players) == 4
        for player in players:
            seat = player["s"]
            assert player["tl"] == _SEAT_TILES[seat]
            # 25000 points / 100 = 250 in wire format
            assert player["sc"] == 250

        # mt (my_tiles) and s (seat) are stripped from the merged output
        assert "mt" not in record
        assert "s" not in record

    async def test_replay_collector__when_single_round_started_event__should_produce_one_record(
        self,
    ):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_round_started_event(seat=2)])

        await collector.save("game1", collector.detach_game("game1"))
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 1
        record = lines[0]
        assert record["t"] == EVENT_TYPE_INT[EventType.ROUND_STARTED]
        # Only seat 2's tiles are populated from my_tiles (single event, no merge partner)
        players = record["p"]
        seat2_player = next(p for p in players if p["s"] == 2)
        assert seat2_player["tl"] == _SEAT_TILES[2]
        # mt (my_tiles) is stripped from the merged output
        assert "mt" not in record

    async def test_replay_collector__when_round_started_follows_game_started__should_merge_and_keep_order(
        self,
    ):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events(
            "game1",
            [
                _make_game_started_event(),
                *_make_all_round_started_events(),
                _make_draw_event(seat=0, tile_id=10),
            ],
        )

        await collector.save("game1", collector.detach_game("game1"))
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 3
        types = [event["t"] for event in lines]
        assert types == [
            EVENT_TYPE_INT[EventType.GAME_STARTED],
            EVENT_TYPE_INT[EventType.ROUND_STARTED],
            EVENT_TYPE_INT[EventType.DRAW],
        ]

    async def test_replay_collector__when_round_started_events_in_separate_batches__should_merge_each_round(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        # First round: all 4 events in one batch
        collector.collect_events("game1", _make_all_round_started_events())
        # Some gameplay
        collector.collect_events("game1", [_make_discard_event()])
        # Second round: all 4 events in another batch
        collector.collect_events("game1", _make_all_round_started_events())

        await collector.save("game1", collector.detach_game("game1"))
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 3
        types = [event["t"] for event in lines]
        assert types == [
            EVENT_TYPE_INT[EventType.ROUND_STARTED],
            EVENT_TYPE_INT[EventType.DISCARD],
            EVENT_TYPE_INT[EventType.ROUND_STARTED],
        ]


class TestReplayCollectorJsonLines:
    async def test_replay_collector__when_discard_collected__should_store_packed_discard(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event(seat=2, tile_id=42)])

        await collector.save("game1", collector.detach_game("game1"))
        record = _parse_saved_replay(storage.saved["game1"])[0]
        assert record["t"] == EVENT_TYPE_INT[EventType.DISCARD]
        assert record["d"] == encode_discard(2, 42, is_tsumogiri=False, is_riichi=False)

    async def test_replay_collector__when_riichi_discard_collected__should_encode_riichi_in_packed_value(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        riichi_discard = ServiceEvent(
            data=DiscardEvent(seat=0, tile_id=10, is_riichi=True),
        )

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [riichi_discard])

        await collector.save("game1", collector.detach_game("game1"))
        record = _parse_saved_replay(storage.saved["game1"])[0]
        assert record["d"] == encode_discard(0, 10, is_tsumogiri=False, is_riichi=True)


class TestReplayCollectorErrorHandling:
    async def test_replay_collector__when_storage_fails__should_not_raise(self):
        collector = ReplayCollector(FailingStorage())

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event()])

        # should not raise
        await collector.save("game1", collector.detach_game("game1"))

    async def test_replay_collector__when_storage_fails__should_still_remove_buffer(self):
        collector = ReplayCollector(FailingStorage())

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event()])
        await collector.save("game1", collector.detach_game("game1"))
        assert collector.detach_game("game1") is None


class TestReplayCollectorIsolation:
    async def test_replay_collector__when_two_games_collected__should_isolate_events_and_seeds(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="e" * 192, rng_version=RNG_VERSION)
        collector.start_game(game_id="game2", seed="f" * 192, rng_version=RNG_VERSION)

        collector.collect_events("game1", [_make_game_started_event("game1"), _make_discard_event(seat=0)])
        collector.collect_events(
            "game2",
            [_make_game_started_event("game2"), _make_discard_event(seat=1), _make_meld_event()],
        )

        await collector.save("game1", collector.detach_game("game1"))
        await collector.save("game2", collector.detach_game("game2"))
        lines1 = _parse_saved_replay(storage.saved["game1"])
        lines2 = _parse_saved_replay(storage.saved["game2"])
        # Events are isolated
        assert len(lines1) == 2
        assert len(lines2) == 3
        # Seeds are isolated
        assert lines1[0]["sd"] == "e" * 192
        assert lines2[0]["sd"] == "f" * 192


class TestReplayCollectorSeedInReplay:
    async def test_replay_collector__when_game_started_collected__should_include_seed_and_rng_version(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="d" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_game_started_event()])

        await collector.save("game1", collector.detach_game("game1"))
        record = _parse_saved_replay(storage.saved["game1"])[0]
        assert record["t"] == EVENT_TYPE_INT[EventType.GAME_STARTED]
        assert record["sd"] == "d" * 192
        assert record["rv"] == RNG_VERSION

    async def test_replay_collector__when_multiple_events_collected__should_include_seed_only_in_game_started(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events(
            "game1",
            [_make_game_started_event(), _make_discard_event(), _make_game_ended_event()],
        )

        await collector.save("game1", collector.detach_game("game1"))
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 3
        game_started = lines[0]
        assert game_started["sd"] == "b" * 192
        assert game_started["rv"] == RNG_VERSION
        discard = lines[1]
        assert "sd" not in discard
        game_ended = lines[2]
        assert "sd" not in game_ended

    def test_service_event_payload__when_game_started__should_exclude_seed(self):
        event = _make_game_started_event()
        payload = service_event_payload(event)
        assert "sd" not in payload


class TestReplayCollectorSensitiveDataGuard:
    async def test_replay_collector__when_events_collected_after_cleanup__should_not_persist_them(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game(game_id="game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.cleanup_game("game1")

        collector.collect_events(
            "game1",
            [_make_draw_event(), _make_round_started_event()],
        )
        await collector.save("game1", collector.detach_game("game1"))
        assert "game1" not in storage.saved
