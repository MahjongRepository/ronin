from game.logic.meld_wrapper import FrozenMeld
from game.logic.state import Discard, MahjongPlayer, MahjongRoundState
from game.logic.tiles import tile_to_34
from game.logic.win import get_waiting_tiles, is_chankan_possible
from game.tests.conftest import create_dealt_game_state, create_player
from game.tests.helpers.hands import tile_copies

_KAN_CALLER = 2
_THREE_PIN = tuple(tile_copies(copy, pin="3")[0] for copy in range(4))
_PENCHAN_ON_THREE_PIN = tuple(tile_copies(0, man="123456789", pin="1255"))
_OTHER_PENCHAN_ON_THREE_PIN = (*tile_copies(1, man="123456789", pin="12"), *tile_copies(2, pin="55"))


def _added_kan_on_three_pin(*, seat_0: MahjongPlayer, seat_3: MahjongPlayer) -> MahjongRoundState:
    pon = FrozenMeld(
        meld_type=FrozenMeld.PON,
        tiles=_THREE_PIN[:3],
        opened=True,
        called_tile=_THREE_PIN[0],
        who=_KAN_CALLER,
        from_who=1,
    )
    players = (
        seat_0,
        create_player(
            seat=1,
            tiles=tile_copies(0, sou="123456789", honors="1234"),
            discards=(Discard(tile_id=_THREE_PIN[0]),),
        ),
        create_player(
            seat=_KAN_CALLER,
            tiles=(_THREE_PIN[3], *tile_copies(1, sou="123456789"), *tile_copies(0, honors="5")),
            melds=(pon,),
        ),
        seat_3,
    )
    return create_dealt_game_state(players, current_player_seat=_KAN_CALLER).round_state


def _bystander(seat: int) -> MahjongPlayer:
    copy = {0: 2, 3: 3}[seat]
    return create_player(seat=seat, tiles=tile_copies(copy, sou="123456789", honors="1234"))


class TestIsChankanPossible:
    def test_chankan__when_player_not_waiting_on_tile__should_not_be_possible(self):
        waiting_on_four_and_seven_pin = create_player(seat=0, tiles=tile_copies(0, man="123456789", pin="5677"))
        round_state = _added_kan_on_three_pin(seat_0=waiting_on_four_and_seven_pin, seat_3=_bystander(3))
        assert get_waiting_tiles(waiting_on_four_and_seven_pin) == {tile_to_34(t) for t in tile_copies(0, pin="47")}

        assert is_chankan_possible(round_state, caller_seat=_KAN_CALLER, kan_tile=_THREE_PIN[3]) == []

    def test_chankan__when_player_furiten__should_not_be_possible(self):
        six_pin = tile_copies(0, pin="6")[0]
        furiten_on_six_pin = create_player(
            seat=0,
            tiles=tile_copies(0, man="123456789", pin="4555"),
            discards=(Discard(tile_id=six_pin),),
        )
        round_state = _added_kan_on_three_pin(seat_0=furiten_on_six_pin, seat_3=_bystander(3))
        assert {tile_to_34(_THREE_PIN[0]), tile_to_34(six_pin)} <= get_waiting_tiles(furiten_on_six_pin)

        assert is_chankan_possible(round_state, caller_seat=_KAN_CALLER, kan_tile=_THREE_PIN[3]) == []

    def test_chankan__when_multiple_players_wait__should_return_all_in_head_bump_order(self):
        round_state = _added_kan_on_three_pin(
            seat_0=create_player(seat=0, tiles=_PENCHAN_ON_THREE_PIN),
            seat_3=create_player(seat=3, tiles=_OTHER_PENCHAN_ON_THREE_PIN),
        )

        assert is_chankan_possible(round_state, caller_seat=_KAN_CALLER, kan_tile=_THREE_PIN[3]) == [3, 0]

    def test_chankan__when_riichi_furiten__should_not_be_possible(self):
        riichi_furiten = create_player(
            seat=0,
            tiles=_PENCHAN_ON_THREE_PIN,
            discards=(Discard(tile_id=tile_copies(0, honors="7")[0], is_riichi_discard=True),),
            is_riichi=True,
            is_riichi_furiten=True,
        )
        round_state = _added_kan_on_three_pin(seat_0=riichi_furiten, seat_3=_bystander(3))

        assert is_chankan_possible(round_state, caller_seat=_KAN_CALLER, kan_tile=_THREE_PIN[3]) == []

    def test_chankan__when_temporary_furiten__should_not_be_possible(self):
        temporary_furiten = create_player(seat=3, tiles=_OTHER_PENCHAN_ON_THREE_PIN, is_temporary_furiten=True)
        round_state = _added_kan_on_three_pin(seat_0=_bystander(0), seat_3=temporary_furiten)

        assert is_chankan_possible(round_state, caller_seat=_KAN_CALLER, kan_tile=_THREE_PIN[3]) == []


class TestChankanWithOpenHand:
    def test_chankan__when_open_hand_only_has_chankan_yaku__should_be_possible(self):
        four_man = tuple(tile_copies(copy, man="4")[0] for copy in range(4))
        one_man_pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(tile_copies(0, man="111")),
            opened=True,
            called_tile=tile_copies(0, man="1")[0],
            who=1,
            from_who=0,
        )
        four_man_pon = FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=four_man[:3],
            opened=True,
            called_tile=four_man[0],
            who=_KAN_CALLER,
            from_who=3,
        )
        open_yakuless_wait = create_player(
            seat=1, tiles=tile_copies(0, man="23", pin="456", sou="67899"), melds=(one_man_pon,)
        )
        players = (
            create_player(
                seat=0,
                tiles=tile_copies(1, pin="123456789", honors="1234"),
                discards=(Discard(tile_id=one_man_pon.called_tile),),
            ),
            open_yakuless_wait,
            create_player(
                seat=_KAN_CALLER,
                tiles=(four_man[3], *tile_copies(2, pin="123456789"), *tile_copies(0, honors="5")),
                melds=(four_man_pon,),
            ),
            create_player(
                seat=3,
                tiles=tile_copies(3, pin="123456789", honors="1234"),
                discards=(Discard(tile_id=four_man[0]),),
            ),
        )
        round_state = create_dealt_game_state(players, current_player_seat=_KAN_CALLER).round_state
        assert get_waiting_tiles(open_yakuless_wait) == {tile_to_34(one_man_pon.called_tile), tile_to_34(four_man[3])}

        assert is_chankan_possible(round_state, caller_seat=_KAN_CALLER, kan_tile=four_man[3]) == [1]
