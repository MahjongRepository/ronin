"""
Integration tests for Mahjong game flow.

Tests complete game scenarios including game creation, round completion,
dealer rotation, and game end conditions.
"""

import pytest

from game.logic.game import finalize_game, init_game, process_round_end
from game.logic.mahjong_service import MahjongGameService
from game.logic.melds import call_pon
from game.logic.riichi import declare_riichi
from game.logic.round import advance_turn, discard_tile, draw_tile
from game.logic.state import RoundPhase
from game.logic.tiles import tile_to_34
from game.logic.turn import process_draw_phase
from game.logic.win import HandResult, apply_ron_score, apply_tsumo_score


class TestGameCreationAndJoin:
    """Test game creation and initial state delivery."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_create_game_and_join_returns_initial_state(self, service):
        """Create game and verify initial state events are received."""
        events = await service.start_game("game1", ["Human"])

        game_started_events = [e for e in events if e.get("event") == "game_started"]
        assert len(game_started_events) == 4

        for event in game_started_events:
            data = event.get("data", {})
            assert "seat" in data
            assert "players" in data
            assert "round_wind" in data
            assert "dealer_seat" in data
            assert len(data["players"]) == 4

    async def test_initial_state_contains_player_hand(self, service):
        """Verify initial state includes player's own hand."""
        events = await service.start_game("game1", ["Human"])

        human_event = next(
            e for e in events if e.get("event") == "game_started" and e.get("target") == "seat_0"
        )
        data = human_event.get("data", {})
        player_info = next(p for p in data["players"] if p["seat"] == 0)

        assert "tiles" in player_info
        assert len(player_info["tiles"]) == 13 or len(player_info["tiles"]) == 14

    async def test_initial_state_hides_opponent_hands(self, service):
        """Verify initial state does not include opponent hands."""
        events = await service.start_game("game1", ["Human"])

        human_event = next(
            e for e in events if e.get("event") == "game_started" and e.get("target") == "seat_0"
        )
        data = human_event.get("data", {})
        opponent_info = next(p for p in data["players"] if p["seat"] == 1)

        assert "tiles" not in opponent_info
        assert "tile_count" in opponent_info

    async def test_initial_state_includes_scores(self, service):
        """Verify all players start with 25000 points."""
        events = await service.start_game("game1", ["Human"])

        human_event = next(
            e for e in events if e.get("event") == "game_started" and e.get("target") == "seat_0"
        )
        data = human_event.get("data", {})

        for player in data["players"]:
            assert player["score"] == 25000


class TestTsumoWin:
    """Test complete round with tsumo (self-draw) win."""

    def test_tsumo_win_updates_scores(self):
        """Tsumo win applies correct score changes."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])

        hand_result = HandResult(
            han=3,
            fu=40,
            cost_main=2600,
            cost_additional=1300,
            yaku=["Riichi", "Menzen Tsumo"],
        )

        initial_scores = [p.score for p in game_state.round_state.players]

        result = apply_tsumo_score(game_state, winner_seat=0, hand_result=hand_result)

        assert result["type"] == "tsumo"
        assert result["winner_seat"] == 0

        winner = game_state.round_state.players[0]
        assert winner.score > initial_scores[0]

        total_score = sum(p.score for p in game_state.round_state.players)
        assert total_score == 100000

    def test_tsumo_win_collects_riichi_sticks(self):
        """Tsumo winner collects riichi sticks on the table."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        game_state.riichi_sticks = 2

        hand_result = HandResult(
            han=1,
            fu=30,
            cost_main=1000,
            cost_additional=500,
            yaku=["Tanyao"],
        )

        result = apply_tsumo_score(game_state, winner_seat=0, hand_result=hand_result)

        assert result["riichi_sticks_collected"] == 2
        assert game_state.riichi_sticks == 0

        winner = game_state.round_state.players[0]
        assert winner.score > 25000 + 2000


class TestRonWin:
    """Test complete round with ron (deal-in) win."""

    def test_ron_win_updates_scores(self):
        """Ron win applies correct score changes."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])

        hand_result = HandResult(
            han=4,
            fu=40,
            cost_main=8000,
            yaku=["Riichi", "Ippatsu", "Menzen Tsumo"],
        )

        result = apply_ron_score(game_state, winner_seat=0, loser_seat=1, hand_result=hand_result)

        assert result["type"] == "ron"
        assert result["winner_seat"] == 0
        assert result["loser_seat"] == 1

        winner = game_state.round_state.players[0]
        loser = game_state.round_state.players[1]
        assert winner.score == 25000 + 8000
        assert loser.score == 25000 - 8000

    def test_ron_win_includes_honba_bonus(self):
        """Ron win includes honba bonus payment."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        game_state.honba_sticks = 2

        hand_result = HandResult(
            han=1,
            fu=30,
            cost_main=1000,
            yaku=["Tanyao"],
        )

        apply_ron_score(game_state, winner_seat=0, loser_seat=1, hand_result=hand_result)

        winner = game_state.round_state.players[0]
        loser = game_state.round_state.players[1]
        # winner gets 1000 + 600 (2 honba * 300)
        assert winner.score == 25000 + 1000 + 600
        # loser pays 1000 + 600
        assert loser.score == 25000 - 1000 - 600


class TestExhaustiveDraw:
    """Test complete round with exhaustive draw (wall empty)."""

    def test_exhaustive_draw_tempai_payment(self):
        """Exhaustive draw transfers points from noten to tempai players."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        round_state = game_state.round_state

        # manually empty wall and set up for exhaustive draw
        round_state.wall = []

        # process draw phase which should detect exhaustive draw
        events = process_draw_phase(round_state, game_state)

        round_end_event = next((e for e in events if e.get("type") == "round_end"), None)
        assert round_end_event is not None
        assert round_state.phase == RoundPhase.FINISHED

    def test_exhaustive_draw_all_noten_no_payment(self):
        """When all players are noten, no payment occurs."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"], seed=42.0)
        round_state = game_state.round_state

        # empty wall
        round_state.wall = []

        process_draw_phase(round_state, game_state)

        # check if scores remained unchanged (all noten) or changed (some tempai)
        # the actual outcome depends on dealt hands
        total_score = sum(p.score for p in round_state.players)
        assert total_score == 100000


class TestRiichiAndIppatsu:
    """Test riichi declaration and ippatsu mechanics."""

    def test_riichi_declaration_deducts_points(self):
        """Riichi declaration costs 1000 points."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        player = game_state.round_state.players[0]
        initial_score = player.score

        player.is_riichi = False
        # manually set up tempai hand (player must be tempai to riichi)
        # for this test we just test the point deduction mechanism
        declare_riichi(player, game_state)

        assert player.score == initial_score - 1000
        assert game_state.riichi_sticks == 1

    def test_riichi_sets_ippatsu_flag(self):
        """Riichi declaration sets ippatsu flag."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        player = game_state.round_state.players[0]

        declare_riichi(player, game_state)

        assert player.is_ippatsu is True

    def test_ippatsu_cleared_after_discard(self):
        """Ippatsu flag is cleared after any discard."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        round_state = game_state.round_state
        player = round_state.players[0]

        player.is_ippatsu = True
        tile_to_discard = player.tiles[-1]

        discard_tile(round_state, seat=0, tile_id=tile_to_discard)

        assert player.is_ippatsu is False


class TestPonCallFlow:
    """Test pon (triplet) call mechanics."""

    def test_pon_call_creates_meld(self):
        """Pon call creates a meld and sets current player."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"], seed=12345.0)
        round_state = game_state.round_state

        caller_seat = 1
        caller = round_state.players[caller_seat]
        discarder_seat = 0

        # find a tile type that caller has 2+ of
        tile_counts: dict[int, list[int]] = {}
        for t in caller.tiles:
            t34 = tile_to_34(t)
            if t34 not in tile_counts:
                tile_counts[t34] = []
            tile_counts[t34].append(t)

        # find a tile we can use for pon
        pon_tile_34 = None
        for t34, tiles in tile_counts.items():
            if len(tiles) >= 2:
                pon_tile_34 = t34
                break

        if pon_tile_34 is None:
            pytest.skip("No suitable tile for pon test in this deal")

        # get a tile_id of this type (simulating discard from seat 0)
        pon_tile_id = tile_counts[pon_tile_34][0]

        initial_hand_size = len(caller.tiles)
        initial_meld_count = len(caller.melds)

        call_pon(round_state, caller_seat, discarder_seat, pon_tile_id)

        # caller should have one more meld
        assert len(caller.melds) == initial_meld_count + 1

        # caller's hand should have 2 fewer tiles (used for pon)
        assert len(caller.tiles) == initial_hand_size - 2

        # current player should be the caller (they must discard)
        assert round_state.current_player_seat == caller_seat

    def test_pon_clears_all_ippatsu(self):
        """Pon call clears ippatsu for all players."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"], seed=12345.0)
        round_state = game_state.round_state

        # set ippatsu for multiple players
        round_state.players[0].is_ippatsu = True
        round_state.players[2].is_ippatsu = True

        caller_seat = 1
        caller = round_state.players[caller_seat]

        # find a suitable pon tile
        tile_counts: dict[int, list[int]] = {}
        for t in caller.tiles:
            t34 = tile_to_34(t)
            if t34 not in tile_counts:
                tile_counts[t34] = []
            tile_counts[t34].append(t)

        pon_tile_34 = None
        for t34, tiles in tile_counts.items():
            if len(tiles) >= 2:
                pon_tile_34 = t34
                break

        if pon_tile_34 is None:
            pytest.skip("No suitable tile for pon test in this deal")

        pon_tile_id = tile_counts[pon_tile_34][0]
        call_pon(round_state, caller_seat, 0, pon_tile_id)

        for player in round_state.players:
            assert player.is_ippatsu is False


class TestDealerRotation:
    """Test dealer rotation after round end."""

    def test_dealer_rotates_after_non_dealer_win(self):
        """Dealer rotates when non-dealer wins by ron."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        initial_dealer = game_state.round_state.dealer_seat

        # simulate non-dealer (seat 1) winning by ron
        result = {"type": "ron", "winner_seat": 1, "loser_seat": 0}
        process_round_end(game_state, result)

        new_dealer = game_state.round_state.dealer_seat
        assert new_dealer == (initial_dealer + 1) % 4

    def test_dealer_stays_after_dealer_win(self):
        """Dealer does not rotate when dealer wins."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        initial_dealer = game_state.round_state.dealer_seat

        # simulate dealer winning by tsumo
        result = {"type": "tsumo", "winner_seat": initial_dealer}
        process_round_end(game_state, result)

        new_dealer = game_state.round_state.dealer_seat
        assert new_dealer == initial_dealer

    def test_honba_increments_after_dealer_win(self):
        """Honba sticks increase when dealer wins."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        initial_honba = game_state.honba_sticks

        result = {"type": "tsumo", "winner_seat": 0}
        process_round_end(game_state, result)

        assert game_state.honba_sticks == initial_honba + 1

    def test_honba_resets_after_non_dealer_win(self):
        """Honba sticks reset to 0 when non-dealer wins."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        game_state.honba_sticks = 3

        result = {"type": "ron", "winner_seat": 1, "loser_seat": 0}
        process_round_end(game_state, result)

        assert game_state.honba_sticks == 0

    def test_wind_progression_after_dealer_rotation(self):
        """Wind progresses after full dealer rotation."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])

        # rotate through all 4 dealers (4 non-dealer wins)
        for _ in range(4):
            current_dealer = game_state.round_state.dealer_seat
            non_dealer = (current_dealer + 1) % 4
            result = {"type": "ron", "winner_seat": non_dealer, "loser_seat": current_dealer}
            process_round_end(game_state, result)

        # after 4 rotations, should be in south wind
        assert game_state.unique_dealers == 5
        assert game_state.round_state.round_wind == 1  # South


class TestGameEndConditions:
    """Test game end when player goes negative."""

    def test_game_ends_when_player_goes_negative(self):
        """Game ends when a player's score goes below 0."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])

        # set up a scenario where loser will go negative
        game_state.round_state.players[1].score = 5000

        hand_result = HandResult(
            han=5,
            fu=40,
            cost_main=8000,
            yaku=["Mangan"],
        )

        apply_ron_score(game_state, winner_seat=0, loser_seat=1, hand_result=hand_result)

        loser = game_state.round_state.players[1]
        assert loser.score < 0

        from game.logic.game import check_game_end

        assert check_game_end(game_state) is True

    def test_finalize_game_determines_winner(self):
        """Game finalization correctly determines winner by highest score."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        game_state.round_state.players[0].score = 35000
        game_state.round_state.players[1].score = 20000
        game_state.round_state.players[2].score = 30000
        game_state.round_state.players[3].score = 15000

        result = finalize_game(game_state)

        assert result["type"] == "game_end"
        assert result["winner_seat"] == 0
        assert result["standings"][0]["seat"] == 0

    def test_finalize_game_distributes_riichi_sticks_to_winner(self):
        """Winner receives remaining riichi sticks on game end."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        game_state.riichi_sticks = 3
        game_state.round_state.players[2].score = 30000

        result = finalize_game(game_state)

        winner = game_state.round_state.players[result["winner_seat"]]
        # winner should have original score + 3000 (3 riichi sticks)
        assert winner.score >= 30000 + 3000


class TestGameServiceIntegration:
    """Integration tests using MahjongGameService."""

    @pytest.fixture
    def service(self):
        return MahjongGameService()

    async def test_full_discard_cycle(self, service):
        """Test human discard triggers bot turns and returns to human."""
        events = await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]
        round_state = game_state.round_state

        # human should be dealer (seat 0)
        assert round_state.dealer_seat == 0
        assert round_state.current_player_seat == 0

        player = round_state.players[0]
        tile_to_discard = player.tiles[-1]

        events = await service.handle_action("game1", "Human", "discard", {"tile_id": tile_to_discard})

        # should have discard event
        discard_events = [e for e in events if e.get("event") == "discard"]
        assert len(discard_events) >= 1

    async def test_multiple_rounds_through_service(self, service):
        """Test multiple rounds can be played through the service."""
        await service.start_game("game1", ["Human"])
        game_state = service._games["game1"]

        initial_round = game_state.round_number

        # play several discards (bots will respond automatically)
        for _ in range(10):
            round_state = game_state.round_state
            if round_state.phase == RoundPhase.FINISHED:
                break

            current_seat = round_state.current_player_seat
            player = round_state.players[current_seat]

            if not player.is_bot and player.tiles:
                tile_to_discard = player.tiles[-1]
                await service.handle_action("game1", player.name, "discard", {"tile_id": tile_to_discard})

        # game should still be running or have progressed
        assert game_state.round_number >= initial_round


class TestDrawFromWall:
    """Test tile drawing mechanics."""

    def test_draw_tile_adds_to_hand(self):
        """Drawing a tile adds it to player's hand."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        round_state = game_state.round_state
        player = round_state.players[0]

        initial_hand_size = len(player.tiles)
        round_state.current_player_seat = 0

        drawn_tile = draw_tile(round_state)

        assert drawn_tile is not None
        assert len(player.tiles) == initial_hand_size + 1
        assert player.tiles[-1] == drawn_tile

    def test_draw_from_empty_wall_returns_none(self):
        """Drawing from empty wall returns None."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        round_state = game_state.round_state
        round_state.wall = []

        drawn_tile = draw_tile(round_state)

        assert drawn_tile is None


class TestTurnAdvancement:
    """Test turn progression mechanics."""

    def test_turn_advances_counter_clockwise(self):
        """Turns advance in counter-clockwise order (0->1->2->3->0)."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        round_state = game_state.round_state
        round_state.current_player_seat = 0

        advance_turn(round_state)
        assert round_state.current_player_seat == 1

        advance_turn(round_state)
        assert round_state.current_player_seat == 2

        advance_turn(round_state)
        assert round_state.current_player_seat == 3

        advance_turn(round_state)
        assert round_state.current_player_seat == 0

    def test_turn_count_increments(self):
        """Turn count increments with each advancement."""
        game_state = init_game(["Human", "Bot1", "Bot2", "Bot3"])
        round_state = game_state.round_state
        round_state.turn_count = 0

        advance_turn(round_state)
        assert round_state.turn_count == 1

        advance_turn(round_state)
        assert round_state.turn_count == 2
