import pytest
from mahjong.hand_calculating.yaku_list import AkaDora, Chankan, Dora, Haku, Ittsu, Riichi, Tsumo
from mahjong.hand_calculating.yaku_list.yakuman import Daisangen, DaiSuushii, Tsuuiisou
from mahjong.tile import TilesConverter

from game.logic.enums import RoundPhase, RoundResultType
from game.logic.events import GameEvent, RoundEndEvent
from game.logic.meld_wrapper import FrozenMeld
from game.logic.scoring import (
    HandResult,
    ScoringContext,
    apply_nagashi_mangan_score,
    calculate_hand_value,
    calculate_hand_value_with_tiles,
)
from game.logic.settings import GameSettings
from game.logic.state import (
    Discard,
    MahjongGameState,
    MahjongPlayer,
    MahjongRoundState,
    seat_to_wind,
)
from game.logic.tiles import EAST_34, NORTH_34, SOUTH_34, WEST_34, tile_to_34
from game.logic.turn import process_ron_call, process_tsumo_call
from game.logic.types import DoubleRonResult, RonCallInput, RonResult, RoundResult, TsumoResult, YakuInfo
from game.logic.win import all_tiles_from_hand_and_melds, get_waiting_tiles
from game.tests.conftest import create_dealt_game_state, create_game_state, create_player, create_round_state
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.wall import FIRST_URA_POSITION


def _yaku(*yaku_ids: int) -> list[YakuInfo]:
    return [YakuInfo(yaku_id=yid, han=0) for yid in yaku_ids]


def _sum_winner_changes(result: DoubleRonResult) -> dict[int, int]:
    return {seat: sum(w.score_changes[seat] for w in result.winners) for seat in range(4)}


_DORA_TWO_MAN_INDICATOR = tile_copies(1, man="1")[0]
_DORA_EAST_INDICATOR = tile_copies(0, honors="4")[0]
_ITTSU_TANKI_ON_FIVE_PIN = tuple(tile_copies(0, man="123456789", pin="12355"))


def _go_around_discards(seat: int, *, riichi: bool = False) -> tuple[Discard, ...]:
    first, riichi_turn, last = tile_copies(seat, honors="123")
    return (Discard(tile_id=first), Discard(tile_id=riichi_turn, is_riichi_discard=riichi), Discard(tile_id=last))


def _bystander(seat: int, *, extra_discards: tuple[Discard, ...] = ()) -> MahjongPlayer:
    return create_player(
        seat=seat,
        tiles=tile_copies(seat, sou="123456789", pin="6789"),
        discards=(*_go_around_discards(seat), *extra_discards),
    )


def _riichi(player: MahjongPlayer) -> MahjongPlayer:
    return player.model_copy(
        update={"is_riichi": True, "score": 24000, "discards": _go_around_discards(player.seat, riichi=True)}
    )


def _dealt_round(
    seat_0: MahjongPlayer,
    *,
    others: dict[int, MahjongPlayer] | None = None,
    current_player_seat: int = 0,
    dora_indicator: int | None = _DORA_TWO_MAN_INDICATOR,
    honba_sticks: int = 0,
    riichi_sticks: int = 0,
    settings: GameSettings | None = None,
) -> MahjongGameState:
    staged = others or {}
    players = (seat_0, *(staged.get(seat) or _bystander(seat) for seat in (1, 2, 3)))
    game_state = create_dealt_game_state(
        players,
        current_player_seat=current_player_seat,
        dora_indicator=dora_indicator,
        riichi_sticks=riichi_sticks,
        settings=settings,
    )
    return game_state.model_copy(update={"honba_sticks": honba_sticks})


def _dealer_after_draw(hand: tuple[int, ...], **updates: object) -> MahjongGameState:
    dealer = create_player(seat=0, tiles=hand, discards=_go_around_discards(0)).model_copy(update=updates)
    return _dealt_round(_riichi(dealer) if updates.get("is_riichi") else dealer)


def _seat_0_context(round_state: MahjongRoundState, *, is_tsumo: bool) -> ScoringContext:
    return ScoringContext(
        player=round_state.players[0], round_state=round_state, settings=GameSettings(), is_tsumo=is_tsumo
    )


def _yaku_han(result: HandResult) -> list[tuple[int, int]]:
    return [(y.yaku_id, y.han) for y in result.yaku]


class TestSeatToWind:
    def test_seat_to_wind__when_dealer_at_seat_2__should_wrap_winds_around_table(self):
        # dealer at seat 2: seat 2=East, seat 3=South, seat 0=West, seat 1=North
        assert seat_to_wind(2, 2) == EAST_34
        assert seat_to_wind(3, 2) == SOUTH_34
        assert seat_to_wind(0, 2) == WEST_34
        assert seat_to_wind(1, 2) == NORTH_34


class TestCalculateHandValue:
    def test_calculate_hand_value__when_closed_tanki_tsumo__should_return_scored_result(self):
        round_state = _dealer_after_draw(_ITTSU_TANKI_ON_FIVE_PIN).round_state
        ctx = ScoringContext(
            player=round_state.players[0], round_state=round_state, settings=GameSettings(), is_tsumo=True
        )

        result = calculate_hand_value(ctx, _ITTSU_TANKI_ON_FIVE_PIN[-1])
        assert result.error is None
        assert _yaku_han(result) == [
            (Tsumo.yaku_id, 1),
            (Ittsu.yaku_id, 2),
            (Dora.yaku_id, 1),
            (AkaDora.yaku_id, 2),
        ]
        assert (result.han, result.fu) == (6, 30)
        assert (result.cost_main, result.cost_additional) == (6000, 6000)

    def test_calculate_hand_value__when_riichi_tsumo__should_include_riichi_yaku(self):
        round_state = _dealer_after_draw(_ITTSU_TANKI_ON_FIVE_PIN, is_riichi=True).round_state
        ctx = ScoringContext(
            player=round_state.players[0], round_state=round_state, settings=GameSettings(), is_tsumo=True
        )

        result = calculate_hand_value(ctx, _ITTSU_TANKI_ON_FIVE_PIN[-1])
        assert result.error is None
        assert _yaku_han(result) == [
            (Tsumo.yaku_id, 1),
            (Riichi.yaku_id, 1),
            (Ittsu.yaku_id, 2),
            (Dora.yaku_id, 1),
            (AkaDora.yaku_id, 2),
        ]
        assert result.han == 7

    def test_calculate_hand_value_with_tiles__when_riichi_ron__should_not_include_menzen_tsumo(self):
        waiting_hand, ron_tile = _ITTSU_TANKI_ON_FIVE_PIN[:-1], tile_copies(2, pin="5")[0]
        riichi_seat = _riichi(create_player(seat=0, tiles=waiting_hand))
        discarder = _bystander(3, extra_discards=(Discard(tile_id=ron_tile),))
        round_state = _dealt_round(riichi_seat, others={3: discarder}, current_player_seat=3).round_state
        ctx = _seat_0_context(round_state, is_tsumo=False)

        result = calculate_hand_value_with_tiles(ctx, tiles=[*waiting_hand, ron_tile], win_tile=ron_tile)
        assert result.error is None
        assert _yaku_han(result) == [(Riichi.yaku_id, 1), (Ittsu.yaku_id, 2), (Dora.yaku_id, 1), (AkaDora.yaku_id, 2)]
        assert result.han == 6

    def test_calculate_hand_value_with_tiles__when_open_hand_rons__should_score_its_yakuhai_meld(self):
        haku = tile_copies(0, honors="555")
        haku_pon = FrozenMeld(
            meld_type=FrozenMeld.PON, tiles=tuple(haku), opened=True, called_tile=haku[0], who=0, from_who=1
        )
        waiting_on_one_or_four_sou = tuple(tile_copies(0, man="234567", sou="2355"))
        ron_tile = tile_copies(3, sou="4")[0]
        open_hand = create_player(
            seat=0, tiles=waiting_on_one_or_four_sou, melds=(haku_pon,), discards=_go_around_discards(0)
        )
        others = {
            1: create_player(
                seat=1,
                tiles=tile_copies(2, man="123456789", pin="1234"),
                discards=(*_go_around_discards(1), Discard(tile_id=haku[0])),
            ),
            3: create_player(
                seat=3,
                tiles=tile_copies(3, man="123456789", pin="6789"),
                discards=(*_go_around_discards(3), Discard(tile_id=ron_tile)),
            ),
        }
        round_state = _dealt_round(open_hand, others=others, current_player_seat=3).round_state
        ctx = _seat_0_context(round_state, is_tsumo=False)

        tiles_with_ron = all_tiles_from_hand_and_melds([*waiting_on_one_or_four_sou, ron_tile], (haku_pon,))
        result = calculate_hand_value_with_tiles(ctx, tiles=tiles_with_ron, win_tile=ron_tile)
        assert result.error is None
        assert _yaku_han(result) == [(Haku.yaku_id, 1), (Dora.yaku_id, 1), (AkaDora.yaku_id, 2)]
        assert (result.han, result.fu, result.cost_main) == (4, 30, 12000)


def _assert_settled(before: MahjongGameState, after: MahjongGameState, score_changes: dict[int, int]) -> None:
    assert {p.seat: p.score for p in after.round_state.players} == {
        p.seat: p.score + score_changes[p.seat] for p in before.round_state.players
    }
    assert after.riichi_sticks == 0


class TestTsumoScoring:
    def test_tsumo_score__when_riichi_dealer_tsumo_with_honba_and_sticks__should_charge_each_player_equally(self):
        game_state = _dealer_after_draw(_ITTSU_TANKI_ON_FIVE_PIN, is_riichi=True)
        game_state = game_state.model_copy(update={"honba_sticks": 1, "riichi_sticks": 2})

        new_state, events = process_tsumo_call(game_state, winner_seat=0)
        result = _round_result(events)
        assert isinstance(result, TsumoResult)
        assert result.hand_result.points == 18000
        assert result.score_changes == {0: 20300, 1: -6100, 2: -6100, 3: -6100}
        _assert_settled(game_state, new_state, result.score_changes)
        assert result.riichi_sticks_collected == 2
        assert (result.closed_tiles, result.win_tile) == (
            list(_ITTSU_TANKI_ON_FIVE_PIN[:-1]),
            _ITTSU_TANKI_ON_FIVE_PIN[-1],
        )
        assert result.ura_dora_indicators == list(game_state.round_state.wall.dead_wall.ura_dora_indicators)

    def test_tsumo_score__when_non_dealer_tsumo_with_custom_honba__should_round_payments_up_and_add_honba_per_loser(
        self,
    ):
        ittsu_tanki_without_red_five = (*tile_copies(0, man="12346789", pin="123"), *tile_copies(1, man="5", pin="55"))
        winner = create_player(seat=1, tiles=ittsu_tanki_without_red_five, discards=_go_around_discards(1))
        seat_0 = create_player(
            seat=0, tiles=tile_copies(0, sou="123456789", pin="6789"), discards=_go_around_discards(0)
        )
        game_state = _dealt_round(
            seat_0,
            others={1: winner},
            current_player_seat=1,
            dora_indicator=_DORA_EAST_INDICATOR,
            honba_sticks=1,
            settings=GameSettings(honba_tsumo_bonus_per_loser=200),
        )

        new_state, events = process_tsumo_call(game_state, winner_seat=1)
        result = _round_result(events)
        assert isinstance(result, TsumoResult)
        assert [(y.yaku_id, y.han) for y in result.hand_result.yaku] == [(Tsumo.yaku_id, 1), (Ittsu.yaku_id, 2)]
        assert (result.hand_result.han, result.hand_result.fu, result.hand_result.points) == (3, 30, 4000)
        assert result.score_changes == {0: -2200, 1: 4600, 2: -1200, 3: -1200}
        _assert_settled(game_state, new_state, result.score_changes)


_THREE_PIN_DISCARD = tile_copies(0, pin="3")[0]
_RIICHI_ITTSU_ON_THREE_PIN = tuple(tile_copies(0, man="123456789", pin="1255"))
_ITTSU_ON_THREE_PIN = (
    *tile_copies(0, sou="123456789"),
    *tile_copies(1, pin="12"),
    *tile_copies(2, pin="5"),
    *tile_copies(3, pin="5"),
)
_RIICHI_WINNER_SEAT = 2
_DEALER_WINNER_SEAT = 0


def _three_pin_discarded(
    *, loser_seat: int, honba_sticks: int, riichi_sticks: int, settings: GameSettings | None = None
) -> MahjongGameState:
    bystander_seat = next(seat for seat in (1, 3) if seat != loser_seat)
    others = {
        _RIICHI_WINNER_SEAT: _riichi(create_player(seat=_RIICHI_WINNER_SEAT, tiles=_RIICHI_ITTSU_ON_THREE_PIN)),
        loser_seat: create_player(
            seat=loser_seat,
            tiles=tile_copies(1, man="123456789", honors="4567"),
            discards=(*_go_around_discards(loser_seat), Discard(tile_id=_THREE_PIN_DISCARD)),
        ),
        bystander_seat: create_player(
            seat=bystander_seat,
            tiles=tile_copies(2, man="123456789", honors="4567"),
            discards=_go_around_discards(bystander_seat),
        ),
    }
    dealer = create_player(seat=_DEALER_WINNER_SEAT, tiles=_ITTSU_ON_THREE_PIN, discards=_go_around_discards(0))
    game_state = _dealt_round(
        dealer,
        others=others,
        current_player_seat=loser_seat,
        dora_indicator=_DORA_EAST_INDICATOR,
        honba_sticks=honba_sticks,
        riichi_sticks=riichi_sticks,
        settings=settings,
    )
    assert (
        get_waiting_tiles(dealer) == get_waiting_tiles(others[_RIICHI_WINNER_SEAT]) == {tile_to_34(_THREE_PIN_DISCARD)}
    )
    return game_state


class TestRonScoring:
    def test_ron_score__when_honba_and_riichi_sticks__should_charge_the_discarder_and_award_sticks_to_the_winner(self):
        game_state = _three_pin_discarded(
            loser_seat=1, honba_sticks=2, riichi_sticks=2, settings=GameSettings(honba_ron_bonus=500)
        )

        new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[_RIICHI_WINNER_SEAT], tile_id=_THREE_PIN_DISCARD, discarder_seat=1),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert result.hand_result.points == 8000
        assert result.score_changes == {0: 0, 1: -9000, 2: 11000, 3: 0}
        _assert_settled(game_state, new_state, result.score_changes)
        assert result.riichi_sticks_collected == 2
        assert result.ura_dora_indicators == list(game_state.round_state.wall.dead_wall.ura_dora_indicators)


class TestDoubleRonScoring:
    @pytest.mark.parametrize(
        ("loser_seat", "stick_receiver", "score_changes"),
        [
            pytest.param(1, 2, {0: 8700, 1: -17700, 2: 11000, 3: 0}, id="closer_winner_is_the_higher_seat"),
            pytest.param(3, 0, {0: 10700, 1: 0, 2: 9000, 3: -17700}, id="closer_winner_wraps_past_seat_3"),
        ],
    )
    def test_double_ron_score__should_charge_the_discarder_both_hands_with_honba_and_give_sticks_to_the_closer_winner(
        self, loser_seat, stick_receiver, score_changes
    ):
        game_state = _three_pin_discarded(
            loser_seat=loser_seat, honba_sticks=2, riichi_sticks=2, settings=GameSettings(honba_ron_bonus=500)
        )

        new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(
                ron_callers=[_DEALER_WINNER_SEAT, _RIICHI_WINNER_SEAT],
                tile_id=_THREE_PIN_DISCARD,
                discarder_seat=loser_seat,
            ),
        )
        result = _round_result(events)
        assert isinstance(result, DoubleRonResult)
        assert [(w.winner_seat, w.hand_result.points) for w in result.winners] == [(0, 7700), (2, 8000)]
        assert {w.winner_seat: w.riichi_sticks_collected for w in result.winners} == {
            seat: 2 if seat == stick_receiver else 0 for seat in (0, 2)
        }
        assert {w.winner_seat: w.ura_dora_indicators for w in result.winners} == {
            0: None,
            2: list(game_state.round_state.wall.dead_wall.ura_dora_indicators),
        }
        assert result.score_changes == score_changes
        assert _sum_winner_changes(result) == score_changes
        _assert_settled(game_state, new_state, score_changes)


class TestApplyNagashiManganScore:
    def _create_game_state(self, dealer_seat: int = 0) -> MahjongGameState:
        # use non-tempai hands (disconnected tiles) by default
        non_tempai_tiles = TilesConverter.string_to_136_array(man="13579", pin="2468", sou="1357")
        players = tuple(create_player(seat=i, score=25000, tiles=tuple(non_tempai_tiles)) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=dealer_seat,
            current_player_seat=0,
            round_wind=0,
        )
        return create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=0)

    def test_apply_nagashi_mangan_score__when_dealer_qualifies__should_collect_4000_from_each(self):
        game_state = self._create_game_state(dealer_seat=0)

        new_game_state, result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[0],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )
        new_round_state = new_game_state.round_state
        assert result.type == RoundResultType.NAGASHI_MANGAN
        assert result.qualifying_seats == [0]
        assert result.score_changes[0] == 12000
        assert result.score_changes[1] == -4000
        assert result.score_changes[2] == -4000
        assert result.score_changes[3] == -4000
        assert new_round_state.players[0].score == 37000
        assert new_round_state.players[1].score == 21000
        assert new_round_state.players[2].score == 21000
        assert new_round_state.players[3].score == 21000

    def test_apply_nagashi_mangan_score__when_non_dealer_qualifies__should_charge_dealer_4000_and_others_2000(self):
        game_state = self._create_game_state(dealer_seat=0)

        new_game_state, result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[1],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )
        new_round_state = new_game_state.round_state
        assert result.score_changes[1] == 8000
        assert result.score_changes[0] == -4000  # dealer pays 4000
        assert result.score_changes[2] == -2000  # non-dealer pays 2000
        assert result.score_changes[3] == -2000  # non-dealer pays 2000
        assert new_round_state.players[1].score == 33000
        assert new_round_state.players[0].score == 21000
        assert new_round_state.players[2].score == 23000
        assert new_round_state.players[3].score == 23000

    def test_apply_nagashi_mangan_score__when_two_players_qualify__should_net_payments_to_zero_sum(self):
        game_state = self._create_game_state(dealer_seat=0)

        _new_game_state, result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[0, 2],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )
        # seat 0 (dealer): +12000 from nagashi, -4000 paying seat 2 (dealer pays 4000)
        # seat 2 (non-dealer): +8000 from nagashi, -4000 paying seat 0 (pays dealer 4000)
        assert result.score_changes[0] == 12000 - 4000  # 8000
        assert result.score_changes[2] == 8000 - 4000  # 4000
        # seat 1: pays 4000 to seat 0 + 2000 to seat 2 = -6000
        assert result.score_changes[1] == -6000
        # seat 3: pays 4000 to seat 0 + 2000 to seat 2 = -6000
        assert result.score_changes[3] == -6000
        # verify total is zero
        assert sum(result.score_changes.values()) == 0


_DAISANGEN_WIN_TILE = tile_copies(1, sou="9")[0]
_DAISANGEN_TSUUIISOU_WIN_TILE = tile_copies(1, honors="2")[0]
_ITTSUU_SHANPON_HAND = (
    *tile_copies(0, man="123456789"),
    *TilesConverter.string_to_136_array(pin="11"),
    *tile_copies(2, sou="9"),
    *tile_copies(3, sou="9"),
)


def _honor_pons(seat: int, *, from_seat: int, honors: str) -> tuple[FrozenMeld, ...]:
    return tuple(
        FrozenMeld(
            meld_type=FrozenMeld.PON,
            tiles=tuple(pon_tiles),
            opened=True,
            called_tile=pon_tiles[0],
            who=seat,
            from_who=from_seat,
        )
        for pon_tiles in (TilesConverter.string_to_136_array(honors=honor * 3) for honor in honors)
    )


def _daisangen_player(seat: int, *, pao_seat: int, closed_tiles: list[int]) -> MahjongPlayer:
    melds = _honor_pons(seat, from_seat=pao_seat, honors="567")
    return create_player(seat=seat, tiles=closed_tiles, melds=melds, pao_seat=pao_seat)


def _daisangen_tanki_player(seat: int, *, pao_seat: int) -> MahjongPlayer:
    return _daisangen_player(seat, pao_seat=pao_seat, closed_tiles=tile_copies(0, pin="234", sou="9"))


def _daisangen_tsuuiisou_tanki_player(seat: int, *, pao_seat: int) -> MahjongPlayer:
    east_triplet_and_south = TilesConverter.string_to_136_array(honors="1112")
    return _daisangen_player(seat, pao_seat=pao_seat, closed_tiles=east_triplet_and_south)


def _with_drawn_tile(player: MahjongPlayer, tile: int) -> MahjongPlayer:
    return player.model_copy(update={"tiles": (*player.tiles, tile)})


def _stage_pao_win(
    *,
    dealer_seat: int,
    winners: list[MahjongPlayer],
    current_seat: int,
    discarded_tile: int | None = None,
    honba_sticks: int = 0,
    riichi_sticks: int = 0,
    settings: GameSettings | None = None,
) -> MahjongGameState:
    winners_by_seat = {winner.seat: winner for winner in winners}
    filler_copies = iter((1, 2, 3))
    players = []
    for seat in range(4):
        if seat in winners_by_seat:
            players.append(winners_by_seat[seat])
            continue

        is_discarder = discarded_tile is not None and seat == current_seat
        discards = [Discard(tile_id=discarded_tile)] if is_discarder else []
        filler_hand = tile_copies(next(filler_copies), man="123456789", pin="5678")
        players.append(create_player(seat=seat, tiles=filler_hand, discards=discards))

    round_state = create_round_state(
        players=players,
        wall=tile_copies(0, sou="2345678"),
        dora_indicators=tile_copies(0, sou="1"),
        dealer_seat=dealer_seat,
        current_player_seat=current_seat,
        phase=RoundPhase.PLAYING,
    )
    return create_game_state(round_state, honba_sticks=honba_sticks, riichi_sticks=riichi_sticks, settings=settings)


def _round_result(events: list[GameEvent]) -> RoundResult:
    assert len(events) == 1
    assert isinstance(events[0], RoundEndEvent)
    return events[0].result


class TestPaoTsumoScoring:
    def test_pao__when_non_dealer_tsumo_with_honba__should_charge_pao_player_everything(self):
        winner = _with_drawn_tile(_daisangen_tanki_player(1, pao_seat=2), _DAISANGEN_WIN_TILE)
        game_state = _stage_pao_win(dealer_seat=0, winners=[winner], current_seat=1, honba_sticks=1, riichi_sticks=1)

        _new_state, events = process_tsumo_call(game_state, winner_seat=1)
        result = _round_result(events)
        assert isinstance(result, TsumoResult)
        assert result.pao_seat == 2
        assert result.hand_result.points == 32000
        assert result.score_changes == {0: 0, 1: 33300, 2: -32300, 3: 0}
        assert result.riichi_sticks_collected == 1

    def test_pao__when_dealer_tsumo_stacks_another_yakuman__should_charge_pao_player_only_the_pao_yakuman_and_honba(
        self,
    ):
        winner = _with_drawn_tile(_daisangen_tsuuiisou_tanki_player(0, pao_seat=3), _DAISANGEN_TSUUIISOU_WIN_TILE)
        game_state = _stage_pao_win(dealer_seat=0, winners=[winner], current_seat=0, honba_sticks=1)

        _new_state, events = process_tsumo_call(game_state, winner_seat=0)
        result = _round_result(events)
        assert isinstance(result, TsumoResult)
        assert [y.yaku_id for y in result.hand_result.yaku] == [Daisangen.yaku_id, Tsuuiisou.yaku_id]
        assert result.hand_result.points == 96000
        assert result.score_changes == {0: 96300, 1: -16000, 2: -16000, 3: -64300}


class TestPaoRonScoring:
    def test_pao__when_dealer_rons_off_other_player__should_split_hand_value_and_give_sticks_to_winner(self):
        winner = _daisangen_tanki_player(0, pao_seat=2)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=1,
            discarded_tile=_DAISANGEN_WIN_TILE,
            riichi_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[0], tile_id=_DAISANGEN_WIN_TILE, discarder_seat=1),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert result.pao_seat == 2
        assert result.hand_result.points == 48000
        assert result.score_changes == {0: 49000, 1: -24000, 2: -24000, 3: 0}
        assert result.riichi_sticks_collected == 1

    def test_pao__when_ron_on_pao_player__should_charge_them_in_full(self):
        winner = _daisangen_tanki_player(1, pao_seat=3)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=3,
            discarded_tile=_DAISANGEN_WIN_TILE,
            honba_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[1], tile_id=_DAISANGEN_WIN_TILE, discarder_seat=3),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert result.pao_seat == 3
        assert result.hand_result.points == 32000
        assert result.score_changes == {0: 0, 1: 32300, 2: 0, 3: -32300}

    def test_pao__when_ron_off_another_player_with_honba__should_charge_the_whole_honba_to_the_pao_player(self):
        winner = _daisangen_tanki_player(1, pao_seat=3)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=2,
            discarded_tile=_DAISANGEN_WIN_TILE,
            honba_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[1], tile_id=_DAISANGEN_WIN_TILE, discarder_seat=2),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert result.hand_result.points == 32000
        assert result.score_changes == {0: 0, 1: 32300, 2: -16000, 3: -16300}

    def test_pao__when_dealer_ron_stacks_another_yakuman__should_charge_pao_player_half_the_pao_yakuman_and_honba(
        self,
    ):
        winner = _daisangen_tsuuiisou_tanki_player(0, pao_seat=3)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=1,
            discarded_tile=_DAISANGEN_TSUUIISOU_WIN_TILE,
            honba_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[0], tile_id=_DAISANGEN_TSUUIISOU_WIN_TILE, discarder_seat=1),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert [y.yaku_id for y in result.hand_result.yaku] == [Daisangen.yaku_id, Tsuuiisou.yaku_id]
        assert result.hand_result.points == 96000
        assert result.score_changes == {0: 96300, 1: -72000, 2: 0, 3: -24300}

    def test_pao__when_double_yakuman_daisuushii_ron_stacks_tsuuiisou__should_weigh_the_pao_share_by_han(self):
        melds = (*_honor_pons(1, from_seat=0, honors="123"), *_honor_pons(1, from_seat=3, honors="4"))
        winner = create_player(seat=1, tiles=tile_copies(0, honors="5"), melds=melds, pao_seat=3)
        haku_win_tile = tile_copies(1, honors="5")[0]
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=2,
            discarded_tile=haku_win_tile,
            honba_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[1], tile_id=haku_win_tile, discarder_seat=2),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert [(y.yaku_id, y.han) for y in result.hand_result.yaku] == [
            (Tsuuiisou.yaku_id, 13),
            (DaiSuushii.yaku_id, 26),
        ]
        assert result.pao_seat == 3
        assert result.hand_result.points == 96000
        assert result.score_changes == {0: 0, 1: 96300, 2: -64000, 3: -32300}

    def test_pao__when_lowered_threshold_hand_wins_without_the_pao_yakuman__should_settle_as_ordinary_ron(self):
        settings = GameSettings(daisangen_pao_set_threshold=2)
        closed_tiles = [*tile_copies(0, pin="234678"), *TilesConverter.string_to_136_array(honors="7")]
        melds = _honor_pons(1, from_seat=3, honors="56")
        winner = create_player(seat=1, tiles=closed_tiles, melds=melds, pao_seat=3)
        chun_win_tile = tile_copies(1, honors="7")[0]
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[winner],
            current_seat=2,
            discarded_tile=chun_win_tile,
            settings=settings,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[1], tile_id=chun_win_tile, discarder_seat=2),
        )
        result = _round_result(events)
        assert isinstance(result, RonResult)
        assert result.pao_seat is None
        assert result.hand_result.points == 12000
        assert result.score_changes == {0: 0, 1: 12000, 2: -12000, 3: 0}

    def test_pao__when_double_ron_with_honba__should_charge_the_pao_winners_honba_to_the_pao_player(self):
        pao_winner = _daisangen_tanki_player(0, pao_seat=2)
        other_winner = create_player(seat=1, tiles=_ITTSUU_SHANPON_HAND)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[pao_winner, other_winner],
            current_seat=3,
            discarded_tile=_DAISANGEN_WIN_TILE,
            honba_sticks=1,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[0, 1], tile_id=_DAISANGEN_WIN_TILE, discarder_seat=3),
        )
        result = _round_result(events)
        assert isinstance(result, DoubleRonResult)
        assert [w.pao_seat for w in result.winners] == [2, None]
        assert [w.hand_result.points for w in result.winners] == [48000, 5200]
        assert [w.score_changes for w in result.winners] == [
            {0: 48300, 1: 0, 2: -24300, 3: -24000},
            {0: 0, 1: 5500, 2: 0, 3: -5500},
        ]
        assert result.score_changes == {0: 48300, 1: 5500, 2: -24300, 3: -29500}

    def test_pao__when_double_ron_liable_player_is_the_other_winner__should_charge_them_half_the_yakuman(self):
        other_winner = create_player(seat=1, tiles=_ITTSUU_SHANPON_HAND)
        pao_winner = _daisangen_tanki_player(2, pao_seat=1)
        game_state = _stage_pao_win(
            dealer_seat=0,
            winners=[other_winner, pao_winner],
            current_seat=0,
            discarded_tile=_DAISANGEN_WIN_TILE,
        )

        _new_state, events = process_ron_call(
            game_state,
            ron_input=RonCallInput(ron_callers=[1, 2], tile_id=_DAISANGEN_WIN_TILE, discarder_seat=0),
        )
        result = _round_result(events)
        assert isinstance(result, DoubleRonResult)
        assert [w.pao_seat for w in result.winners] == [None, 1]
        assert [w.hand_result.points for w in result.winners] == [5200, 32000]
        assert [w.score_changes for w in result.winners] == [
            {0: -5200, 1: 5200, 2: 0, 3: 0},
            {0: -16000, 1: -16000, 2: 32000, 3: 0},
        ]
        assert result.score_changes == {0: -21200, 1: -10800, 2: 32000, 3: 0}


def _added_kan_declared_by_seat_2(kan_tiles: tuple[int, ...], *, robber: MahjongPlayer) -> MahjongRoundState:
    pon = FrozenMeld(
        meld_type=FrozenMeld.PON, tiles=kan_tiles[:3], opened=True, called_tile=kan_tiles[0], who=2, from_who=1
    )
    others = {
        1: _bystander(1, extra_discards=(Discard(tile_id=kan_tiles[0]),)),
        3: _bystander(3, extra_discards=tuple(Discard(tile_id=m.called_tile) for m in robber.melds)),
        2: create_player(
            seat=2,
            tiles=(kan_tiles[3], *tile_copies(2, sou="123456789"), *tile_copies(1, honors="5")),
            melds=(pon,),
            discards=_go_around_discards(2),
        ),
    }
    return _dealt_round(robber, others=others, current_player_seat=2).round_state


_ONE_MAN_PON_TILES = (*tile_copies(0, man="1"), *tile_copies(2, man="1"), *tile_copies(3, man="1"))
_ONE_MAN_PON = FrozenMeld(
    meld_type=FrozenMeld.PON,
    tiles=_ONE_MAN_PON_TILES,
    opened=True,
    called_tile=_ONE_MAN_PON_TILES[0],
    who=0,
    from_who=3,
)
_YAKULESS_OPEN_HAND_WAITING_ON_TWO_OR_FIVE_MAN = tuple(tile_copies(0, man="34", pin="234", sou="567", honors="77"))
_FIVE_MAN_QUAD = tuple(tile_copies(0, man="5555"))


def _yakuless_open_hand(seat: int = 0) -> MahjongPlayer:
    return create_player(
        seat=seat,
        tiles=_YAKULESS_OPEN_HAND_WAITING_ON_TWO_OR_FIVE_MAN,
        melds=(_ONE_MAN_PON,),
        discards=_go_around_discards(seat),
    )


class TestChankanYakuScoring:
    def test_calculate_hand_value_with_tiles__when_chankan__should_include_chankan_yaku(self):
        riichi_robber = _riichi(create_player(seat=0, tiles=_RIICHI_ITTSU_ON_THREE_PIN))
        three_pin_quad = tuple(tile_copies(0, pin="3333"))
        round_state = _added_kan_declared_by_seat_2(three_pin_quad, robber=riichi_robber)
        robber = round_state.players[0]
        ctx = ScoringContext(
            player=robber, round_state=round_state, settings=GameSettings(), is_tsumo=False, is_chankan=True
        )

        result = calculate_hand_value_with_tiles(
            ctx, tiles=[*robber.tiles, three_pin_quad[3]], win_tile=three_pin_quad[3]
        )
        assert result.error is None
        assert _yaku_han(result) == [
            (Riichi.yaku_id, 1),
            (Chankan.yaku_id, 1),
            (Ittsu.yaku_id, 2),
            (Dora.yaku_id, 1),
            (AkaDora.yaku_id, 2),
        ]

    @pytest.mark.parametrize(
        ("is_chankan", "expected_yaku", "expected_error"),
        [
            pytest.param(True, [(Chankan.yaku_id, 1), (AkaDora.yaku_id, 1)], None, id="chankan"),
            pytest.param(False, [], "no_yaku", id="ordinary_ron"),
        ],
    )
    def test_calculate_hand_value_with_tiles__when_open_hand_has_no_other_yaku__should_score_only_with_chankan(
        self, is_chankan, expected_yaku, expected_error
    ):
        round_state = _added_kan_declared_by_seat_2(_FIVE_MAN_QUAD, robber=_yakuless_open_hand())
        robber = round_state.players[0]
        ctx = ScoringContext(
            player=robber, round_state=round_state, settings=GameSettings(), is_tsumo=False, is_chankan=is_chankan
        )

        robbed_tile = _FIVE_MAN_QUAD[3]
        tiles_with_ron = all_tiles_from_hand_and_melds([*robber.tiles, robbed_tile], robber.melds)
        result = calculate_hand_value_with_tiles(ctx, tiles=tiles_with_ron, win_tile=robbed_tile)
        assert (_yaku_han(result), result.error) == (expected_yaku, expected_error)


class TestHandValueParityBetweenFunctions:
    def test_calculate_hand_value_with_tiles__when_tsumo__should_match_calculate_hand_value(self):
        round_state = _dealer_after_draw(_ITTSU_TANKI_ON_FIVE_PIN).round_state
        ctx = ScoringContext(
            player=round_state.players[0], round_state=round_state, settings=GameSettings(), is_tsumo=True
        )
        win_tile = _ITTSU_TANKI_ON_FIVE_PIN[-1]

        result_a = calculate_hand_value(ctx, win_tile)
        result_b = calculate_hand_value_with_tiles(ctx, tiles=list(_ITTSU_TANKI_ON_FIVE_PIN), win_tile=win_tile)
        assert result_a.error is None
        assert result_a == result_b

    def test_calculate_hand_value_with_tiles__when_no_yaku__should_match_calculate_hand_value_error(self):
        drawn_five_man = tile_copies(1, man="5")[0]
        open_hand = _yakuless_open_hand()
        drawn = open_hand.model_copy(update={"tiles": (*open_hand.tiles, drawn_five_man)})
        others = {3: _bystander(3, extra_discards=(Discard(tile_id=_ONE_MAN_PON_TILES[0]),))}
        round_state = _dealt_round(drawn, others=others).round_state
        ctx = ScoringContext(
            player=round_state.players[0], round_state=round_state, settings=GameSettings(), is_tsumo=True
        )

        result_a = calculate_hand_value(ctx, drawn_five_man)
        result_b = calculate_hand_value_with_tiles(
            ctx, tiles=[*drawn.tiles, *_ONE_MAN_PON_TILES], win_tile=drawn_five_man
        )
        assert result_a.error == result_b.error == "no_yaku"


class TestNagashiManganPreservesRiichiSticks:
    def test_apply_nagashi_mangan_score__when_riichi_sticks_on_table__should_keep_them(self):
        players = tuple(create_player(seat=i, score=25000, tiles=[0, 1, 2, 3]) for i in range(4))
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            round_wind=0,
        )
        game_state = create_game_state(round_state=round_state, honba_sticks=0, riichi_sticks=3)

        new_game_state, _result = apply_nagashi_mangan_score(
            game_state,
            qualifying_seats=[0],
            tempai_seats=[],
            noten_seats=[0, 1, 2, 3],
            tenpai_hands=[],
        )
        assert new_game_state.riichi_sticks == 3


class TestUraDoraScoringIntegration:
    def _build_game_state(self, *, dead_wall, dora_indicators, tiles, is_riichi):
        nine_pin_closed_kan = FrozenMeld(
            meld_type=FrozenMeld.KAN, tiles=tuple(tile_copies(0, pin="9999")), opened=False, who=1, from_who=1
        )
        riichi_discard = Discard(tile_id=tile_copies(0, honors="7")[0], is_riichi_discard=True)
        players = (
            create_player(seat=0, tiles=tuple(tiles), is_riichi=is_riichi, discards=(riichi_discard,)),
            create_player(
                seat=1,
                tiles=(*tile_copies(1, pin="12345678"), *tile_copies(0, honors="55")),
                melds=(nine_pin_closed_kan,),
                discards=(Discard(tile_id=tile_copies(1, honors="7")[0]),),
            ),
            create_player(seat=2, tiles=(*tile_copies(2, pin="12345678"), *tile_copies(0, honors="66234"))),
            create_player(seat=3, tiles=(*tile_copies(3, pin="12345678"), *tile_copies(2, honors="56234"))),
        )
        round_state = create_round_state(
            players=players,
            dealer_seat=0,
            current_player_seat=0,
            dora_indicators=dora_indicators,
            dead_wall=dead_wall,
            wall=tile_copies(2, man="123456789"),
            all_discards=tuple(d.tile_id for p in players for d in p.discards),
        )
        return create_game_state(round_state=round_state)

    def test_calculate_hand_value__when_riichi_after_kan__should_count_ura_dora_for_each_indicator(self):
        tiles = TilesConverter.string_to_136_array(man="123456789", sou="12355")
        win_tile = tiles[-1]

        dora_indicator_1 = tile_copies(1, man="1")[0]
        dora_indicator_2 = tile_copies(1, man="5")[0]

        # ura dora 1: indicator 4s -> ura dora 5s (2 copies in hand = 2 han)
        # ura dora 2: indicator 1s -> ura dora 2s (1 copy in hand = 1 han)
        ura_tile_1 = tile_copies(1, sou="4")[0]
        ura_tile_2 = tile_copies(1, sou="1")[0]

        dead_wall: list[int | None] = [None] * 14
        dead_wall[2] = dora_indicator_1
        dead_wall[3] = dora_indicator_2
        dead_wall[FIRST_URA_POSITION] = ura_tile_1
        dead_wall[FIRST_URA_POSITION + 1] = ura_tile_2

        game_state = self._build_game_state(
            dead_wall=tuple(dead_wall),
            dora_indicators=(dora_indicator_1, dora_indicator_2),
            tiles=tiles,
            is_riichi=True,
        )
        player = game_state.round_state.players[0]

        settings = GameSettings(has_akadora=False, has_kan_uradora=True)
        ctx = ScoringContext(player=player, round_state=game_state.round_state, settings=settings, is_tsumo=True)
        result = calculate_hand_value(ctx, win_tile)
        assert result.error is None
        assert any(y.yaku_id == 122 and y.han == 3 for y in result.yaku)  # Ura Dora 3
