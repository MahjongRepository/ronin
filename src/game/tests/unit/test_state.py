"""
Unit tests for game state models.
"""

from mahjong.tile import TilesConverter

from game.logic.enums import GamePhase, MeldViewType, RoundPhase, WindName
from game.logic.meld_wrapper import FrozenMeld
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    get_player_view,
)


class TestDiscard:
    def test_create_basic_discard(self):
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        discard = Discard(tile_id=man_1m)
        assert discard.tile_id == man_1m
        assert discard.is_tsumogiri is False
        assert discard.is_riichi_discard is False

    def test_create_tsumogiri_discard(self):
        pin_1p = TilesConverter.string_to_136_array(pin="1")[0]
        discard = Discard(tile_id=pin_1p, is_tsumogiri=True)
        assert discard.tile_id == pin_1p
        assert discard.is_tsumogiri is True

    def test_create_riichi_discard(self):
        sou_1s = TilesConverter.string_to_136_array(sou="1")[0]
        discard = Discard(tile_id=sou_1s, is_riichi_discard=True)
        assert discard.tile_id == sou_1s
        assert discard.is_riichi_discard is True

    def test_create_tsumogiri_riichi_discard(self):
        east = TilesConverter.string_to_136_array(honors="1")[0]
        discard = Discard(tile_id=east, is_tsumogiri=True, is_riichi_discard=True)
        assert discard.tile_id == east
        assert discard.is_tsumogiri is True
        assert discard.is_riichi_discard is True


class TestMahjongPlayer:
    def test_create_human_player(self):
        player = MahjongPlayer(seat=0, name="Player1")
        assert player.seat == 0
        assert player.name == "Player1"
        assert player.tiles == ()
        assert player.discards == ()
        assert player.melds == ()
        assert player.is_riichi is False
        assert player.is_ippatsu is False
        assert player.is_daburi is False
        assert player.is_rinshan is False
        assert player.score == 25000

    def test_create_bot_player(self):
        player = MahjongPlayer(seat=1, name="Bot1")
        assert player.seat == 1
        assert player.name == "Bot1"

    def test_player_with_tiles(self):
        tiles = TilesConverter.string_to_136_array(man="123", pin="123", sou="123", honors="1115")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles))
        assert player.tiles == tuple(tiles)
        assert len(player.tiles) == 13

    def test_player_with_discards(self):
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        discards = (Discard(tile_id=man_1m), Discard(tile_id=man_2m, is_tsumogiri=True))
        player = MahjongPlayer(seat=0, name="Player1", discards=discards)
        assert len(player.discards) == 2
        assert player.discards[0].tile_id == man_1m
        assert player.discards[1].is_tsumogiri is True

    def test_player_with_melds(self):
        meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(man="111")[:3]),
            opened=True,
        )
        player = MahjongPlayer(seat=0, name="Player1", melds=(meld,))
        assert len(player.melds) == 1
        assert player.melds[0].type == FrozenMeld.PON

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
        assert state.wall == ()
        assert state.dead_wall == ()
        assert state.dora_indicators == ()
        assert state.players == ()
        assert state.dealer_seat == 0
        assert state.current_player_seat == 0
        assert state.round_wind == 0
        assert state.turn_count == 0
        assert state.all_discards == ()
        assert state.players_with_open_hands == ()
        assert state.phase == RoundPhase.WAITING

    def test_round_state_with_wall(self):
        wall = tuple(range(122))  # 136 - 14 dead wall tiles
        state = MahjongRoundState(wall=wall)
        assert len(state.wall) == 122

    def test_round_state_with_dead_wall(self):
        dead_wall = tuple(range(14))
        state = MahjongRoundState(dead_wall=dead_wall)
        assert len(state.dead_wall) == 14

    def test_round_state_with_players(self):
        players = (
            MahjongPlayer(seat=0, name="Player1"),
            MahjongPlayer(seat=1, name="Bot1"),
            MahjongPlayer(seat=2, name="Bot2"),
            MahjongPlayer(seat=3, name="Bot3"),
        )
        state = MahjongRoundState(players=players)
        assert len(state.players) == 4

    def test_round_state_with_wind(self):
        # south wind round
        state = MahjongRoundState(round_wind=1)
        assert state.round_wind == 1

    def test_round_state_phase_transitions(self):
        """Test that round state can be created with different phases."""
        state_waiting = MahjongRoundState(phase=RoundPhase.WAITING)
        assert state_waiting.phase == RoundPhase.WAITING

        state_playing = MahjongRoundState(phase=RoundPhase.PLAYING)
        assert state_playing.phase == RoundPhase.PLAYING

        state_finished = MahjongRoundState(phase=RoundPhase.FINISHED)
        assert state_finished.phase == RoundPhase.FINISHED


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
        """Test that game state can be created with different phases."""
        state_in_progress = MahjongGameState(game_phase=GamePhase.IN_PROGRESS)
        assert state_in_progress.game_phase == GamePhase.IN_PROGRESS

        state_finished = MahjongGameState(game_phase=GamePhase.FINISHED)
        assert state_finished.game_phase == GamePhase.FINISHED


class TestGetPlayerView:
    def _create_test_game_state(
        self,
        player1_discards: tuple[Discard, ...] = (),
        player2_melds: tuple[FrozenMeld, ...] = (),
        *,
        player1_is_riichi: bool = False,
        player0_discards: tuple[Discard, ...] = (),
    ):
        """Create a game state for testing."""
        haku = TilesConverter.string_to_136_array(honors="5")[0]
        players = (
            MahjongPlayer(
                seat=0,
                name="Player1",
                tiles=tuple(
                    TilesConverter.string_to_136_array(
                        man="123",
                        pin="123",
                        sou="123",
                        honors="1115",
                    )
                ),
                score=25000,
                discards=player0_discards,
            ),
            MahjongPlayer(
                seat=1,
                name="Bot1",
                tiles=(
                    *TilesConverter.string_to_136_array(man="112233")[1::2],
                    *TilesConverter.string_to_136_array(pin="112233")[1::2],
                    *TilesConverter.string_to_136_array(sou="112233")[1::2],
                    *TilesConverter.string_to_136_array(honors="222"),
                    TilesConverter.string_to_136_array(honors="55")[1],
                ),
                score=24000,
                discards=player1_discards,
                is_riichi=player1_is_riichi,
            ),
            MahjongPlayer(
                seat=2,
                name="Bot2",
                tiles=(
                    *TilesConverter.string_to_136_array(man="111222333")[2::3],
                    *TilesConverter.string_to_136_array(pin="111222333")[2::3],
                    *TilesConverter.string_to_136_array(sou="111222333")[2::3],
                    *TilesConverter.string_to_136_array(honors="333"),
                    TilesConverter.string_to_136_array(honors="555")[2],
                ),
                score=26000,
                melds=player2_melds,
            ),
            MahjongPlayer(
                seat=3,
                name="Bot3",
                tiles=(
                    *TilesConverter.string_to_136_array(man="111122223333")[3::4],
                    *TilesConverter.string_to_136_array(pin="111122223333")[3::4],
                    *TilesConverter.string_to_136_array(sou="111122223333")[3::4],
                    *TilesConverter.string_to_136_array(honors="444"),
                    TilesConverter.string_to_136_array(honors="5555")[3],
                ),
                score=25000,
            ),
        )

        round_state = MahjongRoundState(
            wall=tuple(range(84, 122)),  # remaining wall tiles
            dead_wall=tuple(range(122, 136)),
            dora_indicators=(haku,),  # haku as dora indicator
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

        assert view.seat == 0
        assert view.round_wind == WindName.EAST
        assert view.round_number == 0
        assert view.dealer_seat == 0
        assert view.current_player_seat == 0
        assert view.honba_sticks == 0
        assert view.riichi_sticks == 0
        assert view.phase == RoundPhase.PLAYING
        assert view.game_phase == GamePhase.IN_PROGRESS

    def test_view_contains_wall_count(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)
        assert view.wall_count == 38  # 122 - 84

    def test_view_contains_dora_indicators(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)
        haku = TilesConverter.string_to_136_array(honors="5")[0]
        assert len(view.dora_indicators) == 1
        assert view.dora_indicators[0] == haku

    def test_view_shows_own_hand(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)

        player_view = view.players[0]
        assert player_view.tiles is not None
        assert len(player_view.tiles) == 13
        assert player_view.tile_count == 13

    def test_view_hides_other_hands(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)

        # check that other players' hands are hidden
        for i in range(1, 4):
            player_view = view.players[i]
            assert player_view.tiles is None
            assert player_view.tile_count == 13

    def test_view_shows_all_player_scores(self):
        game_state = self._create_test_game_state()
        view = get_player_view(game_state, seat=0)

        assert view.players[0].score == 25000
        assert view.players[1].score == 24000
        assert view.players[2].score == 26000
        assert view.players[3].score == 25000

    def test_view_shows_discards(self):
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        pin_1p = TilesConverter.string_to_136_array(pin="1")[0]
        discards = (
            Discard(tile_id=man_1m),
            Discard(tile_id=pin_1p, is_tsumogiri=True),
        )
        game_state = self._create_test_game_state(player1_discards=discards)

        view = get_player_view(game_state, seat=0)
        bot1_discards = view.players[1].discards
        assert len(bot1_discards) == 2
        assert bot1_discards[0].tile_id == man_1m
        assert bot1_discards[0].is_tsumogiri is False
        assert bot1_discards[1].tile_id == pin_1p
        assert bot1_discards[1].is_tsumogiri is True

    def test_view_shows_melds(self):
        meld = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(TilesConverter.string_to_136_array(honors="111")[:3]),
            opened=True,
            from_who=0,
        )
        game_state = self._create_test_game_state(player2_melds=(meld,))

        view = get_player_view(game_state, seat=0)
        bot2_melds = view.players[2].melds
        assert len(bot2_melds) == 1
        assert bot2_melds[0].type == MeldViewType.PON
        assert bot2_melds[0].tile_ids == TilesConverter.string_to_136_array(honors="111")[:3]
        assert bot2_melds[0].opened is True

    def test_view_shows_riichi_status(self):
        game_state = self._create_test_game_state(player1_is_riichi=True)

        view = get_player_view(game_state, seat=0)
        assert view.players[0].is_riichi is False
        assert view.players[1].is_riichi is True

    def test_view_for_different_seats(self):
        game_state = self._create_test_game_state()

        # seat 0 sees their own hand
        view0 = get_player_view(game_state, seat=0)
        assert view0.players[0].tiles is not None
        assert view0.players[1].tiles is None

        # seat 1 sees their own hand
        view1 = get_player_view(game_state, seat=1)
        assert view1.players[0].tiles is None
        assert view1.players[1].tiles is not None

    def test_view_with_riichi_discard(self):
        man_1m = TilesConverter.string_to_136_array(man="1")[0]
        man_2m = TilesConverter.string_to_136_array(man="2")[0]
        discards = (
            Discard(tile_id=man_1m),
            Discard(tile_id=man_2m, is_riichi_discard=True),
        )
        game_state = self._create_test_game_state(player0_discards=discards)

        view = get_player_view(game_state, seat=0)
        player_discards = view.players[0].discards
        assert player_discards[0].is_riichi_discard is False
        assert player_discards[1].is_riichi_discard is True


class TestRoundPhaseEnum:
    def test_phase_values(self):
        assert RoundPhase.WAITING.value == "waiting"
        assert RoundPhase.PLAYING.value == "playing"
        assert RoundPhase.FINISHED.value == "finished"


class TestGamePhaseEnum:
    def test_phase_values(self):
        assert GamePhase.IN_PROGRESS.value == "in_progress"
        assert GamePhase.FINISHED.value == "finished"
