from game.logic.enums import GameAction
from game.logic.events import DoraRevealedEvent, EventType
from game.logic.settings import GameSettings
from game.logic.tiles import tile_to_34
from game.replay import run_replay
from game.replay.models import ReplayInput, ReplayInputEvent

# Seed determines seat assignment via fill_seats(names, seed):
# Alice -> seat 2, Bob -> seat 1, Charlie -> seat 0, Diana -> seat 3
SEED = (
    "23824ff8ec95775ba5bb8de82f2903f25472e4a1f10a54ee31a955210ee871508f95c77bbc51b410531abd33a18d26df"
    "ef563e3bcf5af18c7663313c52eacd650ec18e6993c2ab70912ca363e0ed5bd9c088a5d406dc03584e33879746e7d79f"
)
PLAYERS = ("Alice", "Bob", "Charlie", "Diana")

# tile_34=27 is East wind (1z), tile IDs 108-111
EAST_WIND_TILES = (108, 109, 110, 111)

# Dead wall layout: [122, 123, 124, 125, ...134, 135]
# First dora indicator: dead_wall[2] = tile 124
# Second dora indicator (after kan): dead_wall[3] = tile 125
FIRST_DORA_INDICATOR = 124
SECOND_DORA_INDICATOR = 125


def _build_added_kan_wall() -> tuple[int, ...]:
    wall = list(range(136))

    # Seat 1 hand positions: 4-7, 20-23, 36-39, 49
    # Put tile 108 at position 4 (seat 1 hand)
    wall[4], wall[108] = wall[108], wall[4]

    # Seat 2 hand positions: 8-11, 24-27, 40-43, 50
    # Put tiles 109, 110 at positions 8, 9 (seat 2 hand)
    wall[8], wall[109] = wall[109], wall[8]
    wall[9], wall[110] = wall[110], wall[9]

    # Live wall starts at position 52. Draw sequence after pon:
    # draw 0: seat 0 (wall[52]), draw 1: seat 1 (wall[53]),
    # [pon by seat 2, discard], draw 2: seat 3 (wall[54]),
    # draw 3: seat 0 (wall[55]), draw 4: seat 1 (wall[56]),
    # draw 5: seat 2 (wall[57]) <- put tile 111 here
    wall[57], wall[111] = wall[111], wall[57]

    return tuple(wall)


def _build_added_kan_events() -> tuple[ReplayInputEvent, ...]:
    return (
        # 1. Dealer (Charlie, seat 0) discards after initial draw
        ReplayInputEvent(player_name="Charlie", action=GameAction.DISCARD, data={"tile_id": 0}),
        # 2. Bob (seat 1) draws, discards tile 108 (1z)
        ReplayInputEvent(player_name="Bob", action=GameAction.DISCARD, data={"tile_id": 108}),
        # 3. Alice (seat 2) calls pon on tile 108
        ReplayInputEvent(player_name="Alice", action=GameAction.CALL_PON, data={"tile_id": 108}),
        # 4. Alice discards tile 10
        ReplayInputEvent(player_name="Alice", action=GameAction.DISCARD, data={"tile_id": 10}),
        # 5. Diana (seat 3) draws, discards tile 12
        ReplayInputEvent(player_name="Diana", action=GameAction.DISCARD, data={"tile_id": 12}),
        # 6. Charlie (seat 0) draws, discards tile 1
        ReplayInputEvent(player_name="Charlie", action=GameAction.DISCARD, data={"tile_id": 1}),
        # 7. Bob (seat 1) draws, discards tile 5
        ReplayInputEvent(player_name="Bob", action=GameAction.DISCARD, data={"tile_id": 5}),
        # 8. Alice (seat 2) draws tile 111 (1z), calls added kan
        ReplayInputEvent(
            player_name="Alice",
            action=GameAction.CALL_KAN,
            data={"tile_id": 111, "kan_type": "added"},
        ),
        ReplayInputEvent(player_name="Alice", action=GameAction.DISCARD, data={"tile_id": 122}),
    )


def test_added_kan__when_replayed__should_upgrade_pon_and_draw_replacement():
    replay = ReplayInput(
        seed=SEED,
        player_names=PLAYERS,
        settings=GameSettings(),
        wall=_build_added_kan_wall(),
        events=_build_added_kan_events(),
    )
    trace = run_replay(replay)
    # Find the kan step
    non_synthetic_steps = [s for s in trace.steps if not s.synthetic]
    kan_steps = [s for s in non_synthetic_steps if s.input_event.action == GameAction.CALL_KAN]
    assert len(kan_steps) == 1
    kan_step = kan_steps[0]
    assert kan_step.input_event.player_name == "Alice"
    # Verify meld event was emitted
    step_event_types = [e.type for e in kan_step.emitted_events]
    assert EventType.MELD in step_event_types
    # After kan: Alice (seat 2) should have the upgraded meld
    alice_after_kan = kan_step.state_after.round_state.players[2]
    assert len(alice_after_kan.melds) == 1
    kan_meld = alice_after_kan.melds[0]
    assert kan_meld.type == "shouminkan"
    assert set(kan_meld.tiles) == set(EAST_WIND_TILES)
    # Tile 111 must NOT be in Alice's hand (it was used for kan)
    assert 111 not in alice_after_kan.tiles
    assert 122 in alice_after_kan.tiles
    # The discard step after kan must have succeeded
    discard_after_kan = non_synthetic_steps[-1]
    assert discard_after_kan.input_event.action == GameAction.DISCARD
    assert discard_after_kan.input_event.player_name == "Alice"
    assert discard_after_kan.input_event.data["tile_id"] == 122
    # State transitions must be consistent
    for i in range(len(trace.steps) - 1):
        assert trace.steps[i].state_after == trace.steps[i + 1].state_before


def test_added_kan__when_replayed__should_leave_eleven_tiles_in_hand():
    replay = ReplayInput(
        seed=SEED,
        player_names=PLAYERS,
        settings=GameSettings(),
        wall=_build_added_kan_wall(),
        events=_build_added_kan_events(),
    )
    trace = run_replay(replay)
    non_synthetic_steps = [s for s in trace.steps if not s.synthetic]
    kan_step = next(s for s in non_synthetic_steps if s.input_event.action == GameAction.CALL_KAN)
    alice_after_kan = kan_step.state_after.round_state.players[2]
    # Hand should have 11 tiles (13 - 2 pon - 1 discard + 1 replacement draw)
    assert len(alice_after_kan.tiles) == 11

    # All tiles in hand must be unique tile types won't have 5 of same
    tile_34_counts: dict[int, int] = {}
    for tile_id in alice_after_kan.tiles:
        t34 = tile_to_34(tile_id)
        tile_34_counts[t34] = tile_34_counts.get(t34, 0) + 1

    for t34, count in tile_34_counts.items():
        assert count <= 4, f"tile_34={t34} appears {count} times in hand"


def test_added_kan__when_replayed__should_reveal_dora_after_replacement_discard():
    replay = ReplayInput(
        seed=SEED,
        player_names=PLAYERS,
        settings=GameSettings(),
        wall=_build_added_kan_wall(),
        events=_build_added_kan_events(),
    )
    trace = run_replay(replay)
    non_synthetic_steps = [s for s in trace.steps if not s.synthetic]
    kan_step = next(s for s in non_synthetic_steps if s.input_event.action == GameAction.CALL_KAN)
    kan_step_idx = non_synthetic_steps.index(kan_step)
    discard_after_kan = non_synthetic_steps[kan_step_idx + 1]
    # Kan step: dora is deferred, so NO DoraRevealedEvent
    kan_dora_events = [e for e in kan_step.emitted_events if e.type == EventType.DORA_REVEALED]
    assert len(kan_dora_events) == 0, "added kan should not reveal dora immediately"
    # Kan step: pending_dora_count should be incremented
    assert kan_step.state_after.round_state.wall.pending_dora_count == 1
    # Discard step after kan: DoraRevealedEvent should be emitted
    discard_dora_events = [e for e in discard_after_kan.emitted_events if e.type == EventType.DORA_REVEALED]
    assert len(discard_dora_events) == 1, "dora should be revealed after replacement discard"
    # Verify the revealed dora indicator tile
    dora_event = discard_dora_events[0]
    assert isinstance(dora_event, DoraRevealedEvent)
    assert dora_event.tile_id == SECOND_DORA_INDICATOR
    # After discard: dora_indicators should contain both the original and the kan dora
    round_state = discard_after_kan.state_after.round_state
    assert len(round_state.wall.dora_indicators) == 2
    assert round_state.wall.dora_indicators[0] == FIRST_DORA_INDICATOR
    assert round_state.wall.dora_indicators[1] == SECOND_DORA_INDICATOR
    # pending_dora_count should be back to 0
    assert round_state.wall.pending_dora_count == 0
