import json

from game.logic.enums import CallType, GameErrorCode, MeldViewType, WindName
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
from game.messaging.compact import encode_discard, encode_draw
from game.messaging.event_payload import EVENT_TYPE_INT, service_event_payload
from game.replay.models import REPLAY_VERSION
from game.session.replay_collector import ReplayCollector


class FakeStorage:
    """In-memory storage for testing replay persistence."""

    def __init__(self) -> None:
        self.saved: dict[str, str] = {}

    def save_replay(self, game_id: str, content: str) -> None:
        self.saved[game_id] = content


class FailingStorage:
    """Storage that always raises on save."""

    def save_replay(self, game_id: str, content: str) -> None:
        raise OSError("disk full")


def _parse_saved_replay(content: str) -> list[dict]:
    """Parse saved replay content, validate version tag, return event dicts."""
    events = json.loads("[" + content.replace("}{", "},{") + "]")
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
        event=EventType.DISCARD,
        data=DiscardEvent(seat=seat, tile_id=tile_id),
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
        data=DoraRevealedEvent(tile_id=5),
        target=BroadcastTarget(),
    )


def _make_game_started_event(game_id: str = "game1") -> ServiceEvent:
    return ServiceEvent(
        event=EventType.GAME_STARTED,
        data=GameStartedEvent(
            game_id=game_id,
            players=[GamePlayerInfo(seat=i, name=f"P{i}", is_ai_player=False) for i in range(4)],
            dealer_seat=0,
            dealer_dice=((1, 1), (1, 1)),
        ),
        target=BroadcastTarget(),
    )


def _make_game_ended_event() -> ServiceEvent:
    return ServiceEvent(
        event=EventType.GAME_END,
        data=GameEndedEvent(
            target="all",
            winner_seat=0,
            standings=[PlayerStanding(seat=0, score=25000, final_score=0)],
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
                tenpai_hands=[TenpaiHand(seat=0, closed_tiles=[], melds=[])],
                scores={0: 25000, 1: 25000, 2: 25000, 3: 25000},
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


def _make_round_started_event(seat: int = 0) -> ServiceEvent:
    """Seat-target round started event with concealed tiles (included for replay)."""
    players = [PlayerView(seat=s, score=25000) for s in range(4)]
    return ServiceEvent(
        event=EventType.ROUND_STARTED,
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
            target=f"seat_{seat}",
        ),
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

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event()])
        collector.collect_events("game1", [_make_meld_event()])
        await collector.save_and_cleanup("game1")

        assert "game1" in storage.saved
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 2

        record0 = lines[0]
        assert record0["t"] == EVENT_TYPE_INT[EventType.DISCARD]

        record1 = lines[1]
        assert record1["t"] == EVENT_TYPE_INT[EventType.MELD]

    def test_cleanup_discards_buffer(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event()])
        collector.cleanup_game("game1")

        assert "game1" not in storage.saved

    async def test_save_removes_buffer(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event()])
        await collector.save_and_cleanup("game1")

        # second save is a no-op (buffer already removed)
        await collector.save_and_cleanup("game1")
        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 1

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

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events(
            "game1",
            [
                _make_discard_event(),  # broadcast - collected
                _make_draw_event(),  # seat-target DrawEvent - collected
                _make_round_started_event(),  # seat-target RoundStartedEvent - merged
            ],
        )
        await collector.save_and_cleanup("game1")

        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 3
        types = [event["t"] for event in lines]
        assert types == [
            EVENT_TYPE_INT[EventType.DISCARD],
            EVENT_TYPE_INT[EventType.DRAW],
            EVENT_TYPE_INT[EventType.ROUND_STARTED],
        ]

    async def test_excluded_types_are_filtered(self):
        """CallPromptEvent, ErrorEvent, FuritenEvent are excluded."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events(
            "game1",
            [
                _make_call_prompt_event(),
                _make_error_event(),
                _make_furiten_event(),
                _make_discard_event(),  # only this should survive
            ],
        )
        await collector.save_and_cleanup("game1")

        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 1
        assert lines[0]["t"] == EVENT_TYPE_INT[EventType.DISCARD]

    async def test_excluded_broadcast_types_are_filtered(self):
        """Excluded types are filtered even when broadcast-targeted."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        broadcast_error = ServiceEvent(
            event=EventType.ERROR,
            data=ErrorEvent(code=GameErrorCode.INVALID_ACTION, message="nope", target="all"),
            target=BroadcastTarget(),
        )

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [broadcast_error, _make_discard_event()])
        await collector.save_and_cleanup("game1")

        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 1
        assert lines[0]["t"] == EVENT_TYPE_INT[EventType.DISCARD]

    async def test_draw_event_available_actions_stripped(self):
        """DrawEvent available_actions field is stripped from replay output."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        draw_with_actions = ServiceEvent(
            event=EventType.DRAW,
            data=DrawEvent(
                seat=0,
                tile_id=42,
                target="seat_0",
                available_actions=[AvailableActionItem(action="discard", tiles=[42])],
            ),
            target=SeatTarget(seat=0),
        )

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [draw_with_actions])
        await collector.save_and_cleanup("game1")

        record = _parse_saved_replay(storage.saved["game1"])[0]
        assert record["t"] == EVENT_TYPE_INT[EventType.DRAW]
        assert record["d"] == encode_draw(0, 42)
        assert "aa" not in record

    async def test_broadcast_gameplay_events_all_collected(self):
        """All broadcast gameplay event types are persisted."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
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

    async def test_unknown_target_type_is_excluded(self):
        """Events with an unknown target type are silently excluded."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        unknown_event = ServiceEvent.model_construct(
            event=EventType.DISCARD,
            data=DiscardEvent(seat=0, tile_id=10, target="all"),
            target="unknown_target",
        )

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [unknown_event, _make_discard_event()])
        await collector.save_and_cleanup("game1")

        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 1
        assert lines[0]["t"] == EVENT_TYPE_INT[EventType.DISCARD]


class TestReplayCollectorRoundStartedMerge:
    """Tests for merging per-seat RoundStartedEvent views into a single record."""

    async def test_four_round_started_events_merged_into_one(self):
        """All 4 per-seat round_started events produce a single merged record."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", _make_all_round_started_events())
        await collector.save_and_cleanup("game1")

        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 1
        record = lines[0]
        assert record["t"] == EVENT_TYPE_INT[EventType.ROUND_STARTED]

    async def test_merged_record_contains_all_players_tiles(self):
        """Merged round_started record has tiles for every player from my_tiles."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", _make_all_round_started_events())
        await collector.save_and_cleanup("game1")

        record = _parse_saved_replay(storage.saved["game1"])[0]
        players = record["p"]
        assert len(players) == 4
        for player in players:
            seat = player["s"]
            assert player["tl"] == _SEAT_TILES[seat]

        # mt (my_tiles) and s (seat) are stripped from the merged output
        assert "mt" not in record
        assert "s" not in record

    async def test_merged_record_scores_in_wire_format(self):
        """Scores in merged round_started are in wire format (divided by 100 once)."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", _make_all_round_started_events())
        await collector.save_and_cleanup("game1")

        record = _parse_saved_replay(storage.saved["game1"])[0]
        for player in record["p"]:
            # 25000 points / 100 = 250 in wire format
            assert player["sc"] == 250

    async def test_single_round_started_event_produces_one_record(self):
        """A single round_started event is wrapped as-is (no merge needed)."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_round_started_event(seat=2)])
        await collector.save_and_cleanup("game1")

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

    async def test_merged_round_started_ordered_before_draw(self):
        """Merged round_started appears before subsequent draw events."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events(
            "game1",
            [
                *_make_all_round_started_events(),
                _make_draw_event(seat=0, tile_id=10),
            ],
        )
        await collector.save_and_cleanup("game1")

        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 2
        types = [event["t"] for event in lines]
        assert types == [EVENT_TYPE_INT[EventType.ROUND_STARTED], EVENT_TYPE_INT[EventType.DRAW]]

    async def test_game_started_then_merged_round_started_then_draw(self):
        """Realistic startup: game_started → merged round_started → draw."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events(
            "game1",
            [
                _make_game_started_event(),
                *_make_all_round_started_events(),
                _make_draw_event(seat=0, tile_id=10),
            ],
        )
        await collector.save_and_cleanup("game1")

        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 3
        types = [event["t"] for event in lines]
        assert types == [
            EVENT_TYPE_INT[EventType.GAME_STARTED],
            EVENT_TYPE_INT[EventType.ROUND_STARTED],
            EVENT_TYPE_INT[EventType.DRAW],
        ]

    async def test_round_started_across_separate_collect_calls(self):
        """Round_started events in separate collect_events calls produce separate records."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        # First round: all 4 events in one batch
        collector.collect_events("game1", _make_all_round_started_events())
        # Some gameplay
        collector.collect_events("game1", [_make_discard_event()])
        # Second round: all 4 events in another batch
        collector.collect_events("game1", _make_all_round_started_events())
        await collector.save_and_cleanup("game1")

        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 3
        types = [event["t"] for event in lines]
        assert types == [
            EVENT_TYPE_INT[EventType.ROUND_STARTED],
            EVENT_TYPE_INT[EventType.DISCARD],
            EVENT_TYPE_INT[EventType.ROUND_STARTED],
        ]


class TestReplayCollectorJsonLines:
    """Tests for JSON lines format."""

    async def test_discard_record_shape(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event(seat=2, tile_id=42)])
        await collector.save_and_cleanup("game1")

        record = _parse_saved_replay(storage.saved["game1"])[0]
        assert record["t"] == EVENT_TYPE_INT[EventType.DISCARD]
        assert record["d"] == encode_discard(2, 42, is_tsumogiri=False, is_riichi=False)

    async def test_riichi_discard_encoded_in_packed_integer(self):
        """Riichi discards encode is_riichi in the packed integer."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        riichi_discard = ServiceEvent(
            event=EventType.DISCARD,
            data=DiscardEvent(seat=0, tile_id=10, is_riichi=True),
            target=BroadcastTarget(),
        )

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [riichi_discard])
        await collector.save_and_cleanup("game1")

        record = _parse_saved_replay(storage.saved["game1"])[0]
        assert record["d"] == encode_discard(0, 10, is_tsumogiri=False, is_riichi=True)


class TestReplayCollectorErrorHandling:
    """Tests for error containment on storage failure."""

    async def test_storage_failure_does_not_raise(self):
        collector = ReplayCollector(FailingStorage())

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event()])

        # should not raise
        await collector.save_and_cleanup("game1")

    async def test_storage_failure_cleans_up_buffer(self):
        collector = ReplayCollector(FailingStorage())

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_discard_event()])
        await collector.save_and_cleanup("game1")

        # buffer is removed even on failure (pop before try)
        await collector.save_and_cleanup("game1")  # no-op, no error


class TestReplayCollectorIsolation:
    """Tests for concurrent game isolation."""

    async def test_events_isolated_by_game_id(self):
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.start_game("game2", seed="c" * 192, rng_version=RNG_VERSION)

        collector.collect_events("game1", [_make_discard_event(seat=0)])
        collector.collect_events("game2", [_make_discard_event(seat=1), _make_meld_event()])

        await collector.save_and_cleanup("game1")
        await collector.save_and_cleanup("game2")

        lines1 = _parse_saved_replay(storage.saved["game1"])
        lines2 = _parse_saved_replay(storage.saved["game2"])
        assert len(lines1) == 1
        assert len(lines2) == 2


class TestReplayCollectorSeedInReplay:
    """Tests that the game seed is included in replay game_started events but never leaks to clients."""

    async def test_game_started_replay_event_includes_seed(self):
        """The replay game_started event contains the seed for deterministic replay."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="d" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_game_started_event()])
        await collector.save_and_cleanup("game1")

        record = _parse_saved_replay(storage.saved["game1"])[0]
        assert record["t"] == EVENT_TYPE_INT[EventType.GAME_STARTED]
        assert record["sd"] == "d" * 192
        assert record["rv"] == RNG_VERSION

    async def test_seed_only_in_game_started_event(self):
        """Seed is injected only into game_started, not into other event types."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events(
            "game1",
            [_make_game_started_event(), _make_discard_event(), _make_game_ended_event()],
        )
        await collector.save_and_cleanup("game1")

        lines = _parse_saved_replay(storage.saved["game1"])
        assert len(lines) == 3
        game_started = lines[0]
        assert game_started["sd"] == "b" * 192
        assert game_started["rv"] == RNG_VERSION

        discard = lines[1]
        assert "sd" not in discard

        game_ended = lines[2]
        assert "sd" not in game_ended

    def test_game_started_client_event_excludes_seed(self):
        """The client-facing GameStartedEvent model has no seed field."""
        event = _make_game_started_event()
        payload = service_event_payload(event)
        assert "sd" not in payload

    async def test_seed_cleaned_up_after_save(self):
        """Seed is removed from internal state after save_and_cleanup."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_game_started_event()])
        await collector.save_and_cleanup("game1")

        assert "game1" not in collector._seeds

    def test_seed_cleaned_up_after_cleanup(self):
        """Seed is removed from internal state after cleanup_game."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.cleanup_game("game1")

        assert "game1" not in collector._seeds

    async def test_different_games_have_different_seeds(self):
        """Each game stores its own seed independently."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="e" * 192, rng_version=RNG_VERSION)
        collector.start_game("game2", seed="f" * 192, rng_version=RNG_VERSION)
        collector.collect_events("game1", [_make_game_started_event("game1")])
        collector.collect_events("game2", [_make_game_started_event("game2")])
        await collector.save_and_cleanup("game1")
        await collector.save_and_cleanup("game2")

        record1 = _parse_saved_replay(storage.saved["game1"])[0]
        record2 = _parse_saved_replay(storage.saved["game2"])[0]
        assert record1["sd"] == "e" * 192
        assert record2["sd"] == "f" * 192


class TestReplayCollectorSensitiveDataGuard:
    """Tests that concealed data is only written when collection is active."""

    async def test_concealed_events_not_persisted_after_cleanup(self):
        """Concealed seat-target events are silently dropped after game cleanup."""
        storage = FakeStorage()
        collector = ReplayCollector(storage)

        collector.start_game("game1", seed="b" * 192, rng_version=RNG_VERSION)
        collector.cleanup_game("game1")

        collector.collect_events(
            "game1",
            [_make_draw_event(), _make_round_started_event()],
        )
        await collector.save_and_cleanup("game1")

        assert "game1" not in storage.saved
