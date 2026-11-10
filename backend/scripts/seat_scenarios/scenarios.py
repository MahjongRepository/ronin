from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from game.logic.enums import KanType
from game.logic.settings import EnchousenType, GameSettings, GameType
from game.messaging.types import SessionMessageType
from game.tests.helpers.hands import tile_copies
from game.wire.enums import WireEventType
from scripts.replay_fixtures.staged_game import StagedWall, tile
from scripts.seat_scenarios.harness import SCENARIO_START_CONFIRM_SECONDS, seated_game

if TYPE_CHECKING:
    from collections.abc import Callable

    from scripts.seat_scenarios.harness import SeatTranscript

PLAYER = "Alice"
ROBBER = "Bob"
OWN_TURN_RINSHAN = tile(0, honors="4")
START_CONFIRMED_AT = 3


def call_prompt() -> tuple[SeatTranscript, ...]:
    """
    Offer Alice, the one human at the table (seat 1), a pon, an open kan and a chi two ways on the dealer's 3m; she
    calls chi, and her turn after it opens with the tile types kuikae forbids. Her socket dies unseen during that turn,
    and her reconnect takes it over: the snapshot, then the turn re-sent with its kuikae types and the time its timer
    has run.

    Seat 2's draw reaches her as its notice before its 7s; she passes the pon of them, and her next draw opens her next
    turn with what is left of her bank.
    """
    called_tile = tile(0, man="3")
    ponnable_tile = tile(2, sou="7")
    staged = StagedWall(
        hands=(
            tile_copies(3, man="1245689", pin="13579", sou="1"),
            (
                *tile_copies(0, man="12"),
                *(tile(copy, man="3") for copy in range(1, 4)),
                *tile_copies(0, man="4", pin="678", sou="2"),
                *tile_copies(0, sou="7"),
                tile(1, sou="7"),
                tile(0, honors="3"),
            ),
            tile_copies(2, man="1245689", pin="24689", sou="2"),
            tile_copies(1, man="12456", pin="1359", sou="4569"),
        ),
        draws=(
            (0, called_tile),
            (2, ponnable_tile),
            (3, tile(0, honors="7")),
            (0, tile(0, honors="6")),
            (1, tile(0, sou="1")),
        ),
    )

    with seated_game("seat-call-prompt", staged, players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.label("dealt", WireEventType.ROUND_STARTED)
        alice.label("prompt", WireEventType.CALL_PROMPT)
        alice.chi(called_tile, (tile(0, man="1"), tile(0, man="2")), at=5, label="chi chosen")
        alice.label("turn", WireEventType.TURN)
        alice.drop_unseen(at=6, label="dropped")
        alice.reconnect(at=7, label="reopened")
        alice.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        alice.label("turn re-sent", WireEventType.TURN)
        alice.discard(tile(0, honors="3"), at=12, label="discarded")
        alice.label("pon prompt", WireEventType.CALL_PROMPT)
        alice.label("seat 2 drew", WireEventType.DRAW_NOTICE)
        alice.pass_(at=14, label="passed")
        alice.label("next turn", WireEventType.DRAW)

        return game.transcripts("call_prompt", PLAYER)


def kan_choice() -> tuple[SeatTranscript, ...]:
    """
    Deal Alice (seat 1) four 1m and three 9p, then draw her the fourth 9p: her turn offers a closed kan of either.

    She declares the kan of 9p and draws its rinshan tile.
    """
    staged = StagedWall(
        hands=(
            tile_copies(1, man="2345678", pin="12", sou="1346"),
            (
                *(tile(copy, man="1") for copy in range(4)),
                *(tile(copy, pin="9") for copy in range(3)),
                *tile_copies(0, pin="246", sou="258"),
            ),
            tile_copies(2, man="2345678", pin="12", sou="1346"),
            tile_copies(3, man="2345678", pin="12", sou="1346"),
        ),
        draws=(
            (0, tile(0, honors="1")),
            (1, tile(3, pin="9")),
        ),
        rinshan=(tile(0, honors="4"),),
    )

    with seated_game("seat-kan-choice", staged, players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.label("dealt", WireEventType.ROUND_STARTED)
        alice.label("kan offer", WireEventType.DRAW)
        alice.kan(tile(0, pin="9"), KanType.CLOSED, at=5, label="kan chosen")
        alice.label("rinshan", WireEventType.DRAW)

        return game.transcripts("kan_choice", PLAYER)


def _own_turn_wall() -> StagedWall:
    """
    Deal Alice (seat 1) three 1m, a ready shape waiting on 6s or 9s once a 1m goes, and draw her the fourth 1m; seat 2
    then draws and discards the 6s.
    """
    return StagedWall(
        hands=(
            tile_copies(3, man="2456789", pin="19", sou="1234"),
            (
                *(tile(copy, man="1") for copy in range(3)),
                *tile_copies(0, pin="234"),
                *tile_copies(1, pin="567"),
                *tile_copies(0, sou="78"),
                tile(1, sou="5"),
                tile(2, sou="5"),
            ),
            tile_copies(2, man="2345678", pin="123", sou="123"),
            tile_copies(1, man="2345678", pin="189", sou="123"),
        ),
        draws=(
            (0, tile(0, honors="2")),
            (1, tile(3, man="1")),
            (2, tile(0, sou="6")),
            (3, tile(0, honors="3")),
            (0, tile(0, honors="6")),
            (1, tile(0, sou="9")),
        ),
        rinshan=(OWN_TURN_RINSHAN,),
    )


def own_turn() -> tuple[SeatTranscript, ...]:
    """
    Seat Alice (seat 1), who confirms the game's start over the deal, then draw her the fourth of her three 1m, which
    offers a closed kan and riichi.

    Her socket dies unseen during the turn, and her reconnect takes it over: the snapshot, then the draw re-sent with
    the time its timer has run. She declares the kan and riichi on its rinshan draw.

    She passes a ron on seat 2's 6s, which leaves her furiten, wins by tsumo on her next draw, and presses OK on the
    round end a second after it, after which she deals the next round from the seed.
    """
    with seated_game("seat-own-turn", _own_turn_wall(), players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        alice.label("game started", WireEventType.GAME_STARTED)
        alice.label("dealt", WireEventType.ROUND_STARTED)
        alice.drop_unseen(at=3.5, label="dropped")
        alice.label("first draw", WireEventType.DRAW)
        alice.reconnect(at=4.5, label="reopened")
        alice.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        alice.label("draw re-sent", WireEventType.DRAW)
        alice.kan(tile(0, man="1"), KanType.CLOSED, at=5, label="kan chosen")
        alice.label("rinshan", WireEventType.DRAW)
        alice.riichi(OWN_TURN_RINSHAN, at=11, label="riichi chosen")
        alice.label("ron prompt", WireEventType.CALL_PROMPT)
        alice.pass_(at=13, label="passed")
        alice.label("furiten", WireEventType.FURITEN)
        alice.label("tsumo draw", WireEventType.DRAW)
        alice.tsumo(at=15, label="tsumo chosen")
        alice.label("round end", WireEventType.ROUND_END)
        alice.confirm_round(at=16, label="confirmed")
        alice.label("next round", WireEventType.ROUND_STARTED)
        alice.label("dealer draw", WireEventType.DRAW)

        return game.transcripts("own_turn", PLAYER)


def riichi_kan() -> tuple[SeatTranscript, ...]:
    """
    Offer a concealed kan after Alice declares riichi, then tsumo on its replacement draw.
    """
    declaration = tile(0, honors="4")
    staged = replace(
        _own_turn_wall(),
        draws=(
            (0, tile(0, honors="2")),
            (1, declaration),
            (2, tile(0, honors="3")),
            (3, tile(0, honors="6")),
            (0, tile(0, honors="7")),
            (1, tile(3, man="1")),
        ),
        rinshan=(tile(0, sou="9"),),
    )

    with seated_game("seat-riichi-kan", staged, players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.label("riichi offer", WireEventType.DRAW)
        alice.riichi(declaration, at=5, label="riichi chosen")
        alice.label("kan offer", WireEventType.DRAW)
        alice.kan(tile(0, man="1"), KanType.CLOSED, at=6, label="kan chosen")
        alice.label("tsumo draw", WireEventType.DRAW)

        return game.transcripts("riichi_kan", PLAYER)


def bank_reconnect() -> tuple[SeatTranscript, ...]:
    """
    Alice's (seat 1) socket dies unseen during her first turn, and she reconnects only after its base time ran out: the
    draw re-sent says how far into her bank the turn has run.

    She discards from the bank.
    """
    with seated_game("seat-bank-reconnect", _own_turn_wall(), players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.label("first draw", WireEventType.DRAW)
        alice.drop_unseen(at=8.5, label="dropped")
        alice.reconnect(at=9.5, label="reopened")
        alice.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        alice.label("draw re-sent", WireEventType.DRAW)
        alice.discard(tile(3, man="1"), at=11, label="discarded")

        return game.transcripts("bank_reconnect", PLAYER)


def reconnect() -> tuple[SeatTranscript, ...]:
    """
    Offer Alice (seat 1) a pon of the dealer's haku; her socket dies unseen, so the server keeps her seat and the wait,
    and her reconnect takes the half-open connection over: the snapshot, then the prompt re-sent with the time its timer
    has run. She pons, discards into a ready hand and rons seat 2's 6s; during the round advance another tab of hers
    takes the seat over, closing her socket with 4002.
    """
    haku = tile(2, honors="5")
    junk = tile(0, honors="4")
    staged = StagedWall(
        hands=(
            tile_copies(3, man="156789", pin="1234", sou="123"),
            (
                *tile_copies(0, honors="5"),
                tile(1, honors="5"),
                *tile_copies(0, man="234", sou="78"),
                *tile_copies(1, pin="567"),
                tile(1, sou="5"),
                tile(2, sou="5"),
                junk,
            ),
            tile_copies(2, man="156789", pin="1234", sou="123"),
            tile_copies(1, man="156789", pin="1234", sou="123"),
        ),
        draws=((0, haku), (2, tile(0, sou="6"))),
    )

    with seated_game("seat-reconnect", staged, players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.label("prompt", WireEventType.CALL_PROMPT)
        alice.drop_unseen(at=4.5, label="dropped")
        alice.reconnect(at=5.5, label="reopened")
        alice.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        alice.label("prompt re-sent", WireEventType.CALL_PROMPT)
        alice.pon(haku, at=6.5, label="pon chosen")
        alice.label("turn", WireEventType.TURN)
        alice.discard(junk, at=8, label="discarded")
        alice.label("ron prompt", WireEventType.CALL_PROMPT)
        alice.ron(at=10, label="ron chosen")
        alice.label("round end", WireEventType.ROUND_END)
        alice.be_replaced_by_another_tab(at=10.5, label="replaced")

        return game.transcripts("reconnect", PLAYER)


def riichi_reconnect() -> tuple[SeatTranscript, ...]:
    """
    Declare riichi for Alice (seat 1) on her first draw, discarding a 1m; it passes, so the server takes her stick.

    The game's riichi cost is 2000 and a collected stick pays 1500, neither the default. Her socket dies unseen at seat
    2's 6s, and her reconnect takes it over: the snapshot, with her stick already taken, then the ron prompt sent again.
    She rons it and never confirms the round end, so the server's round advance timeout deals the next round while her
    result is still open. She plays no move after it: the server's timeouts play her seat, and the game, East only with
    no extension, ends with East 4.
    """
    settings = GameSettings(
        riichi_cost=2000, riichi_stick_value=1500, game_type=GameType.TONPUSEN, enchousen=EnchousenType.NONE
    )
    with seated_game("seat-riichi-reconnect", _own_turn_wall(), players=(PLAYER,), settings=settings) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.label("first draw", WireEventType.DRAW)
        alice.riichi(tile(0, man="1"), at=5, label="riichi chosen")
        alice.label("riichi accepted", WireEventType.RIICHI_DECLARED)
        alice.label("ron prompt", WireEventType.CALL_PROMPT)
        alice.drop_unseen(at=5.5, label="dropped")
        alice.reconnect(at=6.5, label="reopened")
        alice.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        alice.label("ron prompt re-sent", WireEventType.CALL_PROMPT)
        alice.ron(at=7, label="ron chosen")
        alice.label("round end", WireEventType.ROUND_END)
        game.wait_until(18)
        alice.label("next round", WireEventType.ROUND_STARTED)
        game.wait_until(6000)
        alice.label("game end", WireEventType.GAME_END)

        return game.transcripts("riichi_reconnect", PLAYER)


def chankan_robbed() -> tuple[SeatTranscript, ...]:
    """
    Alice (seat 1) declares a closed kan of 9m that Bob (seat 3), a kokushi musou hand waiting on 9m, robs: his chankan
    prompt shows the kan, her round end names it. Tobi is off, so the yakuman she pays leaves the game going.

    Her socket dies unseen during the round advance, before her client confirms it, and her reconnect takes it over: the
    snapshot carries the result and the kan it robbed, and she presses OK a second after it; Bob presses OK a second
    after the round end and waits for her. She deals the next round from the seed.
    """
    kan_tile = tile(0, man="9")
    staged = StagedWall(
        hands=(
            tile_copies(2, man="357", pin="357", sou="35789", honors="12"),
            (*(tile(copy, man="9") for copy in range(3)), *tile_copies(1, man="246", pin="2468", sou="246")),
            tile_copies(3, man="357", pin="357", sou="35789", honors="12"),
            tile_copies(0, man="11", pin="19", sou="19", honors="1234567"),
        ),
        draws=(
            (0, tile(1, honors="3")),
            (1, tile(1, honors="4")),
            (2, tile(1, honors="5")),
            (3, tile(1, honors="6")),
            (0, tile(1, honors="7")),
            (1, tile(3, man="9")),
        ),
    )

    settings = GameSettings(tobi_enabled=False)
    with seated_game("seat-chankan-robbed", staged, players=(PLAYER, ROBBER), settings=settings) as game:
        alice = game.clients[PLAYER]
        bob = game.clients[ROBBER]
        alice.join(at=0)
        bob.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        bob.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.discard(tile(1, honors="4"), at=5, label="discarded")
        bob.discard(tile(1, honors="6"), at=6, label="discarded")
        alice.label("kan draw", WireEventType.DRAW)
        alice.kan(kan_tile, KanType.CLOSED, at=7, label="kan chosen")
        bob.label("chankan prompt", WireEventType.CALL_PROMPT)
        bob.ron(at=8, label="ron chosen")
        bob.label("round end", WireEventType.ROUND_END)
        alice.label("round end", WireEventType.ROUND_END)
        alice.drop_unseen(at=8.25, label="dropped")
        bob.confirm_round(at=9, label="confirmed")
        alice.reconnect(at=9.25, label="reopened")
        alice.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        alice.confirm_round(at=10.25, label="confirmed")
        alice.label("next round", WireEventType.ROUND_STARTED)

        return game.transcripts("chankan_robbed", PLAYER, ROBBER)


def chankan_passed() -> tuple[SeatTranscript, ...]:
    """
    Alice (seat 1) pons the dealer's 6p and raises it to an added kan that Bob (seat 3), waiting on 6p, may rob: his
    chankan prompt shows the kan.

    His socket dies unseen during the prompt, and his reconnect takes it over: the snapshot, where Alice's hand still
    holds the kan's tile, then the prompt re-sent. He passes, and the server's meld completes the kan before Alice's
    rinshan draw.
    """
    ponned_tile = tile(2, pin="6")
    staged = StagedWall(
        hands=(
            tile_copies(2, man="258", pin="17", sou="369", honors="12345"),
            (*tile_copies(0, pin="66"), *tile_copies(1, man="147", pin="19", sou="258", honors="123")),
            tile_copies(3, man="258", pin="17", sou="369", honors="12345"),
            tile_copies(0, man="123456789", pin="45", sou="19"),
        ),
        draws=(
            (0, ponned_tile),
            (2, tile(0, honors="7")),
            (3, tile(1, sou="1")),
            (0, tile(1, honors="7")),
            (1, tile(3, pin="6")),
        ),
    )

    with seated_game("seat-chankan-passed", staged, players=(PLAYER, ROBBER)) as game:
        alice = game.clients[PLAYER]
        bob = game.clients[ROBBER]
        alice.join(at=0)
        bob.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        bob.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.pon(ponned_tile, at=5, label="pon chosen")
        alice.discard(tile(1, honors="1"), at=6, label="discarded")
        bob.discard(tile(0, sou="9"), at=7, label="discarded")
        alice.kan(tile(3, pin="6"), KanType.ADDED, at=8, label="kan chosen")
        bob.label("chankan prompt", WireEventType.CALL_PROMPT)
        bob.drop_unseen(at=8.25, label="dropped")
        bob.reconnect(at=9.25, label="reopened")
        bob.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        bob.label("prompt re-sent", WireEventType.CALL_PROMPT)
        bob.pass_(at=9.75, label="passed")
        bob.label("kan", WireEventType.MELD)

        return game.transcripts("chankan_passed", ROBBER)


def double_ron() -> tuple[SeatTranscript, ...]:
    """
    The dealer, an AI player, discards the 4p that Alice (seat 1) and Bob (seat 3) both wait on, and both ron it: a
    double ron with a result page per winner, Alice's first.

    Her socket dies unseen during the round advance, and her reconnect takes it over: the snapshot carries the same
    result with the time its timer has run, and she presses OK a second after it; Bob confirms a second after the round
    end. Tobi is off, so what the dealer pays leaves the game going.
    """
    winning_tile = tile(2, pin="4")
    staged = StagedWall(
        hands=(
            tile_copies(2, man="258", pin="258", sou="258", honors="1234"),
            tile_copies(0, man="234567", pin="23", sou="34566"),
            tile_copies(3, man="258", pin="258", sou="258", honors="1234"),
            (*tile_copies(1, man="345678", sou="234"), *tile_copies(0, pin="568"), tile(1, pin="8")),
        ),
        draws=((0, winning_tile),),
    )

    settings = GameSettings(tobi_enabled=False)
    with seated_game("seat-double-ron", staged, players=(PLAYER, ROBBER), settings=settings) as game:
        alice = game.clients[PLAYER]
        bob = game.clients[ROBBER]
        alice.join(at=0)
        bob.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        bob.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.label("ron prompt", WireEventType.CALL_PROMPT)
        alice.ron(at=5, label="ron chosen")
        bob.ron(at=5.5, label="ron chosen")
        alice.label("round end", WireEventType.ROUND_END)
        alice.drop_unseen(at=5.75, label="dropped")
        bob.confirm_round(at=6.5, label="confirmed")
        alice.reconnect(at=6.75, label="reopened")
        alice.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        alice.confirm_round(at=7.75, label="confirmed")
        alice.label("next round", WireEventType.ROUND_STARTED)

        return game.transcripts("double_ron", PLAYER)


def final_round() -> tuple[SeatTranscript, ...]:
    """
    Alice (seat 1), waiting on 9m with kokushi musou, rons the dealer's first discard: the AI dealer pays a yakuman and
    busts, so the game ends with this round.

    Its round end carries no wait id, and the game end follows it at once.
    """
    staged = StagedWall(
        hands=(
            tile_copies(2, man="258", pin="258", sou="258", honors="1234"),
            tile_copies(0, man="11", pin="19", sou="19", honors="1234567"),
            tile_copies(3, man="258", pin="258", sou="258", honors="1234"),
            (*tile_copies(1, man="345678", sou="234"), *tile_copies(0, pin="568"), tile(1, pin="8")),
        ),
        draws=((0, tile(0, man="9")),),
    )

    with seated_game("seat-final-round", staged, players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.label("ron prompt", WireEventType.CALL_PROMPT)
        alice.ron(at=5, label="ron chosen")
        alice.label("round end", WireEventType.ROUND_END)
        alice.label("game end", WireEventType.GAME_END)
        game.wait_until(6)

        return game.transcripts("final_round", PLAYER)


def _kyuushu_wall() -> StagedWall:
    """
    Deal Alice (seat 1) nine terminal and honor types, so that her first draw offers kyuushu kyuuhai alone.
    """
    return StagedWall(
        hands=(
            tile_copies(2, man="258", pin="258", sou="258", honors="1234"),
            tile_copies(0, man="159", pin="159", sou="159", honors="1234"),
            tile_copies(3, man="258", pin="258", sou="258", honors="1234"),
            tile_copies(1, man="2345678", pin="2346", sou="23"),
        ),
        draws=((0, tile(0, honors="5")), (1, tile(1, honors="5"))),
    )


def resync_before_deal() -> tuple[SeatTranscript, ...]:
    """
    Alice (seat 1) loses step with the server's messages while the game start shows over the deal, before the dealer's
    first draw, and asks for her seat's state again: the snapshot of the dealt round says she still owes the start's
    confirmation, with the time its timer has run and its whole timeout.

    She never confirms it, so the server's game start confirmation timeout confirms for her, and the AI dealer draws.
    """
    with seated_game("seat-resync-before-deal", _kyuushu_wall(), players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.label("game started", WireEventType.GAME_STARTED)
        alice.label("dealt", WireEventType.ROUND_STARTED)
        alice.resync(at=1, label="resync asked")
        alice.label("start snapshot", SessionMessageType.GAME_RECONNECTED)
        game.wait_until(SCENARIO_START_CONFIRM_SECONDS + 1)
        alice.label("first draw", WireEventType.DRAW)

        return game.transcripts("resync_before_deal", PLAYER)


def resync() -> tuple[SeatTranscript, ...]:
    """
    Alice (seat 1) loses step with the server's messages twice and each time asks for her seat's state again on the same
    socket, which stays bound to her seat.

    At her first draw the answer is the snapshot, then the draw re-sent with the time its timer has run, and she
    declares kyuushu kyuuhai on it. During the round advance the snapshot says she still owes her confirmation, with the
    time its timer has run and its whole timeout; she presses OK a second after it, and the dealer deals again.
    """
    with seated_game("seat-resync", _kyuushu_wall(), players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        alice.label("joined", SessionMessageType.GAME_JOINED)
        alice.label("game started", WireEventType.GAME_STARTED)
        game.wait_until(4)
        alice.label("dealt", WireEventType.ROUND_STARTED)
        alice.label("first draw", WireEventType.DRAW)
        alice.resync(at=4, label="turn resync asked")
        alice.label("turn snapshot", SessionMessageType.GAME_RECONNECTED)
        alice.label("draw re-sent", WireEventType.DRAW)
        alice.kyuushu(at=5, label="kyuushu chosen")
        alice.label("round end", WireEventType.ROUND_END)
        alice.resync(at=6.5, label="advance resync asked")
        alice.label("advance snapshot", SessionMessageType.GAME_RECONNECTED)
        alice.confirm_round(at=7.5, label="confirmed")
        alice.label("next round", WireEventType.ROUND_STARTED)

        return game.transcripts("resync", PLAYER)


def game_end_reconnect() -> tuple[SeatTranscript, ...]:
    """
    Alice (seat 1) declares kyuushu kyuuhai on her first draw: an abortive draw that moves no points, so the dealer
    deals again with a honba.

    In that deal, which the seed deals, her socket dies unseen and her reconnect's snapshot lists the first round in its
    history. She plays no move after it: the server's timeouts play her seat, and the AI players discard what they draw.
    The game is East only with no extension, so it ends with East 4.
    """
    settings = GameSettings(game_type=GameType.TONPUSEN, enchousen=EnchousenType.NONE)
    with seated_game("seat-game-end-reconnect", _kyuushu_wall(), players=(PLAYER,), settings=settings) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.label("first draw", WireEventType.DRAW)
        alice.kyuushu(at=5, label="kyuushu chosen")
        alice.label("kyuushu round end", WireEventType.ROUND_END)
        alice.confirm_round(at=6, label="confirmed")
        alice.label("second deal", WireEventType.ROUND_STARTED)
        alice.drop_unseen(at=7.5, label="dropped")
        alice.reconnect(at=8.5, label="reopened")
        alice.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        game.wait_until(6000)
        alice.label("last round end", WireEventType.ROUND_END)
        alice.label("game end", WireEventType.GAME_END)

        return game.transcripts("game_end_reconnect", PLAYER)


def seat_left() -> tuple[SeatTranscript, ...]:
    """
    Bob (seat 3) loses his connection during Alice's (seat 1) first turn, and the server notices: Alice is told an AI
    player stands in for him at his seat. Alice then loses her own connection unseen, and her reconnect's snapshot marks
    his seat as held for him. Bob reconnects, which Alice is told, and his snapshot marks the AI players' seats, his own
    no longer among them; Alice discards her draw.

    No hand can call another's discard (no hand holds two copies of a tile type, and no two of Alice's tiles make a chi
    shape), so nothing prompts either of them.
    """
    alice_draw = tile(0, honors="6")
    staged = StagedWall(
        hands=(
            tile_copies(2, man="258", pin="258", sou="258", honors="1234"),
            tile_copies(0, man="147", pin="147", sou="147", honors="1234"),
            tile_copies(3, man="369", pin="369", sou="369", honors="1234"),
            tile_copies(1, man="258", pin="369", sou="147", honors="1234"),
        ),
        draws=((0, tile(0, honors="5")), (1, alice_draw)),
    )

    with seated_game("seat-left", staged, players=(PLAYER, ROBBER)) as game:
        alice = game.clients[PLAYER]
        bob = game.clients[ROBBER]
        alice.join(at=0)
        bob.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        bob.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(4)
        alice.label("first draw", WireEventType.DRAW)
        bob.drop_seen(at=4.5, label="dropped")
        alice.label("player left", SessionMessageType.SEAT_CONTROL)
        alice.drop_unseen(at=4.5, label="dropped")
        alice.reconnect(at=5.5, label="reopened")
        alice.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        bob.reconnect(at=5.5, label="reopened")
        bob.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        alice.label("player back", SessionMessageType.SEAT_CONTROL)
        alice.discard(alice_draw, at=5.75, label="discarded")

        return game.transcripts("seat_left", PLAYER, ROBBER)


def first_turn_win() -> tuple[SeatTranscript, ...]:
    """
    Two first-turn wins.

    In East 1 the AI dealer, Alice (seat 1) and the AI at seat 2 each discard a wind nobody else holds, and Bob (seat
    3), dealt a hand waiting on the east wind, draws it: chiihou over their three discards. Both confirm, and in East 2
    Alice, now dealer, is dealt a complete hand with her first draw: tenhou over empty rivers.

    No one can call a discard (nobody holds a second copy of a discarded wind), and tobi is off, so the tenhou the AI
    dealer of East 1 pays leaves the game going. Both confirm two seconds after the chiihou, once its call has gone, as
    it has before a player can see the result.
    """
    east_wind = tile(1, honors="1")
    east_1 = StagedWall(
        hands=(
            tile_copies(1, man="123456789", pin="1234"),
            tile_copies(0, pin="456789", sou="13579", honors="56"),
            tile_copies(2, man="123456789", pin="1234"),
            tile_copies(0, man="123456789", pin="123", honors="1"),
        ),
        draws=((0, tile(0, honors="2")), (1, tile(0, honors="3")), (2, tile(0, honors="4")), (3, east_wind)),
    )
    east_2 = StagedWall(
        hands=(
            tile_copies(3, man="123456789", sou="1234"),
            (*tile_copies(0, man="123456789", pin="123"), tile(1, pin="1")),
            tile_copies(1, man="123456789", sou="1234"),
            tile_copies(2, man="123456789", sou="1234"),
        ),
        draws=((1, tile(0, pin="4")),),
        dealer=1,
    )

    settings = GameSettings(tobi_enabled=False)
    with seated_game(
        "seat-first-turn-win", east_1, players=(PLAYER, ROBBER), settings=settings, later_rounds=(east_2,)
    ) as game:
        alice = game.clients[PLAYER]
        bob = game.clients[ROBBER]
        alice.join(at=0)
        bob.join(at=0)
        alice.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        bob.confirm_round(at=START_CONFIRMED_AT, label="start confirmed")
        game.wait_until(3.5)
        alice.label("first draw", WireEventType.DRAW)
        alice.discard(tile(0, honors="3"), at=4, label="discarded")
        bob.label("chiihou draw", WireEventType.DRAW)
        bob.tsumo(at=5, label="tsumo chosen")
        bob.label("round end", WireEventType.ROUND_END)
        alice.label("chiihou round end", WireEventType.ROUND_END)
        alice.confirm_round(at=7, label="confirmed")
        bob.confirm_round(at=7, label="confirmed")
        alice.label("tenhou deal", WireEventType.ROUND_STARTED)
        alice.label("tenhou draw", WireEventType.DRAW)
        alice.tsumo(at=8, label="tsumo chosen")
        alice.label("round end", WireEventType.ROUND_END)

        return game.transcripts("first_turn_win", PLAYER, ROBBER)


ANCHOR_BOB = "Bob"
ANCHOR_CHARLIE = "Charlie"
ANCHOR_SEVEN_SOU = tile(0, sou="7")


def _anchor_east_1() -> StagedWall:
    """
    Deal East 1 to its AI dealer (seat 0) so that it ends at once: everyone discards an honor they cannot call, and Bob
    (seat 3), ready with tanyao and pinfu on 5s or 8s, rons the dealer's next draw, the 5s, which passes the deal to
    Alice (seat 1).
    """
    return StagedWall(
        hands=(
            tile_copies(0, man="123456789", pin="1234"),
            tile_copies(1, man="13579", pin="24689", sou="129"),
            tile_copies(2, man="2468", pin="13579", sou="3469"),
            (*tile_copies(3, man="234567", pin="2345", sou="67"), tile(2, pin="2")),
        ),
        draws=(
            (0, tile(0, honors="4")),
            (1, tile(0, honors="3")),
            (2, tile(0, honors="2")),
            (3, tile(0, honors="6")),
            (0, tile(1, sou="5")),
        ),
    )


def _anchor_east_2() -> StagedWall:
    """
    Deal East 2 from Alice (seat 1): a closed hand one tile from ready with a pair of 5s, while Charlie (seat 2) holds a
    pair of chun and Bob (seat 3) waits for 9p to be ready on 5p or 8p. Every draw nobody keeps is a tile no human seat
    can call or win on when it is discarded: no one else holds a pair of it, the seat after the discarder holds no shape
    around it, and it is not Bob's wait once he is ready.

    Alice keeps 7m, 5s and, in her tenth turn, 6p; Charlie pons her chun and keeps 2p; Bob keeps 6p and 9p, declaring
    riichi on his fifth turn; the AI player (seat 0) discards what it draws. Charlie's tenth draw is the third 5s, and
    Alice's eleventh the 7s that readies her hand two ways.
    """
    alice = (*tile_copies(0, man="23469", pin="134", sou="58", honors="4"), *tile_copies(1, man="5", pin="5"))
    charlie = (*tile_copies(2, man="136", pin="458", sou="679"), *tile_copies(0, honors="257"), tile(1, honors="7"))
    bob = (*tile_copies(1, man="123789", pin="7", sou="1234"), *tile_copies(0, pin="9", honors="1"))
    ai = tile_copies(3, man="1234567", pin="23567", sou="8")
    rounds = (
        (tile(0, honors="3"), tile(2, pin="2"), tile(0, honors="6"), tile(2, man="9")),
        (tile(2, honors="7"), None, tile(1, pin="6"), tile(2, sou="1")),
        (tile(0, man="7"), tile(1, honors="3"), tile(1, sou="9"), tile(2, honors="5")),
        (tile(1, sou="5"), tile(3, pin="9"), tile(1, pin="2"), tile(0, sou="4")),
        (tile(0, sou="1"), tile(1, honors="1"), tile(2, pin="9"), tile(2, honors="3")),
        (tile(1, honors="6"), tile(2, pin="3"), tile(1, man="4"), tile(0, sou="9")),
        (tile(1, pin="9"), tile(3, sou="9"), tile(1, honors="4"), tile(2, sou="2")),
        (tile(0, sou="2"), tile(3, pin="4"), tile(2, sou="3"), tile(3, honors="7")),
        (tile(1, honors="2"), tile(1, honors="5"), tile(1, man="6"), tile(0, sou="6")),
        (tile(0, pin="6"), tile(2, sou="5"), tile(1, pin="1"), tile(0, sou="3")),
        (ANCHOR_SEVEN_SOU,),
    )
    draws = tuple(
        (seat, drawn) for turns in rounds for seat, drawn in zip((1, 2, 3, 0), turns, strict=False) if drawn is not None
    )
    return StagedWall(hands=(ai, alice, charlie, bob), draws=draws, dealer=1)


def anchor() -> tuple[SeatTranscript, ...]:
    """
    The look spec's anchor, East 2 at turn 10, as Alice (seat 1), its dealer, sees it: three players and an AI player.

    East 1 ends at once with Bob's ron on the AI dealer (`_anchor_east_1`), and everyone confirms it. In East 2
    (`_anchor_east_2`) everyone discards about a tile every half second: Charlie (seat 2) pons Alice's chun, Bob (seat
    3) declares riichi on his fifth turn, and by Alice's tenth draw every seat has nine discards. Three checkpoints
    follow: that draw, her plain turn; Charlie's 5s, which she may pon and passes; and her eleventh draw, which offers
    riichi on either of two discards.
    """
    with seated_game(
        "seat-anchor",
        _anchor_east_1(),
        players=(PLAYER, ANCHOR_BOB, ANCHOR_CHARLIE),
        later_rounds=(_anchor_east_2(),),
    ) as game:
        alice = game.clients[PLAYER]
        bob = game.clients[ANCHOR_BOB]
        charlie = game.clients[ANCHOR_CHARLIE]
        for client in (alice, bob, charlie):
            client.join(at=0)

        for client in (alice, bob, charlie):
            client.confirm_round(at=START_CONFIRMED_AT)

        alice.discard(tile(0, honors="3"), at=3.5)
        charlie.discard(tile(0, honors="2"), at=4)
        bob.discard(tile(0, honors="6"), at=4.5)
        bob.ron(at=5)
        alice.confirm_round(at=5.5)
        bob.confirm_round(at=5.5)
        charlie.confirm_round(at=6)
        alice.label("east 2 dealt", WireEventType.ROUND_STARTED)

        moves: tuple[tuple[Callable[..., None], int], ...] = (
            (alice.discard, tile(0, honors="4")),
            (charlie.discard, tile(0, honors="2")),
            (bob.discard, tile(0, honors="1")),
            (alice.discard, tile(2, honors="7")),
            (charlie.pon, tile(2, honors="7")),
            (charlie.discard, tile(0, honors="5")),
            (bob.discard, tile(1, sou="1")),
            (alice.discard, tile(0, pin="1")),
            (charlie.discard, tile(1, honors="3")),
            (bob.discard, tile(1, sou="9")),
            (alice.discard, tile(0, honors="3")),
            (charlie.discard, tile(3, pin="9")),
            (bob.discard, tile(1, pin="2")),
            (alice.discard, tile(0, sou="1")),
            (charlie.discard, tile(1, honors="1")),
            (bob.riichi, tile(0, honors="6")),
            (alice.discard, tile(1, honors="6")),
            (charlie.discard, tile(2, pin="3")),
            (bob.discard, tile(1, man="4")),
            (alice.discard, tile(1, pin="9")),
            (charlie.discard, tile(3, sou="9")),
            (bob.discard, tile(1, honors="4")),
            (alice.discard, tile(0, sou="2")),
            (charlie.discard, tile(3, pin="4")),
            (bob.discard, tile(2, sou="3")),
            (alice.discard, tile(1, honors="2")),
            (charlie.discard, tile(1, honors="5")),
            (bob.discard, tile(1, man="6")),
        )
        at = 6.5
        for move, tile_id in moves:
            move(tile_id, at=at)
            at += 0.5

        alice.label("own turn", WireEventType.DRAW)
        alice.discard(tile(0, man="9"), at=at, label="discarded")
        charlie.discard(tile(2, sou="5"), at=at + 0.5)
        alice.label("call offer", WireEventType.CALL_PROMPT)
        alice.pass_(at=at + 1.5, label="passed")
        bob.discard(tile(1, pin="1"), at=at + 2)
        alice.label("riichi offer", WireEventType.DRAW)

        return game.transcripts("anchor", PLAYER)


SCENARIOS: dict[str, Callable[[], tuple[SeatTranscript, ...]]] = {
    "call_prompt": call_prompt,
    "kan_choice": kan_choice,
    "own_turn": own_turn,
    "riichi_kan": riichi_kan,
    "bank_reconnect": bank_reconnect,
    "reconnect": reconnect,
    "riichi_reconnect": riichi_reconnect,
    "chankan_robbed": chankan_robbed,
    "chankan_passed": chankan_passed,
    "double_ron": double_ron,
    "final_round": final_round,
    "game_end_reconnect": game_end_reconnect,
    "resync_before_deal": resync_before_deal,
    "resync": resync,
    "seat_left": seat_left,
    "first_turn_win": first_turn_win,
    "anchor": anchor,
}
