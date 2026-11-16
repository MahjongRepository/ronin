import pytest

from game.engine import (
    Action,
    Call,
    CallOpportunity,
    CallSource,
    Chi,
    Discard,
    GameEvent,
    GameRuntime,
    Kan,
    KanType,
    MahjongGameService,
    MeldEvent,
    Pass,
    Pon,
    Refusal,
    RefusalCode,
    RefusalKind,
    Riichi,
    Ron,
    Tsumo,
    Turn,
    TurnAfterCall,
    TurnAfterDraw,
)
from game.tests.helpers.hands import tile_copies
from game.tests.helpers.start_wall import make_start_wall

SEED = "5" * 192
DEALER = 0


def _start(hands: tuple[list[int], ...], draws: list[int]) -> tuple[MahjongGameService, GameRuntime]:
    service = MahjongGameService()
    runtime, _ = service.new_game(SEED, walls=[make_start_wall(hands, draws=draws)])
    service.begin_round(runtime)
    return service, runtime


def _play(service: MahjongGameService, runtime: GameRuntime, seat: int, action: Action) -> list[GameEvent]:
    events = service.act(runtime, seat, action)
    assert not isinstance(events, Refusal), events
    return events


def _assert_refused_unchanged(
    service: MahjongGameService, runtime: GameRuntime, seat: int, action: Action, refusal: Refusal
) -> None:
    state_before, awaiting_before = runtime.state, service.get_awaiting(runtime)
    decision_before = service.decision(runtime, seat)

    assert service.act(runtime, seat, action) == refusal
    assert runtime.state is state_before
    assert service.get_awaiting(runtime) == awaiting_before
    assert service.decision(runtime, seat) == decision_before


def test_decision__when_a_turn_follows_a_draw__should_offer_every_discard_then_the_riichi_discards():
    dealer_hand = tile_copies(0, man="123456789", pin="11", sou="45")
    drawn_nine_sou = tile_copies(0, sou="9")[0]
    service, runtime = _start((dealer_hand,), draws=[drawn_nine_sou])

    decision = service.decision(runtime, DEALER)
    assert decision is not None
    assert decision.context == TurnAfterDraw(drawn=drawn_nine_sou, rinshan=False, haitei=False)
    assert decision.legal == (
        *(Discard(tile=tile) for tile in (*dealer_hand, drawn_nine_sou)),
        Riichi(tile=drawn_nine_sou),
    )
    assert decision.default == Discard(tile=drawn_nine_sou)
    assert service.legal_actions(runtime, DEALER) == decision.legal


def test_decision__when_a_turn_follows_the_seats_own_chi__should_leave_out_the_kuikae_discards():
    three_man = tile_copies(0, man="3")[0]
    four_man = tile_copies(0, man="4")[0]
    plain_five_man, other_plain_five_man = tile_copies(1, man="5")[0], tile_copies(2, man="5")[0]
    six_man = tile_copies(1, man="6")[0]
    chi_seat_rest = [*tile_copies(1, pin="2468", sou="246"), *tile_copies(0, honors="12")]
    hands = (
        tile_copies(0, pin="123456789", sou="1239"),
        [four_man, plain_five_man, other_plain_five_man, six_man, *chi_seat_rest],
        tile_copies(2, pin="123456789", sou="1234"),
        tile_copies(3, pin="123456789", sou="5678"),
    )
    service, runtime = _start(hands, draws=[three_man])
    _play(service, runtime, DEALER, Discard(tile=three_man))
    assert service.legal_actions(runtime, 1) == (Chi(tiles=(four_man, plain_five_man)), Pass())

    chi_events = _play(service, runtime, 1, Chi(tiles=(four_man, other_plain_five_man)))
    assert [e.tile_ids for e in chi_events if isinstance(e, MeldEvent)] == [[three_man, four_man, other_plain_five_man]]

    decision = service.decision(runtime, 1)
    assert decision is not None
    assert decision.context == TurnAfterCall(kuikae=(2, 5))
    assert decision.legal == tuple(Discard(tile=tile) for tile in (plain_five_man, *chi_seat_rest))
    assert decision.default == Discard(tile=chi_seat_rest[-1])
    kuikae = Refusal(kind=RefusalKind.RULE, code=RefusalCode.KUIKAE)
    _assert_refused_unchanged(service, runtime, 1, Discard(tile=six_man), kuikae)


def test_decision__when_a_discard_offers_ron_and_chi__should_list_ron_each_chi_shape_then_pass():
    four_man = tile_copies(0, man="4")[0]
    two_man, three_man, red_five_man, six_man = tile_copies(0, man="2356")
    plain_five_man = tile_copies(1, man="5")[0]
    hands = (
        tile_copies(0, pin="56789", sou="3456789", honors="1"),
        [
            two_man,
            three_man,
            red_five_man,
            plain_five_man,
            six_man,
            *tile_copies(0, man="78", pin="234"),
            *tile_copies(0, sou="222"),
        ],
        tile_copies(1, pin="123456789", sou="3456"),
        tile_copies(2, pin="123456789", sou="3456"),
    )
    service, runtime = _start(hands, draws=[four_man])
    _play(service, runtime, DEALER, Discard(tile=four_man))

    decision = service.decision(runtime, 1)
    assert decision is not None
    assert decision.context == CallOpportunity(tile=four_man, from_seat=DEALER, source=CallSource.DISCARD, houtei=False)
    assert decision.legal == (
        Ron(),
        Chi(tiles=(red_five_man, six_man)),
        Chi(tiles=(plain_five_man, six_man)),
        Chi(tiles=(three_man, red_five_man)),
        Chi(tiles=(three_man, plain_five_man)),
        Chi(tiles=(two_man, three_man)),
        Pass(),
    )
    assert decision.default == Pass()
    for seat in (DEALER, 2, 3):
        assert service.decision(runtime, seat) is None
        assert service.legal_actions(runtime, seat) == ()
        assert service.default_action(runtime, seat) is None


def test_act__when_one_of_two_callers_passes__should_await_only_the_other_until_it_answers():
    four_man = tile_copies(0, man="4")[0]
    hands = (
        tile_copies(0, pin="123456789", sou="1239"),
        [*tile_copies(0, man="23"), *tile_copies(1, pin="2468", sou="2468"), *tile_copies(0, honors="123")],
        [*tile_copies(1, man="4"), *tile_copies(2, man="4"), *tile_copies(2, pin="123456789", honors="12")],
        tile_copies(3, pin="123456789", sou="1234"),
    )
    service, runtime = _start(hands, draws=[four_man])
    _play(service, runtime, DEALER, Discard(tile=four_man))
    assert service.get_awaiting(runtime) == Call(seats=frozenset({1, 2}))

    _play(service, runtime, 2, Pass())
    assert service.get_awaiting(runtime) == Call(seats=frozenset({1}))
    assert service.decision(runtime, 2) is None
    assert service.legal_actions(runtime, 1) == (Chi(tiles=tuple(tile_copies(0, man="23"))), Pass())
    already_answered = Refusal(kind=RefusalKind.NOT_AWAITED, code=RefusalCode.ALREADY_ANSWERED)
    _assert_refused_unchanged(service, runtime, 2, Pass(), already_answered)

    _play(service, runtime, 1, Pass())
    assert service.get_awaiting(runtime) == Turn(seat=1)


def test_decision__when_an_added_kan_can_be_robbed__should_offer_the_robber_ron_or_pass():
    red_five_pin, *held_five_pins = tile_copies(0, pin="5555")
    four_pin, six_pin = tile_copies(0, pin="4")[0], tile_copies(1, pin="6")[0]
    north, haku = tile_copies(0, honors="4")[0], tile_copies(1, honors="5")[0]
    hands = (
        [*tile_copies(0, pin="1236789"), *tile_copies(1, sou="2468"), *tile_copies(2, honors="12")],
        [*tile_copies(3, man="123456789"), *tile_copies(2, sou="2468")],
        [
            *held_five_pins,
            *tile_copies(2, man="1479"),
            *tile_copies(1, sou="3579"),
            haku,
            tile_copies(1, honors="6")[0],
        ],
        [*tile_copies(1, man="123456789"), *tile_copies(0, sou="11"), four_pin, north],
    )
    dealer_filler, seat_1_filler, seat_2_filler = (tile_copies(copy, honors="7")[0] for copy in (3, 2, 1))
    service, runtime = _start(hands, draws=[red_five_pin, six_pin, dealer_filler, seat_1_filler, seat_2_filler])
    _play(service, runtime, DEALER, Discard(tile=red_five_pin))
    assert service.legal_actions(runtime, 2) == (Kan(kan_type=KanType.OPEN, tile=red_five_pin), Pon(), Pass())

    pon_events = _play(service, runtime, 2, Pon())
    assert [e.tile_ids for e in pon_events if isinstance(e, MeldEvent)] == [[red_five_pin, *held_five_pins[:2]]]

    _play(service, runtime, 2, Discard(tile=haku))
    _play(service, runtime, 3, Discard(tile=north))
    _play(service, runtime, DEALER, Discard(tile=dealer_filler))
    _play(service, runtime, 1, Discard(tile=seat_1_filler))
    fourth_five_pin = held_five_pins[2]
    assert Kan(kan_type=KanType.ADDED, tile=fourth_five_pin) in service.legal_actions(runtime, 2)

    _play(service, runtime, 2, Kan(kan_type=KanType.ADDED, tile=red_five_pin))
    decision = service.decision(runtime, 3)
    assert decision is not None
    assert decision.context == CallOpportunity(
        tile=fourth_five_pin, from_seat=2, source=CallSource.ADDED_KAN, houtei=False
    )
    assert decision.legal == (Ron(), Pass())
    assert decision.default == Pass()


def test_default_action__when_the_drawn_tile_completes_the_hand__should_discard_it_rather_than_tsumo():
    dealer_hand = tile_copies(0, man="123456789", pin="11", sou="45")
    drawn_six_sou = tile_copies(0, sou="6")[0]
    service, runtime = _start((dealer_hand,), draws=[drawn_six_sou])

    assert Tsumo() in service.legal_actions(runtime, DEALER)
    assert service.default_action(runtime, DEALER) == Discard(tile=drawn_six_sou)


RIICHI_READY_HAND = tile_copies(0, man="123456789", pin="11", sou="45")
DRAWN_NINE_SOU = tile_copies(0, sou="9")[0]
SEAT_1_HAND = tile_copies(1, man="123456789", sou="1234")
SEAT_1_TILE = SEAT_1_HAND[0]
NOT_AWAITED = Refusal(kind=RefusalKind.NOT_AWAITED, code=RefusalCode.SEAT_NOT_AWAITED)


@pytest.mark.parametrize(
    ("seat", "action", "refusal"),
    [
        (
            DEALER,
            Riichi(tile=RIICHI_READY_HAND[0]),
            Refusal(kind=RefusalKind.RULE, code=RefusalCode.RIICHI_BREAKS_TENPAI),
        ),
        (DEALER, Discard(tile=SEAT_1_TILE), Refusal(kind=RefusalKind.NOT_OFFERED, code=RefusalCode.TILE_NOT_HELD)),
        (DEALER, Pass(), NOT_AWAITED),
        (1, Discard(tile=SEAT_1_TILE), NOT_AWAITED),
    ],
    ids=["riichi_breaking_tenpai", "tile_not_held", "pass_on_own_turn", "discard_out_of_turn"],
)
def test_act__when_the_action_is_refused__should_return_the_refusal_and_change_nothing(
    seat: int, action: Action, refusal: Refusal
):
    service, runtime = _start((RIICHI_READY_HAND, SEAT_1_HAND), draws=[DRAWN_NINE_SOU])

    _assert_refused_unchanged(service, runtime, seat, action, refusal)


def test_phase_calls__when_made_out_of_phase__should_be_refused_and_change_nothing():
    wrong_phase = Refusal(kind=RefusalKind.NOT_AWAITED, code=RefusalCode.WRONG_PHASE)
    service = MahjongGameService()
    runtime, _ = service.new_game(SEED, walls=[make_start_wall((RIICHI_READY_HAND,))])
    dealt = runtime.state

    assert service.act(runtime, DEALER, Discard(tile=RIICHI_READY_HAND[0])) == wrong_phase
    assert service.deal_next_round(runtime) == wrong_phase
    assert runtime.state is dealt

    assert not isinstance(service.begin_round(runtime), Refusal)
    playing = runtime.state
    assert service.begin_round(runtime) == wrong_phase
    assert service.deal_next_round(runtime) == wrong_phase
    assert runtime.state is playing
