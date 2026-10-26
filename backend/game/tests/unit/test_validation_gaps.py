from unittest.mock import patch

import pytest

from game.logic.abortive import can_call_kyuushu_kyuuhai
from game.logic.action_handlers import (
    handle_chi,
    handle_discard,
    handle_kan,
    handle_kyuushu,
    handle_pass,
    handle_pon,
    handle_riichi,
    handle_ron,
    handle_tsumo,
)
from game.logic.action_result import ActionResult, Refusal
from game.logic.ai_player import AIPlayer
from game.logic.ai_player_controller import AIPlayerController
from game.logic.enums import (
    AIPlayerType,
    GameAction,
    GameErrorCode,
    KanType,
    MeldCallType,
    TimeoutType,
)
from game.logic.events import SeatTarget
from game.logic.exceptions import GeneratedActionError, InvalidGameActionError
from game.logic.game import init_game
from game.logic.mahjong_service import MahjongGameService
from game.logic.meld_wrapper import FrozenMeld
from game.logic.riichi import can_declare_riichi
from game.logic.round import draw_tile
from game.logic.runtime import GameRuntime
from game.logic.state import (
    Caller,
    Discard,
    MahjongGameState,
    MeldOption,
)
from game.logic.tiles import tile_to_34
from game.logic.turn import process_discard_phase
from game.logic.types import (
    ChiActionData,
    DiscardActionData,
    KanActionData,
    PonActionData,
    RiichiActionData,
    SeatConfig,
)
from game.tests.conftest import create_dealt_game_state, create_player
from game.tests.helpers.hands import tile_copies
from game.tests.unit.helpers import _find_player, _update_round_state


def _default_seat_configs():
    return [
        SeatConfig(name="Player"),
        SeatConfig(name="AI1", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="AI2", ai_player_type=AIPlayerType.TSUMOGIRI),
        SeatConfig(name="AI3", ai_player_type=AIPlayerType.TSUMOGIRI),
    ]


def _create_frozen_game_state():
    game_state = init_game(_default_seat_configs(), seed="a" * 192, wall=list(range(136)))
    new_round_state, _tile = draw_tile(game_state.round_state)
    return game_state.model_copy(update={"round_state": new_round_state})


_NINE_MAN = tuple(tile_copies(copy, man="9")[0] for copy in range(4))
_CHI_SEAT_SIX_MAN, _CHI_SEAT_SEVEN_MAN, _CHI_SEAT_EIGHT_MAN = tile_copies(0, man="678")
_NINE_MAN_CALL_HANDS = (
    create_player(seat=0, tiles=(_NINE_MAN[0], *tile_copies(0, sou="123456789", honors="1234"))),
    create_player(seat=1, tiles=(*tile_copies(0, man="678", pin="159", honors="567"), *tile_copies(1, honors="1234"))),
    create_player(seat=2, tiles=(*_NINE_MAN[1:], *tile_copies(1, sou="123456789", honors="5"))),
    create_player(seat=3, tiles=(*tile_copies(2, honors="1234567"), *tile_copies(1, pin="234678"))),
)


def _nine_man_discard_prompt() -> MahjongGameState:
    prompted, _events = process_discard_phase(create_dealt_game_state(_NINE_MAN_CALL_HANDS), _NINE_MAN[0])
    prompt = prompted.round_state.pending_call_prompt
    assert prompt is not None
    assert prompt.callers == (
        Caller(seat=2, melds=(MeldOption(call_type=MeldCallType.OPEN_KAN), MeldOption(call_type=MeldCallType.PON))),
        Caller(
            seat=1,
            melds=(MeldOption(call_type=MeldCallType.CHI, options=((_CHI_SEAT_SEVEN_MAN, _CHI_SEAT_EIGHT_MAN),)),),
        ),
    )
    return prompted


class TestChiEarlyValidation:
    def test_chi_validation__when_seat_offered_pon_and_chi_sends_an_offered_chi__should_accept_it(self):
        pon_and_chi_seat = create_player(
            seat=1,
            tiles=(
                *_NINE_MAN[1:3],
                *tile_copies(0, man="78", pin="159", honors="567"),
                *tile_copies(1, honors="123"),
            ),
        )
        players = (
            _NINE_MAN_CALL_HANDS[0],
            pon_and_chi_seat,
            create_player(seat=2, tiles=(_NINE_MAN[3], *tile_copies(1, sou="123456789", honors="567"))),
            _NINE_MAN_CALL_HANDS[3],
        )
        prompted, _events = process_discard_phase(create_dealt_game_state(players), _NINE_MAN[0])
        prompt = prompted.round_state.pending_call_prompt
        assert prompt is not None
        assert [(c.seat, [m.call_type for m in c.melds]) for c in prompt.callers] == [
            (1, [MeldCallType.PON, MeldCallType.CHI]),
        ]

        sequence_tiles = (_CHI_SEAT_SEVEN_MAN, _CHI_SEAT_EIGHT_MAN)
        chi = handle_chi(prompted, seat=1, data=ChiActionData(tile_id=_NINE_MAN[0], sequence_tiles=sequence_tiles))
        assert isinstance(chi, ActionResult)
        assert [m.type for m in chi.state.round_state.players[1].melds] == [FrozenMeld.CHI]

    @pytest.mark.parametrize(
        ("sequence_tiles", "reason"),
        [
            pytest.param((_CHI_SEAT_SEVEN_MAN, tile_copies(1, man="8")[0]), "not in hand", id="tile_not_in_hand"),
            pytest.param((_CHI_SEAT_SIX_MAN, _CHI_SEAT_EIGHT_MAN), "not among available", id="not_a_run"),
        ],
    )
    def test_chi_validation__when_sequence_tiles_are_not_an_offered_chi__should_raise(self, sequence_tiles, reason):
        game_state = _nine_man_discard_prompt()
        data = ChiActionData(tile_id=_NINE_MAN[0], sequence_tiles=sequence_tiles)

        with pytest.raises(InvalidGameActionError, match=reason):
            handle_chi(game_state, seat=1, data=data)


class TestCallTileMismatch:
    @pytest.mark.parametrize(
        ("submit", "refusal_code"),
        [
            pytest.param(
                lambda gs: handle_pon(gs, seat=2, data=PonActionData(tile_id=_NINE_MAN[1])),
                GameErrorCode.INVALID_PON,
                id="pon",
            ),
            pytest.param(
                lambda gs: handle_kan(gs, seat=2, data=KanActionData(tile_id=_NINE_MAN[1], kan_type=KanType.OPEN)),
                GameErrorCode.INVALID_KAN,
                id="open_kan",
            ),
            pytest.param(
                lambda gs: handle_chi(
                    gs,
                    seat=1,
                    data=ChiActionData(tile_id=_NINE_MAN[1], sequence_tiles=(_CHI_SEAT_SEVEN_MAN, _CHI_SEAT_EIGHT_MAN)),
                ),
                GameErrorCode.INVALID_CHI,
                id="chi",
            ),
        ],
    )
    def test_call_response__when_tile_id_mismatches_prompt__should_refuse(self, submit, refusal_code):
        game_state = _nine_man_discard_prompt()

        result = submit(game_state)
        assert result == Refusal(code=refusal_code, message="tile_id mismatch")


_THREE_PIN = tile_copies(3, pin="3")[0]
_ONE_TWO_PIN = tuple(tile_copies(0, pin="12"))


class TestResponseActionMatchesPrompt:
    @pytest.mark.parametrize(
        ("submit", "offered"),
        [
            pytest.param(
                lambda gs: handle_pon(gs, seat=1, data=PonActionData(tile_id=_THREE_PIN)), "call_ron", id="pon"
            ),
            pytest.param(
                lambda gs: handle_chi(gs, seat=2, data=ChiActionData(tile_id=_THREE_PIN, sequence_tiles=_ONE_TWO_PIN)),
                "call_pon",
                id="chi",
            ),
            pytest.param(
                lambda gs: handle_kan(gs, seat=2, data=KanActionData(tile_id=_THREE_PIN, kan_type=KanType.OPEN)),
                "call_pon",
                id="open_kan",
            ),
            pytest.param(lambda gs: handle_ron(gs, seat=2), "call_pon", id="ron"),
        ],
    )
    def test_response_action__when_seat_sends_a_call_it_was_not_offered__should_raise(self, submit, offered):
        riichi_penchan_on_three_pin = create_player(
            seat=1,
            tiles=tile_copies(0, man="123456789", pin="1255"),
            discards=(Discard(tile_id=tile_copies(0, honors="7")[0], is_riichi_discard=True),),
            is_riichi=True,
        )
        players = (
            create_player(seat=0, tiles=(*tile_copies(0, sou="123456789", honors="1122"), _THREE_PIN)),
            riichi_penchan_on_three_pin,
            create_player(
                seat=2, tiles=(*tile_copies(1, pin="33"), *tile_copies(1, man="1357", sou="13579", honors="34"))
            ),
            create_player(seat=3, tiles=(*tile_copies(2, sou="123456789"), *tile_copies(2, honors="1234"))),
        )
        prompted, _events = process_discard_phase(create_dealt_game_state(players), _THREE_PIN)
        prompt = prompted.round_state.pending_call_prompt
        assert prompt is not None
        assert prompt.callers == (
            Caller(seat=1, can_ron=True),
            Caller(seat=2, melds=(MeldOption(call_type=MeldCallType.PON),)),
        )

        with pytest.raises(InvalidGameActionError, match=f"does not match available call types: {offered}$"):
            submit(prompted)


_FIVE_PIN = tuple(tile_copies(0, pin="5555"))
_SEAT_1_PON_HAND_WITHOUT_FIVE_PIN = tuple(tile_copies(0, man="123456789", honors="56"))


def _seat_1_to_play(hand: tuple[int, ...], *, has_five_pin_pon: bool) -> MahjongGameState:
    five_pin_pon = FrozenMeld(
        meld_type=FrozenMeld.PON, tiles=_FIVE_PIN[:3], opened=True, called_tile=_FIVE_PIN[2], who=1, from_who=3
    )
    players = (
        create_player(seat=0, tiles=tile_copies(0, sou="123456789", honors="1234")),
        create_player(seat=1, tiles=hand, melds=(five_pin_pon,) if has_five_pin_pon else ()),
        create_player(seat=2, tiles=tile_copies(1, man="123456789", honors="2345")),
        create_player(
            seat=3,
            tiles=tile_copies(2, man="123456789", honors="2345"),
            discards=(Discard(tile_id=_FIVE_PIN[2]),) if has_five_pin_pon else (),
        ),
    )
    return create_dealt_game_state(players, current_player_seat=1)


class TestAddedKanDeclarationValidation:
    def test_added_kan__when_seat_holds_a_triplet_but_no_pon__should_raise(self):
        game_state = _seat_1_to_play((*_FIVE_PIN[:3], *_SEAT_1_PON_HAND_WITHOUT_FIVE_PIN), has_five_pin_pon=False)

        data = KanActionData(tile_id=_FIVE_PIN[0], kan_type=KanType.ADDED)
        with pytest.raises(InvalidGameActionError, match="no pon of tile type"):
            handle_kan(game_state, seat=1, data=data)

    def test_added_kan__when_seat_holds_no_fourth_copy__should_raise(self):
        game_state = _seat_1_to_play(_SEAT_1_PON_HAND_WITHOUT_FIVE_PIN, has_five_pin_pon=True)
        assert _FIVE_PIN[3] in game_state.round_state.wall.live_tiles

        data = KanActionData(tile_id=_FIVE_PIN[3], kan_type=KanType.ADDED)
        with pytest.raises(InvalidGameActionError, match="not in hand"):
            handle_kan(game_state, seat=1, data=data)

    def test_added_kan__when_tile_id_names_a_melded_copy__should_kan_the_copy_in_hand(self):
        hand = (_FIVE_PIN[3], *_SEAT_1_PON_HAND_WITHOUT_FIVE_PIN[:-1])
        game_state = _seat_1_to_play(hand, has_five_pin_pon=True)

        result = handle_kan(game_state, seat=1, data=KanActionData(tile_id=_FIVE_PIN[0], kan_type=KanType.ADDED))
        assert isinstance(result, ActionResult)
        seat_1 = result.state.round_state.players[1]
        assert [(m.type, m.tiles) for m in seat_1.melds] == [(FrozenMeld.SHOUMINKAN, _FIVE_PIN)]
        assert _FIVE_PIN[3] not in seat_1.tiles

    def test_added_kan__when_player_in_riichi__should_raise(self):
        drawn_one_man = tile_copies(3, man="1")[0]
        riichi_seat = create_player(
            seat=0,
            tiles=(*tile_copies(0, man="111", pin="456789", sou="2345"), drawn_one_man),
            discards=(Discard(tile_id=tile_copies(0, honors="1")[0], is_riichi_discard=True),),
            is_riichi=True,
        )
        players = (
            riichi_seat,
            *(
                create_player(
                    seat=seat, tiles=(*tile_copies(seat, pin="123456789"), *tile_copies(seat - 1, honors="2345"))
                )
                for seat in range(1, 4)
            ),
        )
        game_state = create_dealt_game_state(players)

        data = KanActionData(tile_id=drawn_one_man, kan_type=KanType.ADDED)
        with pytest.raises(InvalidGameActionError, match="cannot call added kan while in riichi"):
            handle_kan(game_state, seat=0, data=data)


class TestKanExecutionGuards:
    def test_closed_kan__when_wall_too_short__should_raise(self):
        runtime = GameRuntime(game_id="test", state=_create_frozen_game_state(), ai=AIPlayerController({}))
        wall = runtime.state.round_state.wall
        _update_round_state(runtime, wall=wall.model_copy(update={"live_tiles": wall.live_tiles[:1]}))
        one_man_quad = runtime.state.round_state.players[0].tiles[:4]
        assert len({tile_to_34(t) for t in one_man_quad}) == 1

        data = KanActionData(tile_id=one_man_quad[0], kan_type=KanType.CLOSED)
        with pytest.raises(InvalidGameActionError, match="not enough tiles in wall"):
            handle_kan(runtime.state, seat=0, data=data)

    def test_added_kan__when_total_kans_at_limit__should_raise(self):
        five_pin = tile_copies(0, pin="5555")
        seat_0_quads = tuple(
            FrozenMeld(meld_type=FrozenMeld.KAN, tiles=tuple(tile_copies(0, sou=quad)), opened=False, who=0)
            for quad in ("1111", "2222", "3333", "4444")
        )
        five_pin_pon = FrozenMeld(
            meld_type=FrozenMeld.PON, tiles=five_pin[:3], opened=True, called_tile=five_pin[2], who=1, from_who=3
        )
        players = (
            create_player(seat=0, tiles=tile_copies(0, honors="7"), melds=seat_0_quads),
            create_player(
                seat=1, tiles=(five_pin[3], *tile_copies(0, man="123456789", honors="1")), melds=(five_pin_pon,)
            ),
            create_player(seat=2, tiles=tile_copies(1, man="123456789", honors="2345")),
            create_player(
                seat=3,
                tiles=tile_copies(2, man="123456789", honors="2345"),
                discards=(Discard(tile_id=five_pin[2]),),
            ),
        )
        game_state = create_dealt_game_state(players, current_player_seat=1)

        data = KanActionData(tile_id=five_pin[3], kan_type=KanType.ADDED)
        with pytest.raises(InvalidGameActionError, match="maximum kans per round"):
            handle_kan(game_state, seat=1, data=data)


_TENPAI_DEALER_AFTER_DRAW = tuple(tile_copies(0, man="112345", pin="456", sou="789", honors="11"))
_RIICHI_JUNK_HANDS = {seat: tuple(tile_copies(seat, man="6789", pin="12389", sou="1234")) for seat in (1, 2, 3)}


def _tenpai_dealer_after_draw() -> MahjongGameState:
    players = (
        create_player(seat=0, tiles=_TENPAI_DEALER_AFTER_DRAW),
        *(create_player(seat=seat, tiles=_RIICHI_JUNK_HANDS[seat]) for seat in (1, 2, 3)),
    )
    return create_dealt_game_state(players)


class TestRiichiDiscardTenpaiValidation:
    def test_riichi_discard__when_discard_breaks_tenpai__should_refuse_with_invalid_riichi(self):
        three_man = tile_copies(0, man="3")[0]

        result = handle_riichi(_tenpai_dealer_after_draw(), seat=0, data=RiichiActionData(tile_id=three_man))
        assert result == Refusal(
            code=GameErrorCode.INVALID_RIICHI, message=f"hand is not tenpai after discarding tile {three_man}"
        )


class TestRiichiRaisesInvalidGameActionError:
    def test_riichi__when_riichi_not_offered__should_raise_invalid_game_action(self):
        game_state = _create_frozen_game_state()
        dealer = game_state.round_state.players[0]
        assert not can_declare_riichi(dealer, game_state.round_state, settings=game_state.settings)

        with pytest.raises(InvalidGameActionError, match="cannot declare riichi: conditions not met"):
            handle_riichi(game_state, seat=0, data=RiichiActionData(tile_id=dealer.tiles[-1]))

    def test_riichi__when_tenpai_hand_and_tile_not_in_hand__should_raise(self):
        game_state = _tenpai_dealer_after_draw()
        other_seats_tile = game_state.round_state.players[1].tiles[0]

        with pytest.raises(InvalidGameActionError, match="not in hand"):
            handle_riichi(game_state, seat=0, data=RiichiActionData(tile_id=other_seats_tile))


class TestKyuushuRuleGate:
    def test_kyuushu_kyuuhai__when_conditions_not_met__should_raise(self):
        game_state = _create_frozen_game_state()
        dealer = game_state.round_state.players[0]
        assert not can_call_kyuushu_kyuuhai(dealer, game_state.round_state, settings=game_state.settings)

        with pytest.raises(InvalidGameActionError, match="conditions not met"):
            handle_kyuushu(game_state, seat=0)

    def test_kyuushu_kyuuhai__when_not_players_turn__should_refuse(self):
        game_state = _create_frozen_game_state()

        result = handle_kyuushu(game_state, seat=1)
        assert isinstance(result, Refusal)
        assert result.code == GameErrorCode.NOT_YOUR_TURN


class TestPendingCallPromptStateGate:
    @pytest.mark.parametrize(
        ("action", "data"),
        [
            (GameAction.DISCARD, {"tile_id": "own"}),
            (GameAction.DECLARE_RIICHI, {"tile_id": "own"}),
            (GameAction.DECLARE_TSUMO, {}),
            (GameAction.CALL_KYUUSHU, {}),
            (GameAction.CALL_KAN, {"tile_id": "own", "kan_type": KanType.CLOSED}),
            (GameAction.CALL_KAN, {"tile_id": "own", "kan_type": KanType.ADDED}),
        ],
        ids=["discard", "riichi", "tsumo", "kyuushu", "closed_kan", "added_kan"],
    )
    def test_turn_action__when_prompt_pending__should_answer_not_your_turn_without_kick(self, action, data):
        game_state = _nine_man_discard_prompt()
        runtime = GameRuntime(game_id="test", state=game_state, ai=AIPlayerController({}))
        own_tile = game_state.round_state.players[0].tiles[-1]

        action_data = {key: own_tile if value == "own" else value for key, value in data.items()}
        update = MahjongGameService().handle_action(runtime, seat=0, action=action, data=action_data)
        assert [(e.data.code, e.data.target) for e in update.events] == [
            (GameErrorCode.NOT_YOUR_TURN, SeatTarget(seat=0))
        ]
        assert runtime.state is game_state
        assert update.awaiting.wait_id == game_state.wait_id


def _kuikae_seat_after_chi() -> tuple[MahjongGameState, int, int]:
    passed = handle_pass(_nine_man_discard_prompt(), seat=2)
    sequence_tiles = (_CHI_SEAT_SEVEN_MAN, _CHI_SEAT_EIGHT_MAN)
    chi = handle_chi(passed.state, seat=1, data=ChiActionData(tile_id=_NINE_MAN[0], sequence_tiles=sequence_tiles))
    assert isinstance(chi, ActionResult)
    assert tile_to_34(_CHI_SEAT_SIX_MAN) in chi.state.round_state.players[1].kuikae_tiles
    return chi.state, 1, _CHI_SEAT_SIX_MAN


def _riichi_dealer_after_draw() -> tuple[MahjongGameState, int, int]:
    waiting_hand = tile_copies(0, man="11234", pin="456", sou="789", honors="11")
    riichi_dealer = create_player(
        seat=0,
        tiles=(*waiting_hand, tile_copies(0, man="9")[0]),
        discards=(Discard(tile_id=tile_copies(0, honors="7")[0], is_riichi_discard=True),),
        is_riichi=True,
    )
    players = (riichi_dealer, *(create_player(seat=seat, tiles=_RIICHI_JUNK_HANDS[seat]) for seat in (1, 2, 3)))
    return create_dealt_game_state(players), 0, waiting_hand[0]


class TestSoftErrorsRemainUnchanged:
    @pytest.mark.parametrize(
        "stage_forbidden_discard",
        [pytest.param(_kuikae_seat_after_chi, id="kuikae"), pytest.param(_riichi_dealer_after_draw, id="riichi")],
    )
    def test_discard__when_rule_forbids_the_tile__should_refuse_with_invalid_discard(self, stage_forbidden_discard):
        game_state, seat, forbidden_tile = stage_forbidden_discard()

        result = handle_discard(game_state, seat=seat, data=DiscardActionData(tile_id=forbidden_tile))
        assert isinstance(result, Refusal)
        assert result.code == GameErrorCode.INVALID_DISCARD

    def test_soft_error__when_not_your_turn__should_return_refusal(self):
        game_state = _create_frozen_game_state()

        result = handle_discard(game_state, seat=1, data=DiscardActionData(tile_id=0))
        assert isinstance(result, Refusal)
        assert result.code == GameErrorCode.NOT_YOUR_TURN

    def test_soft_error__when_ron_without_pending_prompt__should_return_refusal(self):
        game_state = _create_frozen_game_state()

        result = handle_ron(game_state, seat=0)
        assert isinstance(result, Refusal)
        assert result.code == GameErrorCode.INVALID_RON

    def test_soft_error__when_pass_without_prompt__should_return_refusal(self):
        game_state = _create_frozen_game_state()

        result = handle_pass(game_state, seat=0)
        assert isinstance(result, Refusal)
        assert result.code == GameErrorCode.INVALID_PASS

    def test_soft_error__when_seat_not_pending__should_return_refusal(self):
        result = handle_ron(_nine_man_discard_prompt(), seat=3)
        assert result == Refusal(code=GameErrorCode.INVALID_RON, message="no pending call prompt")


# --- Phase 3: Error Handling Conversion Tests ---


class TestDiscardRaisesInvalidGameActionError:
    def test_discard__when_tile_not_in_hand__should_raise_invalid_game_action(self):
        game_state = _create_frozen_game_state()

        with pytest.raises(InvalidGameActionError, match="discard") as exc_info:
            handle_discard(game_state, seat=0, data=DiscardActionData(tile_id=999))
        assert exc_info.value.seat == 0


class TestTsumoRaisesInvalidGameActionError:
    def test_tsumo__when_hand_not_winning__should_raise_invalid_game_action(self):
        game_state = _create_frozen_game_state()

        with pytest.raises(InvalidGameActionError, match="declare_tsumo") as exc_info:
            handle_tsumo(game_state, seat=0)
        assert exc_info.value.seat == 0


class TestKanRaisesInvalidGameActionError:
    def test_closed_kan__when_seat_holds_three_copies__should_raise_invalid_game_action(self):
        one_man_triplet = tile_copies(0, man="111")
        dealer = create_player(seat=0, tiles=(*one_man_triplet, *tile_copies(0, pin="123456789", sou="12")))
        players = (
            dealer,
            *(
                create_player(
                    seat=seat, tiles=(*tile_copies(seat, pin="123456789"), *tile_copies(seat - 1, honors="2345"))
                )
                for seat in range(1, 4)
            ),
        )
        game_state = create_dealt_game_state(players)

        data = KanActionData(tile_id=one_man_triplet[0], kan_type=KanType.CLOSED)
        with pytest.raises(InvalidGameActionError, match="closed kan requires 4 tiles"):
            handle_kan(game_state, seat=0, data=data)


class TestServerGeneratedActionRefusals:
    @pytest.fixture
    def service(self):
        return MahjongGameService()

    @pytest.fixture
    def runtime(self, service):
        return service.start_game("test", ["Player"], seed="a" * 192).runtime

    def test_ai_call_response__when_handler_refuses_it__should_raise_generated_action_error(self, service):
        game_state = _nine_man_discard_prompt()
        runtime = GameRuntime(game_id="test", state=game_state, ai=AIPlayerController({1: AIPlayer()}))
        prompt = game_state.round_state.pending_call_prompt
        unheld_sequence = (_CHI_SEAT_SEVEN_MAN, tile_copies(1, man="8")[0])

        with (
            patch.object(AIPlayer, "should_call_chi", return_value=unheld_sequence),
            pytest.raises(GeneratedActionError, match="call_chi refused"),
        ):
            service._dispatch_ai_player_call_responses(runtime, prompt, [])
        assert runtime.state.round_state.pending_call_prompt == prompt

    def test_ai_turn__when_its_discard_gets_a_soft_error__should_raise_without_progress(self, service):
        game_state, ai_seat, forbidden_tile = _riichi_dealer_after_draw()
        runtime = GameRuntime(game_id="test", state=game_state, ai=AIPlayerController({ai_seat: AIPlayer()}))

        with (
            patch.object(AIPlayer, "select_discard", return_value=forbidden_tile),
            pytest.raises(GeneratedActionError, match="invalid_discard"),
        ):
            service._process_ai_player_followup(runtime)
        assert runtime.state is game_state

    def test_turn_timeout__when_default_discard_is_refused__should_raise_instead_of_kicking(self, service, runtime):
        player_seat = _find_player(runtime.state.round_state, "Player").seat
        assert runtime.state.round_state.current_player_seat == player_seat

        with (
            patch("game.logic.mahjong_service.choose_default_discard", return_value=999),
            pytest.raises(GeneratedActionError, match="discard refused") as exc_info,
        ):
            service.handle_timeout(runtime, seat=player_seat, timeout_type=TimeoutType.TURN)
        assert isinstance(exc_info.value.__cause__, InvalidGameActionError)

    def test_round_advance_timeout__when_no_round_awaits_confirmation__should_raise(self, service, runtime):
        player_seat = _find_player(runtime.state.round_state, "Player").seat
        with pytest.raises(GeneratedActionError, match="no round pending confirmation"):
            service.handle_timeout(runtime, seat=player_seat, timeout_type=TimeoutType.ROUND_ADVANCE)

    def test_handle_action__when_the_seat_is_ai_controlled__should_raise_as_a_server_fault(self, service, runtime):
        ai_player_seat = min(runtime.ai.ai_player_seats)
        state_before = runtime.state

        with pytest.raises(AssertionError, match=f"seat {ai_player_seat} is controlled by an AI player"):
            service.handle_action(runtime, seat=ai_player_seat, action=GameAction.DISCARD, data={"tile_id": 0})
        assert runtime.state is state_before
