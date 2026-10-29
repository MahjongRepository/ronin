from __future__ import annotations

from typing import TYPE_CHECKING

from game.logic.enums import KanType
from game.logic.settings import GameSettings
from game.messaging.types import SessionMessageType
from game.tests.helpers.hands import tile_copies
from game.wire.enums import WireEventType
from scripts.replay_fixtures.staged_game import StagedWall, tile
from scripts.seat_scenarios.harness import seated_game

if TYPE_CHECKING:
    from collections.abc import Callable

    from scripts.seat_scenarios.harness import SeatTranscript

PLAYER = "Alice"
ROBBER = "Bob"
OWN_TURN_RINSHAN = tile(0, honors="4")


def call_prompt() -> tuple[SeatTranscript, ...]:
    """
    Offer Alice, the one human at the table (seat 1), a pon, an open kan and a chi two ways on the dealer's 3m; she
    calls chi, and her turn after it opens with the tile types kuikae forbids.

    She passes a pon of 7s from seat 2, and her next draw opens her next turn with what is left of her bank.
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
        game.wait_until(4)
        alice.label("dealt", WireEventType.ROUND_STARTED)
        alice.label("prompt", WireEventType.CALL_PROMPT)
        alice.chi(called_tile, (tile(0, man="1"), tile(0, man="2")), at=5, label="chi chosen")
        alice.label("turn", WireEventType.TURN)
        alice.discard(tile(0, honors="3"), at=12, label="discarded")
        alice.label("pon prompt", WireEventType.CALL_PROMPT)
        alice.pass_(at=14, label="passed")
        alice.label("next turn", WireEventType.DRAW)

        return game.transcripts("call_prompt", PLAYER)


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
    Deal Alice (seat 1) three 1m and draw her the fourth, which offers a closed kan and riichi.

    Her socket dies unseen during the turn, and her reconnect takes it over: the snapshot, then the draw re-sent with
    the time its timer has run. She declares the kan and riichi on its rinshan draw.

    She passes a ron on seat 2's 6s, which leaves her furiten, wins by tsumo on her next draw, and presses OK on the
    round end a second after it, after which she deals the next round from the seed.
    """
    with seated_game("seat-own-turn", _own_turn_wall(), players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
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
        alice.be_replaced_by_another_tab(at=10.5)

        return game.transcripts("reconnect", PLAYER)


def riichi_reconnect() -> tuple[SeatTranscript, ...]:
    """
    Declare riichi for Alice (seat 1) on her first draw, discarding a 1m; it passes, so the server takes her stick.

    Her socket dies unseen at seat 2's 6s, and her reconnect takes it over: the snapshot, with her stick already taken,
    then the ron prompt re-sent. She rons it and never confirms the round end, so the server's round advance timeout
    deals the next round while her result is still open.
    """
    with seated_game("seat-riichi-reconnect", _own_turn_wall(), players=(PLAYER,)) as game:
        alice = game.clients[PLAYER]
        alice.join(at=0)
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
        game.wait_until(4)
        alice.label("ron prompt", WireEventType.CALL_PROMPT)
        alice.ron(at=5, label="ron chosen")
        alice.label("round end", WireEventType.ROUND_END)
        alice.label("game end", WireEventType.GAME_END)
        game.wait_until(6)

        return game.transcripts("final_round", PLAYER)


def seat_left() -> tuple[SeatTranscript, ...]:
    """
    Bob (seat 3) loses his connection during Alice's (seat 1) first turn, and the server notices: Alice is told he left,
    and an AI player plays his seat. Alice then loses her own connection unseen, and her reconnect's snapshot marks his
    seat as an AI player's. Bob reconnects, which Alice is told, and his snapshot marks the AI players' seats, his own
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
        game.wait_until(4)
        alice.label("first draw", WireEventType.DRAW)
        bob.drop_seen(at=4.5, label="dropped")
        alice.label("player left", SessionMessageType.PLAYER_LEFT)
        alice.drop_unseen(at=4.5, label="dropped")
        alice.reconnect(at=5.5, label="reopened")
        alice.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        bob.reconnect(at=5.5, label="reopened")
        bob.label("reconnected", SessionMessageType.GAME_RECONNECTED)
        alice.label("player back", SessionMessageType.PLAYER_RECONNECTED)
        alice.discard(alice_draw, at=5.75, label="discarded")

        return game.transcripts("seat_left", PLAYER, ROBBER)


SCENARIOS: dict[str, Callable[[], tuple[SeatTranscript, ...]]] = {
    "call_prompt": call_prompt,
    "own_turn": own_turn,
    "reconnect": reconnect,
    "riichi_reconnect": riichi_reconnect,
    "chankan_robbed": chankan_robbed,
    "chankan_passed": chankan_passed,
    "double_ron": double_ron,
    "final_round": final_round,
    "seat_left": seat_left,
}
