import json

from game.logic.enums import CallType, GameErrorCode, GamePhase, MeldViewType, RoundPhase, WindName
from game.logic.events import (
    BroadcastTarget,
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
    TurnEvent,
)
from game.logic.types import (
    ExhaustiveDrawResult,
    GameEndResult,
    GamePlayerInfo,
    GameView,
    PlayerStanding,
    PlayerView,
)
from game.messaging.event_payload import service_event_payload
from game.session.replay_collector import ReplayCollector


class FakeStorage:
    """In-memory storage for testing replay persistence."""

    def __init__(self) -> None:
        self.saved: dict[str, str] = {}

    def save_replay(self, game_id: str, content: str) -> None:
        self.saved[game_id] = content


class FailingStorage:
    """Storage that always raises on save."""

    def save_replay(self, game_id: str, content: str) -> None:  # noqa: ARG002
        raise OSError("disk full")


# Per-seat tile assignments for 4-player round_started merge tests.
_SEAT_TILES = {
    0: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
    1: [14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26],
    2: [27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39],
    3: [40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52],
}


def _make_discard_event(seat: int = 0, tile_id: int = 10) -> ServiceEvent:
    return ServiceEvent(
        event=EventType.DISCARD,
        data=DiscardEvent(seat=seat, tile_id=tile_id, is_tsumogiri=False, is_riichi=False),
        target=BroadcastTarget(),
    )


def _make_meld_event() -> ServiceEvent:
    return ServiceEvent(
        event=EventType.MELD,
        data=MeldEvent(
            meld_type=MeldViewType.PON,
            caller_seat=1,
            from_seat=0,
            tile_ids=[10, 11, 12],
            called_tile_id=10,
        ),
        target=BroadcastTarget(),
    )


def _make_riichi_event(seat: int = 0) -> ServiceEvent:
    return ServiceEvent(
        event=EventType.RIICHI_DECLARED,
        data=RiichiDeclaredEvent(seat=seat, target="all"),
        target=BroadcastTarget(),
    )


def _make_dora_event() -> ServiceEvent:
    return ServiceEvent(
        event=EventType.DORA_REVEALED,
        data=DoraRevealedEvent(tile_id=5, dora_indicators=[5]),
        target=BroadcastTarget(),
    )


def _make_game_started_event(game_id: str = "game1") -> ServiceEvent:
    return ServiceEvent(
        event=EventType.GAME_STARTED,
        data=GameStartedEvent(
            game_id=game_id,
            players=[GamePlayerInfo(seat=i, name=f"P{i}", is_bot=False) for i in range(4)],
        ),
        target=BroadcastTarget(),
    )


def _make_game_ended_event() -> ServiceEvent:
    return ServiceEvent(
        event=EventType.GAME_END,
        data=GameEndedEvent(
            target="all",
            result=GameEndResult(
                winner_seat=0,
                standings=[PlayerStanding(seat=0, name="P0", score=25000, final_score=0, is_bot=False)],
            ),
        ),
        target=BroadcastTarget(),
    )


def _make_round_end_event() -> ServiceEvent:
    return ServiceEvent(
        event=EventType.ROUND_END,
        data=RoundEndEvent(
            target="all",
            result=ExhaustiveDrawResult(
                tempai_seats=[0],
                noten_seats=[1, 2, 3],
                score_changes={0: 3000, 1: -1000, 2: -1000, 3: -1000},
            ),
        ),
        target=BroadcastTarget(),
    )


def _make_draw_event(seat: int = 0, tile_id: int = 1) -> ServiceEvent:
    """Seat-target draw event (included for replay reconstruction)."""
    return ServiceEvent(
        event=EventType.DRAW,
        data=DrawEvent(seat=seat, tile_id=tile_id, target=f"seat_{seat}"),
        target=SeatTarget(seat=seat),
    )


def _make_turn_event(seat: int = 0) -> ServiceEvent:
    return ServiceEvent(
        event=EventType.TURN,
        data=TurnEvent(current_seat=seat, available_actions=[], wall_count=70, target=f"seat_{seat}"),
        target=SeatTarget(seat=seat),
    )


def _make_call_prompt_event(seat: int = 1) -> ServiceEvent:
    return ServiceEvent(
        event=EventType.CALL_PROMPT,
        data=CallPromptEvent(
            call_type=CallType.MELD,
            tile_id=10,
            from_seat=0,
            callers=[seat],
            target=f"seat_{seat}",
        ),
        target=SeatTarget(seat=seat),
    )


def _make_error_event(seat: int = 0) -> ServiceEvent:
    return ServiceEvent(
        event=EventType.ERROR,
        data=ErrorEvent(code=GameErrorCode.INVALID_ACTION, message="nope", target=f"seat_{seat}"),
        target=SeatTarget(seat=seat),
    )


def _make_furiten_event(seat: int = 0) -> ServiceEvent:
    return ServiceEvent(
        event=EventType.FURITEN,
        data=FuritenEvent(is_furiten=True, target=f"seat_{seat}"),
        target=SeatTarget(seat=seat),
    )


def _make_game_view_for_seat(seat: int) -> GameView:
    """Create a GameView from the perspective of the given seat.

    The viewing player's tiles are visible; other players' tiles are None.
    """
    players = [
        PlayerView(
            seat=s,
            name=f"P{s}",
            is_bot=False,
            score=25000,
            is_riichi=False,
            discards=[],
            melds=[],
            tile_count=13,
            tiles=_SEAT_TILES[s] if s == seat else None,
        )
        for s in range(4)
    ]
    return GameView(
        seat=seat,
        round_wind=WindName.EAST,
        round_number=1,
        dealer_seat=0,
        current_player_seat=0,
        wall_count=70,
        dora_indicators=[],
        honba_sticks=0,
        riichi_sticks=0,
        players=players,
        phase=RoundPhase.PLAYING,
        game_phase=GamePhase.IN_PROGRESS,
    )


def _make_round_started_event(seat: int = 0) -> ServiceEvent:
    """Seat-target round started event with concealed view (included for replay)."""
    return ServiceEvent(
        event=EventType.ROUND_STARTED,
        data=RoundStartedEvent(view=_make_game_view_for_seat(seat), target=f"seat_{seat}"),
        target=SeatTarget(seat=seat),
    )


def _make_all_round_started_events() -> list[ServiceEvent]:
    """Create 4 seat-targeted round_started events (one per player)."""
    return [_make_round_started_event(seat) for seat in range(4)]


class TestReplayCollectorLifecycle:
    """Tests for the start -> collect -> save -> cleanup lifecycle."""

    async def test_full_lifecycle(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", [_make_discard_event()])
        collector.collect_events("game1", [_make_meld_event()])
        await collector.save_and_cleanup("game1")

        assert "game1" in storage.saved
        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 2

        record0 = json.loads(lines[0])
        assert record0["type"] == "discard"

        record1 = json.loads(lines[1])
        assert record1["type"] == "meld"

    def test_cleanup_discards_buffer(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", [_make_discard_event()])
        collector.cleanup_game("game1")

        assert "game1" not in storage.saved

    async def test_save_removes_buffer(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", [_make_discard_event()])
        await collector.save_and_cleanup("game1")

        # second save is a no-op (buffer already removed)
        await collector.save_and_cleanup("game1")
        assert len(storage.saved["game1"].strip().split("\n")) == 1

    async def test_collect_before_start_is_ignored(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        # no start_game call
        collector.collect_events("game1", [_make_discard_event()])
        await collector.save_and_cleanup("game1")

        assert "game1" not in storage.saved


class TestReplayCollectorFiltering:
    """Tests for broadcast-only and excluded type filtering."""

    async def test_broadcast_and_included_seat_target_events_collected(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events(
            "game1",
            [
                _make_discard_event(),  # broadcast - collected
                _make_draw_event(),  # seat-target DrawEvent - collected
                _make_round_started_event(),  # seat-target RoundStartedEvent - merged
            ],
        )
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 3
        types = [json.loads(line)["type"] for line in lines]
        assert types == ["discard", "draw", "round_started"]

    async def test_excluded_types_are_filtered(self):
        """TurnEvent, CallPromptEvent, ErrorEvent, FuritenEvent are excluded."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events(
            "game1",
            [
                _make_turn_event(),
                _make_call_prompt_event(),
                _make_error_event(),
                _make_furiten_event(),
                _make_discard_event(),  # only this should survive
            ],
        )
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["type"] == "discard"

    async def test_excluded_broadcast_types_are_filtered(self):
        """Excluded types are filtered even when broadcast-targeted."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        broadcast_error = ServiceEvent(
            event=EventType.ERROR,
            data=ErrorEvent(code=GameErrorCode.INVALID_ACTION, message="nope", target="all"),
            target=BroadcastTarget(),
        )

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", [broadcast_error, _make_discard_event()])
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["type"] == "discard"

    async def test_draw_event_seat_target_persisted(self):
        """DrawEvent (SeatTarget) carries tile ID data for replay."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", [_make_draw_event(seat=1, tile_id=55)])
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["type"] == "draw"
        assert record["seat"] == 1
        assert record["tile_id"] == 55

    async def test_broadcast_gameplay_events_all_collected(self):
        """All broadcast gameplay event types are persisted."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
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
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 7
        types = [json.loads(line)["type"] for line in lines]
        expected = [
            "game_started",
            "discard",
            "meld",
            "riichi_declared",
            "dora_revealed",
            "round_end",
            "game_end",
        ]
        assert types == expected

    async def test_unknown_target_type_is_excluded(self):
        """Events with an unknown target type are silently excluded."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        unknown_event = ServiceEvent.model_construct(
            event=EventType.DISCARD,
            data=DiscardEvent(seat=0, tile_id=10, is_tsumogiri=False, is_riichi=False, target="all"),
            target="unknown_target",  # type: ignore[arg-type]
        )

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", [unknown_event, _make_discard_event()])
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 1
        assert json.loads(lines[0])["type"] == "discard"


class TestReplayCollectorRoundStartedMerge:
    """Tests for merging per-seat RoundStartedEvent views into a single record."""

    async def test_four_round_started_events_merged_into_one(self):
        """All 4 per-seat round_started events produce a single merged record."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", _make_all_round_started_events())
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["type"] == "round_started"

    async def test_merged_record_contains_all_players_tiles(self):
        """Merged round_started record has tiles for every player."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", _make_all_round_started_events())
        await collector.save_and_cleanup("game1")

        record = json.loads(storage.saved["game1"])
        players = record["view"]["players"]
        assert len(players) == 4
        for player in players:
            seat = player["seat"]
            assert player["tiles"] == _SEAT_TILES[seat]

    async def test_merged_record_uses_first_view_as_base(self):
        """Merged record's view.seat matches the first event's perspective."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", _make_all_round_started_events())
        await collector.save_and_cleanup("game1")

        record = json.loads(storage.saved["game1"])
        assert record["view"]["seat"] == 0

    async def test_single_round_started_event_produces_one_record(self):
        """A single round_started event is wrapped as-is (no merge needed)."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", [_make_round_started_event(seat=2)])
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["type"] == "round_started"
        # Only seat 2's tiles are populated (single event, no merge partner)
        players = record["view"]["players"]
        seat2_player = next(p for p in players if p["seat"] == 2)
        assert seat2_player["tiles"] == _SEAT_TILES[2]

    async def test_merged_round_started_ordered_before_draw(self):
        """Merged round_started appears before subsequent draw events."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events(
            "game1",
            [
                *_make_all_round_started_events(),
                _make_draw_event(seat=0, tile_id=10),
            ],
        )
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 2
        types = [json.loads(line)["type"] for line in lines]
        assert types == ["round_started", "draw"]

    async def test_game_started_then_merged_round_started_then_draw(self):
        """Realistic startup: game_started → merged round_started → draw."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events(
            "game1",
            [
                _make_game_started_event(),
                *_make_all_round_started_events(),
                _make_draw_event(seat=0, tile_id=10),
            ],
        )
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 3
        types = [json.loads(line)["type"] for line in lines]
        assert types == ["game_started", "round_started", "draw"]

    async def test_round_started_across_separate_collect_calls(self):
        """Round_started events in separate collect_events calls produce separate records."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        # First round: all 4 events in one batch
        collector.collect_events("game1", _make_all_round_started_events())
        # Some gameplay
        collector.collect_events("game1", [_make_discard_event()])
        # Second round: all 4 events in another batch
        collector.collect_events("game1", _make_all_round_started_events())
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 3
        types = [json.loads(line)["type"] for line in lines]
        assert types == ["round_started", "discard", "round_started"]


class TestReplayCollectorJsonLines:
    """Tests for JSON lines format."""

    async def test_json_lines_parseable(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events(
            "game1",
            [_make_discard_event(), _make_meld_event(), _make_game_ended_event()],
        )
        await collector.save_and_cleanup("game1")

        for line in storage.saved["game1"].strip().split("\n"):
            record = json.loads(line)
            assert isinstance(record, dict)

    async def test_discard_record_shape(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", [_make_discard_event(seat=2, tile_id=42)])
        await collector.save_and_cleanup("game1")

        record = json.loads(storage.saved["game1"])
        assert record["type"] == "discard"
        assert record["seat"] == 2
        assert record["tile_id"] == 42
        assert record["is_tsumogiri"] is False
        assert record["is_riichi"] is False


class TestReplayCollectorErrorHandling:
    """Tests for error containment on storage failure."""

    async def test_storage_failure_does_not_raise(self):
        collector = ReplayCollector(FailingStorage())

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", [_make_discard_event()])

        # should not raise
        await collector.save_and_cleanup("game1")

    async def test_storage_failure_cleans_up_buffer(self):
        collector = ReplayCollector(FailingStorage())

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", [_make_discard_event()])
        await collector.save_and_cleanup("game1")

        # buffer is removed even on failure (pop before try)
        await collector.save_and_cleanup("game1")  # no-op, no error


class TestReplayCollectorIsolation:
    """Tests for concurrent game isolation."""

    async def test_events_isolated_by_game_id(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.start_game("game2", seed=0.99)

        collector.collect_events("game1", [_make_discard_event(seat=0)])
        collector.collect_events("game2", [_make_discard_event(seat=1), _make_meld_event()])

        await collector.save_and_cleanup("game1")
        await collector.save_and_cleanup("game2")

        lines1 = storage.saved["game1"].strip().split("\n")
        lines2 = storage.saved["game2"].strip().split("\n")
        assert len(lines1) == 1
        assert len(lines2) == 2


class TestReplayCollectorSeedInReplay:
    """Tests that the game seed is included in replay game_started events but never leaks to clients."""

    async def test_game_started_replay_event_includes_seed(self):
        """The replay game_started event contains the seed for deterministic replay."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.12345)
        collector.collect_events("game1", [_make_game_started_event()])
        await collector.save_and_cleanup("game1")

        record = json.loads(storage.saved["game1"])
        assert record["type"] == "game_started"
        assert record["seed"] == 0.12345

    async def test_seed_only_in_game_started_event(self):
        """Seed is injected only into game_started, not into other event types."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events(
            "game1",
            [_make_game_started_event(), _make_discard_event(), _make_game_ended_event()],
        )
        await collector.save_and_cleanup("game1")

        lines = storage.saved["game1"].strip().split("\n")
        assert len(lines) == 3
        game_started = json.loads(lines[0])
        assert game_started["seed"] == 0.42

        discard = json.loads(lines[1])
        assert "seed" not in discard

        game_ended = json.loads(lines[2])
        assert "seed" not in game_ended

    def test_game_started_client_event_excludes_seed(self):
        """The client-facing GameStartedEvent model has no seed field."""
        event = _make_game_started_event()
        payload = service_event_payload(event)
        assert "seed" not in payload

    async def test_seed_cleaned_up_after_save(self):
        """Seed is removed from internal state after save_and_cleanup."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.collect_events("game1", [_make_game_started_event()])
        await collector.save_and_cleanup("game1")

        assert "game1" not in collector._seeds

    def test_seed_cleaned_up_after_cleanup(self):
        """Seed is removed from internal state after cleanup_game."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.cleanup_game("game1")

        assert "game1" not in collector._seeds

    async def test_different_games_have_different_seeds(self):
        """Each game stores its own seed independently."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.111)
        collector.start_game("game2", seed=0.222)
        collector.collect_events("game1", [_make_game_started_event("game1")])
        collector.collect_events("game2", [_make_game_started_event("game2")])
        await collector.save_and_cleanup("game1")
        await collector.save_and_cleanup("game2")

        record1 = json.loads(storage.saved["game1"])
        record2 = json.loads(storage.saved["game2"])
        assert record1["seed"] == 0.111
        assert record2["seed"] == 0.222


class TestReplayCollectorSensitiveDataGuard:
    """Tests that concealed data is only written when collection is active."""

    async def test_concealed_events_not_persisted_without_start(self):
        """Concealed seat-target events are silently dropped if game was not started."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.collect_events(
            "game1",
            [
                _make_draw_event(),
                _make_round_started_event(),
            ],
        )
        await collector.save_and_cleanup("game1")

        assert "game1" not in storage.saved

    async def test_concealed_events_not_persisted_after_cleanup(self):
        """Concealed seat-target events are silently dropped after game cleanup."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed=0.42)
        collector.cleanup_game("game1")

        collector.collect_events(
            "game1",
            [_make_draw_event(), _make_round_started_event()],
        )
        await collector.save_and_cleanup("game1")

        assert "game1" not in storage.saved
