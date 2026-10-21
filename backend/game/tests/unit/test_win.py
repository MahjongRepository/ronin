from mahjong.tile import TilesConverter

from game.logic.meld_wrapper import FrozenMeld
from game.logic.riichi import can_declare_riichi
from game.logic.settings import GameSettings
from game.logic.state import (
    Discard,
    MahjongPlayer,
    MahjongRoundState,
)
from game.logic.wall import Wall
from game.logic.win import (
    apply_temporary_furiten,
    can_call_ron,
    can_declare_tsumo,
    check_tsumo,
    check_tsumo_with_tiles,
    get_waiting_tiles,
    is_chiihou,
    is_effective_furiten,
    is_furiten,
    is_renhou,
    is_tenhou,
)


class TestCheckTsumoMeldDedup:
    def test_check_tsumo__when_meld_tiles_still_in_hand__should_win(self):
        # meld tiles IN player.tiles (dedup path in all_player_tiles)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        all_tiles = closed_tiles + pon_tiles

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)
        assert check_tsumo(player) is True

    def test_check_tsumo__when_meld_tiles_absent_from_hand__should_win(self):
        # meld tiles NOT in player.tiles (actual gameplay after call_pon)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        assert check_tsumo(player) is True


class TestCheckTsumoWithTiles:
    def test_check_tsumo_with_tiles__when_ron_tile_and_meld__should_win(self):
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        pon_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        ron_tile = TilesConverter.string_to_136_array(sou="4")[0]
        tiles_with_ron = [*closed_tiles, ron_tile]

        assert check_tsumo_with_tiles(player, tiles_with_ron) is True


class TestCanDeclareTsumo:
    def _create_round_state(self, dealer_seat: int = 0) -> MahjongRoundState:
        return MahjongRoundState(
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(
                live_tiles=tuple(range(10)),
                dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            ),
        )

    def test_can_declare_tsumo__when_hand_not_winning__should_be_false(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), score=25000)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state, GameSettings()) is False

    def test_can_declare_tsumo__when_open_hand_has_yakuhai__should_be_true(self):
        # open hand with haku pon (yakuhai yaku exists)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state, GameSettings()) is True

    def test_can_declare_tsumo__when_open_hand_has_no_yaku__should_be_false(self):
        # open hand with pon of 1m, no yakuhai, no tanyao -> no yaku
        closed_tiles_before_win = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        win_tile = TilesConverter.string_to_136_array(man="5")[:1]
        pon_tiles = TilesConverter.string_to_136_array(man="111")

        all_tiles = closed_tiles_before_win + pon_tiles + win_tile

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state, GameSettings()) is False

    def test_can_declare_tsumo__when_open_tanyao_and_kuitan_enabled__should_be_true(self):
        # open tanyao (kuitan) - all simples with open meld
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        assert can_declare_tsumo(player, round_state, GameSettings()) is True


class TestGetWaitingTiles:
    def test_waiting_tiles__when_tempai_with_multiple_waits__should_list_all(self):
        # ryanmen wait: 123m 456m 789m 45p 5p -> waiting for 3p or 6p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="4555")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), score=25000)

        waiting = get_waiting_tiles(player)

        assert 11 in waiting  # 3p
        assert 14 in waiting  # 6p

    def test_waiting_tiles__when_tanki_wait__should_list_pair_tile(self):
        # tanki wait: 111m 222m 333m 444m 5m -> waiting for 5m
        tiles = TilesConverter.string_to_136_array(man="1112223334445")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), score=25000)

        waiting = get_waiting_tiles(player)

        assert 4 in waiting  # 5m

    def test_waiting_tiles__when_all_four_copies_held__should_exclude_tile(self):
        tiles = TilesConverter.string_to_136_array(man="111123", pin="456", sou="5578")
        player = MahjongPlayer(seat=0, name="Player0", tiles=tuple(tiles), score=25000)

        waiting = get_waiting_tiles(player)

        assert waiting == {23, 26}

    def test_waiting_tiles__when_chiitoitsu_tempai__should_list_wait(self):
        # 6 pairs + single: 11m 22m 33m 44p 55p 66s 7s -> waiting for 7s
        tiles = TilesConverter.string_to_136_array(man="112233", pin="4455", sou="667")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), score=25000)

        waiting = get_waiting_tiles(player)

        assert 24 in waiting  # 7s

    def test_waiting_tiles__when_open_pon_tiles_removed_from_hand__should_list_waits(self):
        # meld tiles NOT in player.tiles (actual gameplay after call_pon)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        pon_tiles = TilesConverter.string_to_136_array(pin="888")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)

        waiting = get_waiting_tiles(player)

        assert 18 in waiting  # 1s
        assert 21 in waiting  # 4s


class TestIsFuriten:
    def test_furiten__when_discards_not_waiting_tiles__should_be_false(self):
        # tempai waiting for 3p, discarded unrelated 1m
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        discards = (Discard(tile_id=TilesConverter.string_to_136_array(man="1")[0]),)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), discards=discards, score=25000)

        assert is_furiten(player) is False

    def test_furiten__when_waiting_tile_discarded__should_be_true(self):
        # tempai waiting for 3p, already discarded 3p
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        discards = (Discard(tile_id=TilesConverter.string_to_136_array(pin="3")[0]),)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), discards=discards, score=25000)

        assert is_furiten(player) is True

    def test_furiten__when_one_of_many_discards_is_waiting__should_be_true(self):
        # tempai waiting for 3p or 6p, discarded 6p (one of two waits)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="4555")
        discards = (
            Discard(tile_id=TilesConverter.string_to_136_array(man="1")[0]),
            Discard(tile_id=TilesConverter.string_to_136_array(pin="6")[0]),
        )
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), discards=discards, score=25000)

        assert is_furiten(player) is True

    def test_furiten__when_waiting_tile_only_in_kan__should_be_false(self):
        # player is tenpai waiting on 1m, has a closed kan of 1m-type tiles
        # kan tiles are in melds (not discards), so they should NOT cause furiten
        tiles = TilesConverter.string_to_136_array(man="234567", sou="23455")
        one_m_tiles = TilesConverter.string_to_136_array(man="1111")

        kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(one_m_tiles),
            opened=False,
        )

        # waiting on 1s and 4s (not 1m since we have kan of 1m), no discards
        player = MahjongPlayer(seat=0, name="P1", tiles=tuple(tiles), melds=(kan,), score=25000)

        assert is_furiten(player) is False

    def test_furiten__when_waiting_tile_discard_was_claimed__should_be_true(self):
        # a tile that was discarded and later claimed by another player
        # remains in the discarder's discard history and causes furiten
        # player waiting on 3p and 6p, discarded 3p previously
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="4555")
        discards = (Discard(tile_id=TilesConverter.string_to_136_array(pin="3")[0]),)
        player = MahjongPlayer(seat=0, name="P1", tiles=tuple(tiles), discards=discards, score=25000)

        # even if the 3p discard was claimed by another player (pon/chi), it's still in discards
        assert is_furiten(player) is True


class TestIsEffectiveFuriten:
    def test_effective_furiten__when_temporary_furiten_only__should_be_true(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(
            seat=0,
            name="P1",
            tiles=tuple(tiles),
            is_temporary_furiten=True,
            score=25000,
        )
        assert is_effective_furiten(player) is True

    def test_effective_furiten__when_riichi_furiten_only__should_be_true(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(
            seat=0,
            name="P1",
            tiles=tuple(tiles),
            is_riichi_furiten=True,
            score=25000,
        )
        assert is_effective_furiten(player) is True

    def test_effective_furiten__when_no_furiten_flags__should_be_false(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="P1", tiles=tuple(tiles), score=25000)
        assert is_effective_furiten(player) is False


class TestTemporaryFuritenResetOnDiscard:
    def test_temporary_furiten__when_active__should_block_ron(self):
        # player in temporary furiten cannot call ron
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(
            seat=1,
            name="P2",
            tiles=tuple(tiles),
            is_temporary_furiten=True,
            score=25000,
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(
                live_tiles=tuple(range(10)),
                dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            ),
        )
        ron_tile = TilesConverter.string_to_136_array(pin="3")[0]
        assert can_call_ron(player, ron_tile, round_state, GameSettings()) is False

    def test_temporary_furiten__when_active__should_allow_tsumo(self):
        # furiten player can still win by tsumo
        # hand: 123m 456m 789m 12p 55p + drawn 3p -> winning hand (14 tiles)
        closed_tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        win_tile = TilesConverter.string_to_136_array(pin="3")[0]
        tiles = (*closed_tiles, win_tile)

        player = MahjongPlayer(
            seat=0,
            name="P1",
            tiles=tiles,
            is_temporary_furiten=True,
            score=25000,
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(
                live_tiles=tuple(range(10)),
                dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            ),
            all_discards=(99,),
        )
        assert can_declare_tsumo(player, round_state, GameSettings()) is True


class TestRiichiFuritenPermanent:
    def test_riichi_furiten__when_active__should_block_ron(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(
            seat=1,
            name="P2",
            tiles=tuple(tiles),
            is_riichi=True,
            is_riichi_furiten=True,
            score=25000,
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(
                live_tiles=tuple(range(10)),
                dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            ),
        )
        ron_tile = TilesConverter.string_to_136_array(pin="3")[0]
        assert can_call_ron(player, ron_tile, round_state, GameSettings()) is False

    def test_riichi_furiten__when_active__should_allow_tsumo(self):
        # riichi furiten player can still win by tsumo
        # hand: 123m 456m 789m 12p 55p + drawn 3p -> winning hand (14 tiles)
        closed_tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        win_tile = TilesConverter.string_to_136_array(pin="3")[0]
        tiles = (*closed_tiles, win_tile)

        player = MahjongPlayer(
            seat=0,
            name="P1",
            tiles=tiles,
            is_riichi=True,
            is_riichi_furiten=True,
            score=25000,
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(
                live_tiles=tuple(range(10)),
                dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            ),
            all_discards=(99,),
        )
        assert can_declare_tsumo(player, round_state, GameSettings()) is True


class TestFuritenRiichiDeclarationAllowed:
    def test_declare_riichi__when_player_discard_furiten__should_be_allowed(self):
        # player waiting on 3p, discarded 3p -> discard furiten, but can still riichi
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        discards = (Discard(tile_id=TilesConverter.string_to_136_array(pin="3")[0]),)
        player = MahjongPlayer(
            seat=0,
            name="P1",
            tiles=tuple(tiles),
            discards=discards,
            score=25000,
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(live_tiles=tuple(range(10))),
        )
        # verify player IS in furiten
        assert is_furiten(player) is True
        # verify player CAN still declare riichi
        assert can_declare_riichi(player, round_state, GameSettings()) is True

    def test_declare_riichi__when_player_temporary_furiten__should_be_allowed(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(
            seat=0,
            name="P1",
            tiles=tuple(tiles),
            is_temporary_furiten=True,
            score=25000,
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(live_tiles=tuple(range(10))),
        )
        assert can_declare_riichi(player, round_state, GameSettings()) is True


class TestApplyTemporaryFuriten:
    def test_apply_temporary_furiten__when_applied__should_flag_only_that_seat(self):
        players = tuple(MahjongPlayer(seat=i, name=f"P{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        new_state = apply_temporary_furiten(round_state, 2)
        assert new_state.players[2].is_temporary_furiten is True
        # other players unaffected
        assert new_state.players[0].is_temporary_furiten is False
        assert new_state.players[1].is_temporary_furiten is False
        assert new_state.players[3].is_temporary_furiten is False


class TestCanCallRon:
    def _create_round_state(self, dealer_seat: int = 0) -> MahjongRoundState:
        return MahjongRoundState(
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(
                live_tiles=tuple(range(10)),
                dora_indicators=tuple(TilesConverter.string_to_136_array(man="1")),
            ),
        )

    def test_can_call_ron__when_furiten__should_be_false(self):
        # permanent furiten (discarded waiting tile 3p)
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        discards = (Discard(tile_id=TilesConverter.string_to_136_array(pin="3")[0]),)
        player = MahjongPlayer(
            seat=0,
            name="Player1",
            tiles=tuple(tiles),
            discards=discards,
            is_riichi=True,
            score=25000,
        )
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(pin="3")[0]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is False

    def test_can_call_ron__when_tile_not_waiting__should_be_false(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", pin="1255")
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(tiles), is_riichi=True, score=25000)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(sou="9")[0]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is False

    def test_can_call_ron__when_open_hand_has_yaku__should_be_true(self):
        # open hand with haku pon (yakuhai) via _has_yaku_for_ron_with_tiles
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")
        all_tiles = closed_tiles + haku_tiles

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(sou="4")[0]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is True

    def test_can_call_ron__when_open_hand_has_no_yaku__should_be_false(self):
        # open hand with pon of 1m, no yakuhai, no tanyao -> no yaku
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        all_tiles = closed_tiles + pon_tiles

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(man="6")[0]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is False

    def test_can_call_ron__when_open_tanyao__should_be_true(self):
        # open tanyao (kuitan) ron via _has_yaku_for_ron_with_tiles
        closed_tiles = TilesConverter.string_to_136_array(man="234567", pin="234", sou="5")
        pon_tiles = TilesConverter.string_to_136_array(sou="888")
        all_tiles = closed_tiles + pon_tiles

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(sou="55")[1]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is True

    def test_can_call_ron__when_meld_tiles_removed_from_hand__should_be_true(self):
        # meld tiles NOT in player.tiles (actual gameplay after call_pon)
        closed_tiles = TilesConverter.string_to_136_array(man="234567", sou="2355")
        haku_tiles = TilesConverter.string_to_136_array(honors="555")

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(haku_tiles),
            opened=True,
            called_tile=haku_tiles[0],
            who=0,
            from_who=1,
        )

        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(closed_tiles), melds=(pon,), score=25000)
        round_state = self._create_round_state()

        discarded_tile = TilesConverter.string_to_136_array(sou="4")[0]

        assert can_call_ron(player, discarded_tile, round_state, GameSettings()) is True


class TestIsTenhou:
    def test_tenhou__when_dealer_first_draw__should_be_true(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_tenhou(players[0], round_state) is True

    def test_tenhou__when_non_dealer__should_be_false(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_tenhou(players[1], round_state) is False

    def test_tenhou__when_discards_made__should_be_false(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(1,),
            players_with_open_hands=(),
        )
        assert is_tenhou(players[0], round_state) is False

    def test_tenhou__when_meld_made__should_be_false(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(1,),
        )
        assert is_tenhou(players[0], round_state) is False

    def test_tenhou__when_closed_kan_made__should_be_false(self):
        closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(man="1111")),
            opened=False,
        )
        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"Player{i}",
                melds=(closed_kan,) if i == 0 else (),
                score=25000,
            )
            for i in range(4)
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_tenhou(players[0], round_state) is False


class TestIsChiihou:
    def test_chiihou__when_non_dealer_first_draw__should_be_true(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_chiihou(players[1], round_state) is True

    def test_chiihou__when_dealer__should_be_false(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_chiihou(players[0], round_state) is False

    def test_chiihou__when_player_already_discarded__should_be_false(self):
        player_with_discard = MahjongPlayer(
            seat=1,
            name="Player1",
            score=25000,
            discards=(Discard(tile_id=1),),
        )
        players = (
            MahjongPlayer(seat=0, name="Player0", score=25000),
            player_with_discard,
            MahjongPlayer(seat=2, name="Player2", score=25000),
            MahjongPlayer(seat=3, name="Player3", score=25000),
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            players_with_open_hands=(),
        )
        assert is_chiihou(players[1], round_state) is False

    def test_chiihou__when_meld_made__should_be_false(self):
        players = tuple(MahjongPlayer(seat=i, name=f"Player{i}", score=25000) for i in range(4))
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(2,),
        )
        assert is_chiihou(players[1], round_state) is False

    def test_chiihou__when_dealer_made_closed_kan__should_be_false(self):
        closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(man="1111")),
            opened=False,
        )
        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"Player{i}",
                melds=(closed_kan,) if i == 0 else (),
                score=25000,
            )
            for i in range(4)
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=1,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_chiihou(players[1], round_state) is False


class TestIsRenhouClosedKan:
    def test_renhou__when_closed_kan_made__should_be_false(self):
        closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN,
            tiles=tuple(TilesConverter.string_to_136_array(man="1111")),
            opened=False,
        )
        players = tuple(
            MahjongPlayer(
                seat=i,
                name=f"Player{i}",
                melds=(closed_kan,) if i == 2 else (),
                score=25000,
            )
            for i in range(4)
        )
        round_state = MahjongRoundState(
            dealer_seat=0,
            current_player_seat=2,
            round_wind=0,
            players=players,
            all_discards=(),
            players_with_open_hands=(),
        )
        assert is_renhou(players[1], round_state) is False


class TestShibariDoraOnly:
    def _create_round_state(self, dora_indicator_tiles: tuple[int, ...]) -> MahjongRoundState:
        return MahjongRoundState(
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
            wall=Wall(
                live_tiles=tuple(range(10)),
                dora_indicators=dora_indicator_tiles,
            ),
            all_discards=(99,),
        )

    def test_shibari__when_open_hand_has_only_dora__should_reject_tsumo(self):
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        win_tile = TilesConverter.string_to_136_array(man="5")[:1]
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        all_tiles = closed_tiles + pon_tiles + win_tile

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        # dora indicator 4m -> 5m is dora; player has two 5m tiles
        dora_indicator = tuple(TilesConverter.string_to_136_array(man="4")[:1])
        round_state = self._create_round_state(dora_indicator)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)

        assert can_declare_tsumo(player, round_state, GameSettings()) is False

    def test_shibari__when_open_hand_has_only_dora__should_reject_ron(self):
        closed_tiles = TilesConverter.string_to_136_array(man="2345", pin="234", sou="567")
        pon_tiles = TilesConverter.string_to_136_array(man="111")
        all_tiles = closed_tiles + pon_tiles

        pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=0,
            from_who=1,
        )

        # dora indicator 4m -> 5m is dora
        dora_indicator = tuple(TilesConverter.string_to_136_array(man="4")[:1])
        round_state = self._create_round_state(dora_indicator)
        player = MahjongPlayer(seat=0, name="Player1", tiles=tuple(all_tiles), melds=(pon,), score=25000)

        # ron on 6m completes the hand (234m + 56m pair -> 23456m = 234m + 56m... no)
        # ron on 5m gives 55m pair: 111m(pon) + 234m + 234p + 567s + 55m
        ron_tile = TilesConverter.string_to_136_array(man="5")[0]

        assert can_call_ron(player, ron_tile, round_state, GameSettings()) is False
