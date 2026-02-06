"""
Unit tests for immutable turn processing functions.
"""

import pytest
from mahjong.tile import TilesConverter

from game.logic.enums import CallType, MeldCallType, RoundPhase, RoundResultType
from game.logic.state import (
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.turn import (
    emit_deferred_dora_events,
    process_discard_phase,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
    process_tsumo_call,
)
from game.messaging.events import (
    CallPromptEvent,
    DiscardEvent,
    DoraRevealedEvent,
    DrawEvent,
    MeldEvent,
    RiichiDeclaredEvent,
    RoundEndEvent,
    TurnEvent,
)


def _create_frozen_players() -> tuple[MahjongPlayer, ...]:
    """Create a tuple of frozen players for testing."""
    all_tiles = TilesConverter.string_to_136_array(man="123456789", pin="111")
    return tuple(
        MahjongPlayer(
            seat=i,
            name=f"Player{i}" if i == 0 else f"Bot{i}",
            tiles=tuple(all_tiles[i * 3 : (i + 1) * 3 + 10]),
            score=25000,
        )
        for i in range(4)
    )


def _create_frozen_round_state(
    wall: tuple[int, ...] | None = None,
    dead_wall: tuple[int, ...] | None = None,
    players: tuple[MahjongPlayer, ...] | None = None,
    current_player_seat: int = 0,
    pending_dora_count: int = 0,
) -> MahjongRoundState:
    """Create a frozen round state for testing."""
    if wall is None:
        wall = tuple(TilesConverter.string_to_136_array(man="1111222233334444"))
    if dead_wall is None:
        # 14 tiles for dead wall
        dead_wall = tuple(TilesConverter.string_to_136_array(sou="11112222333355"))
    if players is None:
        players = _create_frozen_players()

    return MahjongRoundState(
        wall=wall,
        dead_wall=dead_wall,
        dora_indicators=(dead_wall[2],) if len(dead_wall) > 2 else (),
        players=players,
        current_player_seat=current_player_seat,
        pending_dora_count=pending_dora_count,
        phase=RoundPhase.PLAYING,
    )


def _create_frozen_game_state(
    round_state: MahjongRoundState | None = None,
) -> MahjongGameState:
    """Create a frozen game state for testing."""
    if round_state is None:
        round_state = _create_frozen_round_state()
    return MahjongGameState(
        round_state=round_state,
        riichi_sticks=0,
        honba_sticks=0,
    )


class TestEmitDeferredDoraEventsImmutable:
    def test_emit_deferred_dora_events_with_pending_dora(self):
        """Pending dora should be revealed and emitted as events."""
        round_state = _create_frozen_round_state(pending_dora_count=1)
        initial_dora_count = len(round_state.dora_indicators)

        new_state, events = emit_deferred_dora_events(round_state)

        assert len(new_state.dora_indicators) == initial_dora_count + 1
        assert new_state.pending_dora_count == 0
        assert len(events) == 1
        assert isinstance(events[0], DoraRevealedEvent)
        # original state unchanged
        assert len(round_state.dora_indicators) == initial_dora_count
        assert round_state.pending_dora_count == 1

    def test_emit_deferred_dora_events_no_pending_dora(self):
        """No events should be emitted when pending_dora_count is 0."""
        round_state = _create_frozen_round_state(pending_dora_count=0)

        new_state, events = emit_deferred_dora_events(round_state)

        assert new_state.dora_indicators == round_state.dora_indicators
        assert len(events) == 0

    def test_emit_deferred_dora_events_multiple_pending(self):
        """Multiple pending dora should all be revealed."""
        round_state = _create_frozen_round_state(pending_dora_count=2)
        initial_dora_count = len(round_state.dora_indicators)

        new_state, events = emit_deferred_dora_events(round_state)

        assert len(new_state.dora_indicators) == initial_dora_count + 2
        assert new_state.pending_dora_count == 0
        assert len(events) == 2
        assert all(isinstance(e, DoraRevealedEvent) for e in events)


class TestProcessDrawPhaseImmutable:
    def test_draw_phase_draws_tile_and_emits_events(self):
        """Draw phase should draw a tile and emit DrawEvent and TurnEvent."""
        round_state = _create_frozen_round_state()
        game_state = _create_frozen_game_state(round_state)
        initial_wall_len = len(round_state.wall)
        initial_hand_len = len(round_state.players[0].tiles)

        new_round, _new_game, events = process_draw_phase(round_state, game_state)

        assert len(new_round.wall) == initial_wall_len - 1
        assert len(new_round.players[0].tiles) == initial_hand_len + 1
        # original state unchanged
        assert len(round_state.wall) == initial_wall_len
        assert len(round_state.players[0].tiles) == initial_hand_len

        # check events
        draw_events = [e for e in events if isinstance(e, DrawEvent)]
        assert len(draw_events) == 1
        assert draw_events[0].seat == 0

        turn_events = [e for e in events if isinstance(e, TurnEvent)]
        assert len(turn_events) == 1
        assert turn_events[0].current_seat == 0

    def test_draw_phase_exhaustive_draw_on_empty_wall(self):
        """Draw phase should handle exhaustive draw when wall is empty."""
        round_state = _create_frozen_round_state(wall=())
        game_state = _create_frozen_game_state(round_state)

        new_round, _new_game, events = process_draw_phase(round_state, game_state)

        assert new_round.phase == RoundPhase.FINISHED
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.EXHAUSTIVE_DRAW

    def test_draw_phase_does_not_mutate_original_state(self):
        """Draw phase should not mutate the original state."""
        round_state = _create_frozen_round_state()
        game_state = _create_frozen_game_state(round_state)
        original_wall_len = len(round_state.wall)
        original_tiles = round_state.players[0].tiles

        _new_round, _new_game, _events = process_draw_phase(round_state, game_state)

        # original state should be unchanged
        assert len(round_state.wall) == original_wall_len
        assert round_state.players[0].tiles == original_tiles


class TestProcessDiscardPhaseImmutable:
    def _create_state_with_hand(self):
        """Create a state where player 0 has tiles to discard."""
        players = []
        for i in range(4):
            tiles = tuple(TilesConverter.string_to_136_array(man="123456789111222")[:14])
            players.append(
                MahjongPlayer(
                    seat=i,
                    name=f"Player{i}" if i == 0 else f"Bot{i}",
                    tiles=tiles if i == 0 else (),
                    score=25000,
                )
            )
        round_state = _create_frozen_round_state(players=tuple(players))
        return round_state, _create_frozen_game_state(round_state)

    def test_discard_phase_removes_tile_and_emits_event(self):
        """Discard phase should remove tile from hand and emit DiscardEvent."""
        round_state, game_state = self._create_state_with_hand()
        tile_to_discard = round_state.players[0].tiles[0]

        new_round, _new_game, events = process_discard_phase(round_state, game_state, tile_to_discard)

        assert tile_to_discard not in new_round.players[0].tiles
        assert tile_to_discard in new_round.all_discards

        # original state unchanged
        assert tile_to_discard in round_state.players[0].tiles
        assert tile_to_discard not in round_state.all_discards

        # check events
        discard_events = [e for e in events if isinstance(e, DiscardEvent)]
        assert len(discard_events) == 1
        assert discard_events[0].tile_id == tile_to_discard

    def test_discard_phase_advances_turn_when_no_calls(self):
        """Discard phase should advance turn when no calls are available."""
        round_state, game_state = self._create_state_with_hand()
        tile_to_discard = round_state.players[0].tiles[0]

        new_round, _new_game, events = process_discard_phase(round_state, game_state, tile_to_discard)

        # if no call prompts, turn should advance
        call_prompts = [e for e in events if isinstance(e, CallPromptEvent)]
        if not call_prompts:
            assert new_round.current_player_seat == 1  # advanced from 0 to 1

    def test_discard_phase_reveals_pending_dora(self):
        """Discard phase should reveal pending dora when no ron calls."""
        players = []
        for i in range(4):
            tiles = tuple(TilesConverter.string_to_136_array(man="123456789111222")[:14])
            players.append(
                MahjongPlayer(
                    seat=i,
                    name=f"Player{i}" if i == 0 else f"Bot{i}",
                    tiles=tiles if i == 0 else (),
                    score=25000,
                )
            )
        round_state = _create_frozen_round_state(players=tuple(players), pending_dora_count=1)
        game_state = _create_frozen_game_state(round_state)
        initial_dora_count = len(round_state.dora_indicators)
        tile_to_discard = round_state.players[0].tiles[0]

        new_round, _new_game, events = process_discard_phase(round_state, game_state, tile_to_discard)

        # check for dora revealed events (if no ron prompt)
        ron_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.RON]
        if not ron_prompts:
            dora_events = [e for e in events if isinstance(e, DoraRevealedEvent)]
            assert len(dora_events) == 1
            assert len(new_round.dora_indicators) == initial_dora_count + 1

    def test_discard_phase_with_riichi_declaration(self):
        """Discard phase with riichi should declare riichi after discard."""
        # create tempai hand: 123m 456m 789m 111p -- waiting for 2p
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1113"))
        # add a drawn tile
        drawn_tile = TilesConverter.string_to_136_array(sou="5")[0]
        hand_tiles = (*hand_tiles, drawn_tile)

        players = [
            MahjongPlayer(
                seat=i,
                name=f"Player{i}" if i == 0 else f"Bot{i}",
                tiles=hand_tiles if i == 0 else (),
                score=25000,
            )
            for i in range(4)
        ]
        round_state = _create_frozen_round_state(players=tuple(players))
        game_state = _create_frozen_game_state(round_state)

        new_round, _new_game, events = process_discard_phase(
            round_state, game_state, drawn_tile, is_riichi=True
        )

        # check for riichi declared event (if no ron calls)
        ron_prompts = [e for e in events if isinstance(e, CallPromptEvent) and e.call_type == CallType.RON]
        if not ron_prompts:
            riichi_events = [e for e in events if isinstance(e, RiichiDeclaredEvent)]
            assert len(riichi_events) == 1
            assert riichi_events[0].seat == 0
            assert new_round.players[0].is_riichi is True

    def test_discard_phase_riichi_fails_when_not_tempai(self):
        """Discard phase with riichi should fail when player is not tempai."""
        players = []
        for i in range(4):
            # random hand, not tempai
            tiles = tuple(TilesConverter.string_to_136_array(man="135789", pin="246")[:14])
            players.append(
                MahjongPlayer(
                    seat=i,
                    name=f"Player{i}" if i == 0 else f"Bot{i}",
                    tiles=tiles if i == 0 else (),
                    score=25000,
                )
            )
        round_state = _create_frozen_round_state(players=tuple(players))
        game_state = _create_frozen_game_state(round_state)
        tile_to_discard = round_state.players[0].tiles[0]

        with pytest.raises(ValueError, match="cannot declare riichi"):
            process_discard_phase(round_state, game_state, tile_to_discard, is_riichi=True)

    def test_discard_phase_does_not_mutate_original_state(self):
        """Discard phase should not mutate the original state."""
        round_state, game_state = self._create_state_with_hand()
        original_tiles = round_state.players[0].tiles
        original_all_discards = round_state.all_discards
        tile_to_discard = round_state.players[0].tiles[0]

        _new_round, _new_game, _events = process_discard_phase(round_state, game_state, tile_to_discard)

        # original state should be unchanged
        assert round_state.players[0].tiles == original_tiles
        assert round_state.all_discards == original_all_discards


class TestProcessTsumoCallImmutable:
    def _create_winning_state(self):
        """Create a state where player 0 has a winning hand."""
        # 123m 456m 789m 12355p (pinfu hand, complete with 5p pair)
        hand_tiles = tuple(TilesConverter.string_to_136_array(man="123456789", pin="12355"))

        players = [
            MahjongPlayer(
                seat=i,
                name=f"Player{i}" if i == 0 else f"Bot{i}",
                tiles=hand_tiles if i == 0 else (),
                score=25000,
            )
            for i in range(4)
        ]
        round_state = _create_frozen_round_state(players=tuple(players))
        return round_state, _create_frozen_game_state(round_state)

    def test_tsumo_call_ends_round_with_win(self):
        """Tsumo call should end the round with a win result."""
        round_state, game_state = self._create_winning_state()

        new_round, _new_game, events = process_tsumo_call(round_state, game_state, winner_seat=0)

        assert new_round.phase == RoundPhase.FINISHED
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.TSUMO

    def test_tsumo_call_applies_score_changes(self):
        """Tsumo call should update player scores."""
        round_state, game_state = self._create_winning_state()
        initial_scores = [p.score for p in round_state.players]

        new_round, _new_game, _events = process_tsumo_call(round_state, game_state, winner_seat=0)

        # winner should have gained points
        assert new_round.players[0].score > initial_scores[0]
        # losers should have lost points
        for i in range(1, 4):
            assert new_round.players[i].score < initial_scores[i]

    def test_tsumo_call_does_not_mutate_original_state(self):
        """Tsumo call should not mutate the original state."""
        round_state, game_state = self._create_winning_state()
        original_scores = [p.score for p in round_state.players]

        _new_round, _new_game, _events = process_tsumo_call(round_state, game_state, winner_seat=0)

        # original state should be unchanged
        for i in range(4):
            assert round_state.players[i].score == original_scores[i]

    def test_tsumo_call_fails_when_not_winning_hand(self):
        """Tsumo call should fail when player doesn't have a winning hand."""
        players = []
        for i in range(4):
            # random hand, not winning
            tiles = tuple(TilesConverter.string_to_136_array(man="13579", pin="2468", sou="135")[:13])
            players.append(
                MahjongPlayer(
                    seat=i,
                    name=f"Player{i}" if i == 0 else f"Bot{i}",
                    tiles=tiles if i == 0 else (),
                    score=25000,
                )
            )
        round_state = _create_frozen_round_state(players=tuple(players))
        game_state = _create_frozen_game_state(round_state)

        with pytest.raises(ValueError, match="cannot declare tsumo"):
            process_tsumo_call(round_state, game_state, winner_seat=0)


class TestProcessRonCallImmutable:
    def _create_ron_state(self):
        """Create a state where player 1 can ron on player 0's discard."""
        # Player 1 has tempai hand: 123m 456m 789m 12p 55p - waiting for 3p
        # When ron tile (3p) is added, forms: 123m 456m 789m 123p 55p (ittsu hand)
        hand_tiles_1 = tuple(TilesConverter.string_to_136_array(man="123456789", pin="1255"))
        # Player 0 discards 3p
        discard_tile = TilesConverter.string_to_136_array(pin="3")[0]

        # tempai hand - win tile is NOT in hand, it's the discarded tile
        players = [
            MahjongPlayer(
                seat=i,
                name=f"Player{i}" if i == 0 else f"Bot{i}",
                tiles=hand_tiles_1 if i == 1 else (),
                score=25000,
            )
            for i in range(4)
        ]
        round_state = _create_frozen_round_state(players=tuple(players))
        return round_state, _create_frozen_game_state(round_state), discard_tile

    def test_ron_call_ends_round_with_win(self):
        """Ron call should end the round with a win result."""
        round_state, game_state, discard_tile = self._create_ron_state()

        new_round, _new_game, events = process_ron_call(
            round_state,
            game_state,
            ron_callers=[1],
            tile_id=discard_tile,
            discarder_seat=0,
        )

        assert new_round.phase == RoundPhase.FINISHED
        round_end_events = [e for e in events if isinstance(e, RoundEndEvent)]
        assert len(round_end_events) == 1
        assert round_end_events[0].result.type == RoundResultType.RON

    def test_ron_call_applies_score_changes(self):
        """Ron call should update player scores."""
        round_state, game_state, discard_tile = self._create_ron_state()
        initial_scores = [p.score for p in round_state.players]

        new_round, _new_game, _events = process_ron_call(
            round_state,
            game_state,
            ron_callers=[1],
            tile_id=discard_tile,
            discarder_seat=0,
        )

        # winner should have gained points
        assert new_round.players[1].score > initial_scores[1]
        # discarder should have lost points
        assert new_round.players[0].score < initial_scores[0]

    def test_ron_call_does_not_mutate_original_state(self):
        """Ron call should not mutate the original state."""
        round_state, game_state, discard_tile = self._create_ron_state()
        original_scores = [p.score for p in round_state.players]

        _new_round, _new_game, _events = process_ron_call(
            round_state,
            game_state,
            ron_callers=[1],
            tile_id=discard_tile,
            discarder_seat=0,
        )

        # original state should be unchanged
        for i in range(4):
            assert round_state.players[i].score == original_scores[i]

    def test_ron_call_uses_local_tile_copies(self):
        """Ron call should calculate hand value without mutating player.tiles."""
        round_state, game_state, discard_tile = self._create_ron_state()
        original_tiles = round_state.players[1].tiles

        _new_round, _new_game, _events = process_ron_call(
            round_state,
            game_state,
            ron_callers=[1],
            tile_id=discard_tile,
            discarder_seat=0,
        )

        # original player tiles should be unchanged (no append/remove)
        assert round_state.players[1].tiles == original_tiles


class TestProcessMeldCallImmutable:
    def _create_pon_state(self):
        """Create a state where player 1 can pon player 0's discard."""
        # Player 1 has two 1p tiles (indices 0,1 of pin="1111")
        all_1p = TilesConverter.string_to_136_array(pin="1111")
        hand_tiles_1 = (all_1p[0], all_1p[1], *TilesConverter.string_to_136_array(man="123456789"))
        # Player 0 discards 1p (third 1p, index 2)
        discard_tile = all_1p[2]

        players = []
        for i in range(4):
            if i == 1:
                tiles = hand_tiles_1
            elif i == 0:
                tiles = (discard_tile,)
            else:
                tiles = ()
            players.append(
                MahjongPlayer(
                    seat=i,
                    name=f"Player{i}" if i == 0 else f"Bot{i}",
                    tiles=tiles,
                    score=25000,
                )
            )
        round_state = _create_frozen_round_state(players=tuple(players))
        return round_state, _create_frozen_game_state(round_state), discard_tile

    def test_meld_call_pon_creates_meld_event(self):
        """Pon call should create a MeldEvent."""
        round_state, game_state, discard_tile = self._create_pon_state()

        _new_round, _new_game, events = process_meld_call(
            round_state,
            game_state,
            caller_seat=1,
            call_type=MeldCallType.PON,
            tile_id=discard_tile,
        )

        meld_events = [e for e in events if isinstance(e, MeldEvent)]
        assert len(meld_events) == 1
        assert meld_events[0].caller_seat == 1

    def test_meld_call_pon_removes_tiles_from_caller_hand(self):
        """Pon call should remove tiles from caller's hand."""
        round_state, game_state, discard_tile = self._create_pon_state()
        initial_hand_len = len(round_state.players[1].tiles)

        new_round, _new_game, _events = process_meld_call(
            round_state,
            game_state,
            caller_seat=1,
            call_type=MeldCallType.PON,
            tile_id=discard_tile,
        )

        # caller should have 2 fewer tiles (used for pon)
        assert len(new_round.players[1].tiles) == initial_hand_len - 2

    def test_meld_call_pon_sets_current_player_to_caller(self):
        """Pon call should set current player to caller."""
        round_state, game_state, discard_tile = self._create_pon_state()

        new_round, _new_game, _events = process_meld_call(
            round_state,
            game_state,
            caller_seat=1,
            call_type=MeldCallType.PON,
            tile_id=discard_tile,
        )

        assert new_round.current_player_seat == 1

    def test_meld_call_does_not_mutate_original_state(self):
        """Meld call should not mutate the original state."""
        round_state, game_state, discard_tile = self._create_pon_state()
        original_tiles = round_state.players[1].tiles
        original_melds = round_state.players[1].melds

        _new_round, _new_game, _events = process_meld_call(
            round_state,
            game_state,
            caller_seat=1,
            call_type=MeldCallType.PON,
            tile_id=discard_tile,
        )

        # original state should be unchanged
        assert round_state.players[1].tiles == original_tiles
        assert round_state.players[1].melds == original_melds
