"""
Unit tests for game state models.
"""

from mahjong.meld import Meld

from game.logic.state import (
    Discard,
    GamePhase,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    RoundPhase,
    get_player_view,
)


class TestDiscard:
    def test_create_basic_discard(self):
        discard = Discard(tile_id=0)
        assert discard.tile_id == 0
        assert discard.is_tsumogiri is False
        assert discard.is_riichi_discard is False

    def test_create_tsumogiri_discard(self):
        discard = Discard(tile_id=36, is_tsumogiri=True)
        assert discard.tile_id == 36
        assert discard.is_tsumogiri is True

    def test_create_riichi_discard(self):
        discard = Discard(tile_id=72, is_riichi_discard=True)
        assert discard.tile_id == 72
        assert discard.is_riichi_discard is True

    def test_create_tsumogiri_riichi_discard(self):
        discard = Discard(tile_id=108, is_tsumogiri=True, is_riichi_discard=True)
        assert discard.tile_id == 108
        assert discard.is_tsumogiri is True
        assert discard.is_riichi_discard is True


class TestMahjongPlayer:
    def test_create_human_player(self):
        player = MahjongPlayer(seat=0, name="Player1")
        assert player.seat == 0
        assert player.name == "Player1"
        assert player.is_bot is False
        assert player.tiles == []
        assert player.discards == []
        assert player.melds == []
        assert player.is_riichi is False
        assert player.is_ippatsu is False
        assert player.is_daburi is False
        assert player.is_rinshan is False
        assert player.score == 25000

    def test_create_bot_player(self):
        player = MahjongPlayer(seat=1, name="Bot1", is_bot=True)
        assert player.seat == 1
        assert player.name == "Bot1"
        assert player.is_bot is True

    def test_player_with_tiles(self):
        tiles = [0, 4, 8, 36, 40, 44, 72, 76, 80, 108, 109, 110, 124]
        player = MahjongPlayer(seat=0, name="Player1", tiles=tiles)
        assert player.tiles == tiles
        assert len(player.tiles) == 13

    def test_player_with_discards(self):
        discards = [Discard(tile_id=0), Discard(tile_id=4, is_tsumogiri=True)]
        player = MahjongPlayer(seat=0, name="Player1", discards=discards)
        assert len(player.discards) == 2
        assert player.discards[0].tile_id == 0
        assert player.discards[1].is_tsumogiri is True

    def test_player_with_melds(self):
        meld = Meld()
        meld.type = Meld.PON
        meld.tiles = [0, 1, 2]
        meld.opened = True
        player = MahjongPlayer(seat=0, name="Player1", melds=[meld])
        assert len(player.melds) == 1
        assert player.melds[0].type == Meld.PON

    def test_player_riichi_state(self):
        player = MahjongPlayer(seat=0, name="Player1", is_riichi=True, is_ippatsu=True, is_daburi=True)
        assert player.is_riichi is True
        assert player.is_ippatsu is True
        assert player.is_daburi is True

    def test_player_custom_score(self):
        player = MahjongPlayer(seat=0, name="Player1", score=30000)
        assert player.score == 30000


class TestMahjongRoundState:
    def test_create_default_round_state(self):
        state = MahjongRoundState()
        assert state.wall == []
        assert state.dead_wall == []
        assert state.dora_indicators == []
        assert state.players == []
        assert state.dealer_seat == 0
        assert state.current_player_seat == 0
        assert state.round_wind == 0
        assert state.turn_count == 0
        assert state.all_discards == []
        assert state.players_with_open_hands == []
        assert state.phase == RoundPhase.WAITING

    def test_round_state_with_wall(self):
        wall = list(range(122))  # 136 - 14 dead wall tiles
        state = MahjongRoundState(wall=wall)
        assert len(state.wall) == 122

    def test_round_state_with_dead_wall(self):
        dead_wall = list(range(14))
        state = MahjongRoundState(dead_wall=dead_wall)
        assert len(state.dead_wall) == 14

    def test_round_state_with_players(self):
        players = [
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1", is_bot=True),
            MahjongPlayer(seat=2, name="Bot2", is_bot=True),
            MahjongPlayer(seat=3, name="Bot3", is_bot=True),
        ]
        state = MahjongRoundState(players=players)
        assert len(state.players) == 4
        assert state.players[0].is_bot is False
        assert state.players[1].is_bot is True

    def test_round_state_with_wind(self):
        # south wind round
        state = MahjongRoundState(round_wind=1)
        assert state.round_wind == 1

    def test_round_state_phase_transitions(self):
        state = MahjongRoundState()
        assert state.phase == RoundPhase.WAITING
        state.phase = RoundPhase.PLAYING
        assert state.phase == RoundPhase.PLAYING
        state.phase = RoundPhase.FINISHED
        assert state.phase == RoundPhase.FINISHED


class TestMahjongGameState:
    def test_create_default_game_state(self):
        state = MahjongGameState()
        assert state.round_state is not None
        assert state.round_number == 0
        assert state.unique_dealers == 1
        assert state.honba_sticks == 0
        assert state.riichi_sticks == 0
        assert state.game_phase == GamePhase.IN_PROGRESS
        assert state.seed == 0.0

    def test_game_state_with_custom_values(self):
        state = MahjongGameState(
            round_number=4,
            unique_dealers=5,
            honba_sticks=2,
            riichi_sticks=3,
            seed=12345.0,
        )
        assert state.round_number == 4
        assert state.unique_dealers == 5
        assert state.honba_sticks == 2
        assert state.riichi_sticks == 3
        assert state.seed == 12345.0

    def test_game_state_with_round_state(self):
        round_state = MahjongRoundState(dealer_seat=2, round_wind=1)
        state = MahjongGameState(round_state=round_state)
        assert state.round_state.dealer_seat == 2
        assert state.round_state.round_wind == 1

    def test_game_state_phase_transitions(self):
        state = MahjongGameState()
        assert state.game_phase == GamePhase.IN_PROGRESS
        state.game_phase = GamePhase.FINISHED
        assert state.game_phase == GamePhase.FINISHED


class TestGetPlayerView:
    def _create_test_game_state(self):
        """Create a game state for testing."""
        players = [
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=[0, 4, 8, 36, 40, 44, 72, 76, 80, 108, 109, 110, 124],
                score=25000,
            ),
            MahjongPlayer(
                seat=1,
                name="Bot1",
                is_bot=True,
                tiles=[1, 5, 9, 37, 41, 45, 73, 77, 81, 112, 113, 114, 125],
                score=24000,
            ),
            MahjongPlayer(
                seat=2,
                name="Bot2",
                is_bot=True,
                tiles=[2, 6, 10, 38, 42, 46, 74, 78, 82, 116, 117, 118, 126],
                score=26000,
            ),
            MahjongPlayer(
                seat=3,
                name="Bot3",
                is_bot=True,
                tiles=[3, 7, 11, 39, 43, 47, 75, 79, 83, 120, 121, 122, 127],
                score=25000,
            ),
        ]

        round_state = MahjongRoundState(
            wall=list(range(84, 122)),  # remaining wall tiles
            dead_wall=list(range(122, 136)),
            dora_indicators=[124],  # haku as dora indicator
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,  # east
            phase=RoundPhase.PLAYING,
        )

        return MahjongGameState(
            round_state=round_state,
            round_number=0,
            honba_sticks=0,
            riichi_sticks=0,
        )

    def test_view_contains_basic_info(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)

        assert view["seat"] == 0
        assert view["round_wind"] == "East"
        assert view["round_number"] == 0
        assert view["dealer_seat"] == 0
        assert view["current_player_seat"] == 0
        assert view["honba_sticks"] == 0
        assert view["riichi_sticks"] == 0
        assert view["phase"] == "playing"
        assert view["game_phase"] == "in_progress"

    def test_view_contains_wall_count(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)
        assert view["wall_count"] == 38  # 122 - 84

    def test_view_contains_dora_indicators(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)
        assert len(view["dora_indicators"]) == 1
        assert view["dora_indicators"][0]["tile"] == "Haku"
        assert view["dora_indicators"][0]["tile_id"] == 124

    def test_view_shows_own_hand(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)

        player_view = view["players"][0]
        assert "tiles" in player_view
        assert len(player_view["tiles"]) == 13
        assert "hand" in player_view
        assert player_view["tile_count"] == 13

    def test_view_hides_other_hands(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)

        # check that other players' hands are hidden
        for i in range(1, 4):
            player_view = view["players"][i]
            assert "tiles" not in player_view
            assert "hand" not in player_view
            assert player_view["tile_count"] == 13

    def test_view_shows_all_player_scores(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)

        assert view["players"][0]["score"] == 25000
        assert view["players"][1]["score"] == 24000
        assert view["players"][2]["score"] == 26000
        assert view["players"][3]["score"] == 25000

    def test_view_shows_discards(self):
        game_state = self._create_test_game_state()
        # add some discards
        game_state.round_state.players[1].discards = [
            Discard(tile_id=0),
            Discard(tile_id=36, is_tsumogiri=True),
        ]

        view = get_player_view(game_state, seat=0)
        bot1_discards = view["players"][1]["discards"]
        assert len(bot1_discards) == 2
        assert bot1_discards[0]["tile"] == "1m"
        assert bot1_discards[0]["is_tsumogiri"] is False
        assert bot1_discards[1]["tile"] == "1p"
        assert bot1_discards[1]["is_tsumogiri"] is True

    def test_view_shows_melds(self):
        game_state = self._create_test_game_state()
        # add a pon meld
        meld = Meld()
        meld.type = Meld.PON
        meld.tiles = [108, 109, 110]
        meld.opened = True
        meld.from_who = 0
        game_state.round_state.players[2].melds = [meld]

        view = get_player_view(game_state, seat=0)
        bot2_melds = view["players"][2]["melds"]
        assert len(bot2_melds) == 1
        assert bot2_melds[0]["type"] == "pon"
        assert bot2_melds[0]["tiles"] == ["E", "E", "E"]
        assert bot2_melds[0]["opened"] is True

    def test_view_shows_riichi_status(self):
        game_state = self._create_test_game_state()
        game_state.round_state.players[1].is_riichi = True

        view = get_player_view(game_state, seat=0)
        assert view["players"][0]["is_riichi"] is False
        assert view["players"][1]["is_riichi"] is True

    def test_view_for_different_seats(self):
        game_state = self._create_test_game_state()

        # seat 0 sees their own hand
        view0 = get_player_view(game_state, seat=0)
        assert "tiles" in view0["players"][0]
        assert "tiles" not in view0["players"][1]

        # seat 1 sees their own hand
        view1 = get_player_view(game_state, seat=1)
        assert "tiles" not in view1["players"][0]
        assert "tiles" in view1["players"][1]

    def test_view_with_riichi_discard(self):
        game_state = self._create_test_game_state()
        game_state.round_state.players[0].discards = [
            Discard(tile_id=0),
            Discard(tile_id=4, is_riichi_discard=True),
        ]

        view = get_player_view(game_state, seat=0)
        discards = view["players"][0]["discards"]
        assert discards[0]["is_riichi_discard"] is False
        assert discards[1]["is_riichi_discard"] is True


class TestRoundPhaseEnum:
    def test_phase_values(self):
        assert RoundPhase.WAITING.value == "waiting"
        assert RoundPhase.PLAYING.value == "playing"
        assert RoundPhase.FINISHED.value == "finished"


class TestGamePhaseEnum:
    def test_phase_values(self):
        assert GamePhase.IN_PROGRESS.value == "in_progress"
        assert GamePhase.FINISHED.value == "finished"
