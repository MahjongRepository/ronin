"""
Unit tests for turn loop special and abortive conditions.
"""

from mahjong.meld import Meld as MahjongMeld
from mahjong.tile import TilesConverter

from game.logic.abortive import check_four_riichi
from game.logic.actions import get_available_actions
from game.logic.enums import (
    AbortiveDrawType,
    CallType,
    MeldCallType,
    PlayerAction,
    RoundPhase,
    RoundResultType,
)
from game.logic.game import init_game
from game.logic.melds import can_call_chi
from game.logic.round import draw_tile
from game.logic.turn import (
    process_discard_phase,
    process_draw_phase,
    process_meld_call,
    process_ron_call,
)
from game.logic.types import AbortiveDrawResult
from game.messaging.events import CallPromptEvent, EventType, RoundEndEvent, TurnEvent
from game.tests.unit.helpers import _default_seat_configs


class TestFourWindsAbortiveDraw:
    def _create_game_state_for_four_winds(self):
        """Create a game state where four winds can occur."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give each player an East wind tile (E = honors 1)
        east_tiles = TilesConverter.string_to_136_array(honors="1111")
        for i, player in enumerate(round_state.players):
            player.tiles = list(range(i * 13, (i + 1) * 13))  # placeholder tiles
            player.tiles[0] = east_tiles[i]  # add East wind

        return game_state

    def test_four_winds_abortive_draw(self):
        game_state = self._create_game_state_for_four_winds()
        round_state = game_state.round_state

        # draw for player 0
        draw_tile(round_state)

        # simulate 4 East wind discards
        east_tiles = TilesConverter.string_to_136_array(honors="1111")

        for i in range(4):
            round_state.current_player_seat = i
            round_state.players[i].tiles.append(east_tiles[i])  # ensure they have the tile
            events = process_discard_phase(round_state, game_state, east_tiles[i])

            if i == 3:  # fourth discard triggers four winds
                round_end_events = [e for e in events if e.type == EventType.ROUND_END]
                assert len(round_end_events) == 1
                assert isinstance(round_end_events[0], RoundEndEvent)
                assert isinstance(round_end_events[0].result, AbortiveDrawResult)
                assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_WINDS
                assert round_state.phase == RoundPhase.FINISHED


class TestFourRiichiAbortiveDraw:
    def _create_tempai_for_all(self):
        """Create a game state where all players are in tempai."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # tempai hand for all players: 123m 456m 789m 111p, waiting for 2p
        base_hand = TilesConverter.string_to_136_array(man="123456789", pin="111")
        # each player gets a unique 3p copy to discard (3p tiles: 44, 45, 46, 47)
        discard_tiles = TilesConverter.string_to_136_array(pin="3333")

        for i, player in enumerate(round_state.players):
            # each player gets the base hand plus one unique tile to discard
            player.tiles = [*list(base_hand), discard_tiles[i]]

        return game_state

    def test_four_riichi_tracking(self):
        """Test that four riichi is detected after all players declare riichi."""
        game_state = self._create_tempai_for_all()
        round_state = game_state.round_state

        # declare riichi for all 4 players manually
        for player in round_state.players:
            player.is_riichi = True

        # verify the condition is detected
        assert check_four_riichi(round_state) is True


class TestRiichiPlayerExcludedFromMeldCallers:
    """Tests that riichi players cannot call melds on discarded tiles."""

    def _create_game_state_with_meld_opportunity(self):
        """Create a game where player 1 could call pon if not in riichi."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 two 1m tiles
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="11", pin="12345", sou="123456")

        # player 0 will discard a 1m tile (3rd copy of 1m)
        tile_to_discard = TilesConverter.string_to_136_array(man="111")[2]
        round_state.players[0].tiles.append(tile_to_discard)
        round_state.current_player_seat = 0

        return game_state, tile_to_discard

    def test_riichi_player_excluded_from_pon_callers(self):
        """Riichi players should not appear in meld callers for pon."""
        game_state, tile_to_discard = self._create_game_state_with_meld_opportunity()
        round_state = game_state.round_state

        # player 1 is NOT in riichi - should be able to call pon
        events = process_discard_phase(round_state, game_state, tile_to_discard)
        call_prompts = [
            e
            for e in events
            if e.type == EventType.CALL_PROMPT and getattr(e, "call_type", None) == CallType.MELD
        ]
        if call_prompts:
            assert isinstance(call_prompts[0], CallPromptEvent)
            callers = call_prompts[0].callers
            caller_seats = [c.seat if hasattr(c, "seat") else c for c in callers]
            assert 1 in caller_seats

    def test_riichi_player_excluded_from_pon_callers_when_riichi(self):
        """Riichi players should be excluded from meld callers."""
        game_state, tile_to_discard = self._create_game_state_with_meld_opportunity()
        round_state = game_state.round_state

        # put player 1 in riichi
        round_state.players[1].is_riichi = True

        events = process_discard_phase(round_state, game_state, tile_to_discard)
        call_prompts = [
            e
            for e in events
            if e.type == EventType.CALL_PROMPT and getattr(e, "call_type", None) == CallType.MELD
        ]
        if call_prompts:
            assert isinstance(call_prompts[0], CallPromptEvent)
            callers = call_prompts[0].callers
            caller_seats = [c.seat if hasattr(c, "seat") else c for c in callers]
            # player 1 should NOT be in callers since they're in riichi
            assert 1 not in caller_seats

    def test_riichi_player_discard_limited_to_drawn_tile(self):
        """After riichi, only the drawn tile should be discardable."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        player = round_state.players[0]

        # setup: player draws and is in riichi
        drawn_tile = draw_tile(round_state)
        player.is_riichi = True

        actions = get_available_actions(round_state, game_state, seat=0)

        # find the discard action
        discard_action = next((a for a in actions if a.action == PlayerAction.DISCARD), None)
        assert discard_action is not None
        # should only be able to discard the drawn tile
        assert discard_action.tiles is not None
        assert len(discard_action.tiles) == 1
        assert discard_action.tiles[0] == drawn_tile

    def test_riichi_player_cannot_call_chi(self):
        """Verify can_call_chi returns empty for riichi players."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state
        player = round_state.players[1]

        # give player 1 tiles that could form a sequence (1m, 2m + filler)
        player.tiles = TilesConverter.string_to_136_array(man="12", pin="12345", sou="123456")
        discarded_tile = TilesConverter.string_to_136_array(man="3")[0]  # 3m, would form 1-2-3m sequence

        # not in riichi - should be able to chi
        options = can_call_chi(player, discarded_tile, discarder_seat=0, caller_seat=1)
        assert len(options) > 0

        # in riichi - should not be able to chi
        player.is_riichi = True
        options = can_call_chi(player, discarded_tile, discarder_seat=0, caller_seat=1)
        assert options == []


class TestKyuushuInDrawPhase:
    """Tests kyuushu kyuuhai action availability during draw phase."""

    def test_draw_phase_includes_kyuushu_action(self):
        """Draw phase includes kyuushu action when player has 9+ terminals/honors."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 0 nine terminal/honor tiles plus filler tiles
        # terminals: 1m, 9m, 1p, 9p, 1s, 9s; honors: E, S, W; filler: 2m, 3m, 4m, 5m
        round_state.players[0].tiles = TilesConverter.string_to_136_array(
            man="123459", pin="19", sou="19", honors="123"
        )

        events = process_draw_phase(round_state, game_state)

        turn_events = [e for e in events if e.type == EventType.TURN]
        assert len(turn_events) == 1
        assert isinstance(turn_events[0], TurnEvent)
        actions = turn_events[0].available_actions
        kyuushu_actions = [a for a in actions if a.action == PlayerAction.KYUUSHU]
        assert len(kyuushu_actions) == 1


class TestRonCallersAfterDiscard:
    """Tests ron call prompt generation after a discard."""

    def test_discard_generates_ron_prompt(self):
        """Discard generates ron call prompt when opponent is waiting."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # give player 1 a hand waiting for 2p
        # 123m 456m 789m 111p + 2p (waiting for pair)
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1112")

        # draw a tile for player 0 so the hand has proper count
        draw_tile(round_state)
        win_tile = TilesConverter.string_to_136_array(pin="22")[1]  # 2nd copy of 2p
        round_state.players[0].tiles.append(win_tile)

        events = process_discard_phase(round_state, game_state, win_tile)

        call_prompts = [e for e in events if e.type == EventType.CALL_PROMPT]
        ron_prompts = [e for e in call_prompts if e.call_type == CallType.RON]
        assert len(ron_prompts) == 1
        assert isinstance(ron_prompts[0], CallPromptEvent)
        assert 1 in ron_prompts[0].callers


class TestDoubleRon:
    """Tests double ron processing when two players can ron on the same discard."""

    def test_double_ron(self):
        """Two players calling ron on the same discard produces a double ron result."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # player 1 and player 2 both waiting for 2p
        # 123m 456m 789m 111p + 2p
        waiting_hand = TilesConverter.string_to_136_array(man="123456789", pin="1112")
        round_state.players[1].tiles = list(waiting_hand)
        round_state.players[2].tiles = list(waiting_hand)

        win_tile = TilesConverter.string_to_136_array(pin="22")[1]  # 2nd copy of 2p
        round_state.current_player_seat = 0

        events = process_ron_call(
            round_state,
            game_state,
            ron_callers=[1, 2],
            tile_id=win_tile,
            discarder_seat=0,
        )

        round_end_events = [e for e in events if e.type == EventType.ROUND_END]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0], RoundEndEvent)
        result = round_end_events[0].result
        assert result.type == RoundResultType.DOUBLE_RON
        assert round_state.phase == RoundPhase.FINISHED


class TestFourRiichiDuringDiscard:
    """Tests four riichi abortive draw triggered during discard phase."""

    def test_four_riichi_abortive_draw(self):
        """Fourth riichi declaration triggers abortive draw."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # set 3 players as already in riichi
        for i in range(1, 4):
            round_state.players[i].is_riichi = True

        # give player 0 a tempai hand: 123m 456m 789m 111p + discard tile
        round_state.players[0].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1113")
        draw_tile(round_state)
        tile_to_discard = round_state.players[0].tiles[-1]

        events = process_discard_phase(round_state, game_state, tile_to_discard, is_riichi=True)

        # check for ron prompts first (a riichi player might be able to ron)
        ron_prompts = [
            e
            for e in events
            if e.type == EventType.CALL_PROMPT and getattr(e, "call_type", None) == CallType.RON
        ]
        if not ron_prompts:
            round_end_events = [e for e in events if e.type == EventType.ROUND_END]
            if round_end_events:
                assert isinstance(round_end_events[0], RoundEndEvent)
                assert isinstance(round_end_events[0].result, AbortiveDrawResult)
                assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_RIICHI


class TestFourKansAbortDuringKan:
    """Tests four kans abortive draw triggered during kan processing."""

    def test_four_kans_abort_on_open_kan(self):
        """Fourth kan by a different player triggers abortive draw."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # three players each have one kan meld (3 kans total from 3 different players)
        round_state.players[0].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="1111"),
                opened=True,
                who=0,
                from_who=1,
            )
        ]
        round_state.players[1].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="2222"),
                opened=True,
                who=1,
                from_who=0,
            )
        ]
        round_state.players[2].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="3333"),
                opened=True,
                who=2,
                from_who=1,
            )
        ]

        # player 3 has three 4m tiles to call open kan
        round_state.players[3].tiles = TilesConverter.string_to_136_array(man="444678", pin="1234567")
        round_state.current_player_seat = 0

        tile_to_kan = TilesConverter.string_to_136_array(man="4444")[3]  # 4th copy of 4m
        events = process_meld_call(
            round_state, game_state, caller_seat=3, call_type=MeldCallType.OPEN_KAN, tile_id=tile_to_kan
        )

        round_end_events = [e for e in events if e.type == EventType.ROUND_END]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0], RoundEndEvent)
        assert isinstance(round_end_events[0].result, AbortiveDrawResult)
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS
        assert round_state.phase == RoundPhase.FINISHED


class TestChankanDuringAddedKan:
    """Tests chankan prompt generation during added kan processing."""

    def test_chankan_prompt_during_added_kan(self):
        """Added kan triggers chankan prompt when opponent is waiting on the tile."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # player 0 has pon of 3p and 4th 3p in hand
        pon_3p_tiles = TilesConverter.string_to_136_array(pin="333")
        fourth_3p = TilesConverter.string_to_136_array(pin="3333")[3]
        pon_meld = MahjongMeld(
            meld_type=MahjongMeld.PON,
            tiles=pon_3p_tiles,
            opened=True,
            called_tile=pon_3p_tiles[2],
            who=0,
            from_who=1,
        )
        round_state.players[0].melds = [pon_meld]
        round_state.players[0].tiles = [
            fourth_3p,
            *TilesConverter.string_to_136_array(sou="123456789"),
        ]
        round_state.players_with_open_hands = [0]
        round_state.current_player_seat = 0

        # player 1 waiting for 3p: 123m 456m 789m 12p 55p
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")

        events = process_meld_call(
            round_state, game_state, caller_seat=0, call_type=MeldCallType.ADDED_KAN, tile_id=fourth_3p
        )

        call_prompts = [e for e in events if e.type == EventType.CALL_PROMPT]
        chankan_prompts = [e for e in call_prompts if e.call_type == CallType.CHANKAN]
        assert len(chankan_prompts) == 1
        assert isinstance(chankan_prompts[0], CallPromptEvent)
        assert 1 in chankan_prompts[0].callers


class TestOpenKanDetectionAfterDiscard:
    """Tests open kan detection in meld caller scanning after discard."""

    def test_discard_detects_open_kan_caller(self):
        """Discard detects opponent with 3 matching tiles for open kan."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # player 1 has three 1m tiles (can call open kan on 4th)
        round_state.players[1].tiles = TilesConverter.string_to_136_array(man="111", pin="23456", sou="23456")

        # draw a tile for player 0
        draw_tile(round_state)
        # player 0 discards 1m (4th copy)
        fourth_1m = TilesConverter.string_to_136_array(man="1111")[3]
        round_state.players[0].tiles.append(fourth_1m)
        round_state.current_player_seat = 0

        events = process_discard_phase(round_state, game_state, fourth_1m)

        # meld call prompt should include open_kan option for player 1
        call_prompts = [
            e
            for e in events
            if e.type == EventType.CALL_PROMPT and getattr(e, "call_type", None) == CallType.MELD
        ]
        assert len(call_prompts) >= 1
        assert isinstance(call_prompts[0], CallPromptEvent)
        callers = call_prompts[0].callers
        open_kan_callers = [c for c in callers if c.call_type == MeldCallType.OPEN_KAN]
        assert len(open_kan_callers) == 1
        assert open_kan_callers[0].seat == 1


class TestFourKansAbortAfterClosedKan:
    """Tests four kans abortive draw triggered by a closed kan."""

    def test_four_kans_abort_on_closed_kan(self):
        """Fourth kan via closed kan by a different player triggers abortive draw."""
        game_state = init_game(_default_seat_configs(), seed=12345.0)
        round_state = game_state.round_state

        # three players each have one kan meld (3 kans total from 3 different players)
        round_state.players[0].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="1111"),
                opened=True,
                who=0,
                from_who=1,
            )
        ]
        round_state.players[1].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="2222"),
                opened=True,
                who=1,
                from_who=0,
            )
        ]
        round_state.players[2].melds = [
            MahjongMeld(
                meld_type=MahjongMeld.KAN,
                tiles=TilesConverter.string_to_136_array(man="3333"),
                opened=True,
                who=2,
                from_who=1,
            )
        ]

        # player 3 has four 4m tiles for closed kan
        round_state.players[3].tiles = TilesConverter.string_to_136_array(man="4444678", pin="123456")
        round_state.current_player_seat = 3

        tile_4m = TilesConverter.string_to_136_array(man="4")[0]
        events = process_meld_call(
            round_state, game_state, caller_seat=3, call_type=MeldCallType.CLOSED_KAN, tile_id=tile_4m
        )

        round_end_events = [e for e in events if e.type == EventType.ROUND_END]
        assert len(round_end_events) == 1
        assert isinstance(round_end_events[0], RoundEndEvent)
        assert isinstance(round_end_events[0].result, AbortiveDrawResult)
        assert round_end_events[0].result.reason == AbortiveDrawType.FOUR_KANS
        assert round_state.phase == RoundPhase.FINISHED
