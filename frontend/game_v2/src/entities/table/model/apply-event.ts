import { assertNever } from "@/shared/lib";
import {
    type DiscardEvent,
    type DoraRevealedEvent,
    type DrawEvent,
    type GameEndEvent,
    type GameStartedEvent,
    type PlayerLeftMessage,
    type PlayerReconnectedMessage,
    type RiichiDeclaredEvent,
    type RoundStartedEvent,
    SEAT_CONTROL_REASON,
    type SeatControlLine,
} from "@/shared/protocol";

import { applyKanDeclared } from "./handlers/kan-declared";
import { applyMeld } from "./handlers/meld";
import { applyGameReconnected } from "./handlers/reconnect";
import { applyRoundEnd } from "./handlers/round-end";
import { drewUnseen, requirePlayer, takeFromHand, updatePlayer } from "./helpers";
import { createInitialPlayerState } from "./initial-state";
import { type PlayerState, type TableEvent, type TableState } from "./types";

/** Live wall size after dealing: 136 total - 14 dead wall - 52 dealt (13 × 4 players). */
const TILES_AFTER_DEAL = 136 - 14 - 13 * 4;
const DEALT_HAND_SIZE = 13;
/**
 * What an accepted riichi takes from its declarer onto the table: the server's `riichi_cost`, which no live message
 * carries, at its default, the one every game is played with.
 */
export const RIICHI_DEPOSIT = 1000;

function applyGameStarted(state: TableState, event: GameStartedEvent): TableState {
    const players = event.players.map((p) =>
        createInitialPlayerState({
            isAiPlayer: p.isAiPlayer,
            name: p.name,
            score: 0,
            seat: p.seat,
        }),
    );
    return {
        ...state,
        dealerSeat: event.dealerSeat,
        firstDealerSeat: event.dealerSeat,
        gameEndResult: null,
        gameId: event.gameId,
        phase: "pre_game",
        players,
        roundEndResult: null,
        roundHistory: [],
    };
}

/**
 * The hand a deal gives a seat: every hand when the event shows them all (a replay), the viewer's own from its
 * private tiles (a live seat), and otherwise a count of face-down tiles.
 */
function dealtHand(
    event: RoundStartedEvent,
    seat: number,
): Pick<PlayerState, "tiles" | "concealedCount"> {
    const shown = event.players.find((view) => view.seat === seat)?.tiles ?? null;
    if (shown !== null) {
        return { concealedCount: 0, tiles: shown };
    }
    if (event.seat === seat && event.myTiles !== null) {
        return { concealedCount: 0, tiles: event.myTiles };
    }
    return { concealedCount: DEALT_HAND_SIZE, tiles: [] };
}

function applyRoundStarted(state: TableState, event: RoundStartedEvent): TableState {
    const players = state.players.map((p) => ({
        ...p,
        ...dealtHand(event, p.seat),
        discards: [],
        drawnTileId: null,
        isRiichi: false,
        melds: [],
        score: event.players.find((view) => view.seat === p.seat)?.score ?? p.score,
    }));
    return {
        ...state,
        currentPlayerSeat: event.currentPlayerSeat,
        dealerSeat: event.dealerSeat,
        doraIndicators: event.doraIndicators,
        honbaSticks: event.honbaSticks,
        lastDiscardSeat: null,
        phase: "in_round",
        players,
        riichiSticks: event.riichiSticks,
        roundEndResult: null,
        roundWind: event.wind,
        tilesRemaining: TILES_AFTER_DEAL,
    };
}

/**
 * A draw puts its tile in the hand. The draw a reconnect re-sends names a tile the snapshot's hand already holds:
 * it only marks the drawn tile again, taking nothing from the wall.
 */
function applyDraw(state: TableState, event: DrawEvent): TableState {
    const player = requirePlayer(state, event.seat);
    const resent = player.tiles.includes(event.tileId);
    return {
        ...state,
        currentPlayerSeat: event.seat,
        players: updatePlayer(state.players, event.seat, {
            drawnTileId: event.tileId,
            tiles: resent ? player.tiles : [...player.tiles, event.tileId],
        }),
        tilesRemaining: resent ? state.tilesRemaining : state.tilesRemaining - 1,
    };
}

/** A discard leaves the hand; a hidden hand that discards without a draw this view saw drew one unseen first. */
function applyDiscard(state: TableState, event: DiscardEvent): TableState {
    const player = requirePlayer(state, event.seat);
    const unseen = drewUnseen(player) ? 1 : 0;
    const hand = takeFromHand(
        { concealedCount: player.concealedCount + unseen, tiles: player.tiles },
        [event.tileId],
    );
    if (hand === null) {
        throw new Error(`Discarded tile ${event.tileId} not found in hand of seat ${event.seat}`);
    }
    return {
        ...state,
        currentPlayerSeat: event.seat,
        lastDiscardSeat: event.seat,
        players: updatePlayer(state.players, event.seat, {
            concealedCount: hand.concealedCount,
            discards: [
                ...player.discards,
                {
                    isRiichi: event.isRiichi,
                    isTsumogiri: event.isTsumogiri,
                    tileId: event.tileId,
                },
            ],
            drawnTileId: null,
            tiles: hand.tiles.toSorted((tileA, tileB) => (tileA >> 2) - (tileB >> 2)),
        }),
        tilesRemaining: state.tilesRemaining - unseen,
    };
}

/**
 * The server declares riichi once the declaration's discard passes without a ron, and only then takes the stick: the
 * declarer's score pays it onto the table. A ronned declaration discard never reaches here, so it deposits nothing.
 */
function applyRiichiDeclared(state: TableState, event: RiichiDeclaredEvent): TableState {
    const player = requirePlayer(state, event.seat);
    return {
        ...state,
        players: updatePlayer(state.players, event.seat, {
            isRiichi: true,
            score: player.score - RIICHI_DEPOSIT,
        }),
        riichiSticks: state.riichiSticks + 1,
    };
}

function applyDoraRevealed(state: TableState, event: DoraRevealedEvent): TableState {
    return {
        ...state,
        doraIndicators: [...state.doraIndicators, event.tileId],
    };
}

function applyGameEnd(state: TableState, event: GameEndEvent): TableState {
    const players = state.players.map((p) => {
        const standing = event.standings.find((s) => s.seat === p.seat);
        return standing ? { ...p, score: standing.score } : p;
    });
    return {
        ...state,
        gameEndResult: {
            leftoverRiichiBonus: event.leftoverRiichiBonus,
            standings: event.standings.map((s) => ({
                finalScore: s.finalScore,
                score: s.score,
                seat: s.seat,
            })),
            winnerSeat: event.winnerSeat,
        },
        phase: "game_ended",
        players,
        riichiSticks: 0,
    };
}

/** A replay's seat control line: an AI player takes the seat for its human, or the human takes it back. */
function applySeatControl(state: TableState, line: SeatControlLine): TableState {
    const aiStandIn = line.type === "ai_replacement" ? line.reason : null;
    return { ...state, players: updatePlayer(state.players, line.seat, { aiStandIn }) };
}

/**
 * The live socket's word that a seat's human left (an AI player takes the seat while the game plays) or came back.
 * A return puts the human in control, whatever AI flag a reconnect's snapshot gave the seat while they were away.
 * It names the player, not the seat; a name the table does not hold changes nothing.
 */
function applyPlayerPresence(
    state: TableState,
    message: PlayerLeftMessage | PlayerReconnectedMessage,
): TableState {
    const player = state.players.find((p) => p.name === message.playerName);
    if (player === undefined) {
        return state;
    }
    const update =
        message.type === "player_left"
            ? { aiStandIn: SEAT_CONTROL_REASON.LEFT }
            : { aiStandIn: null, isAiPlayer: false };
    return { ...state, players: updatePlayer(state.players, player.seat, update) };
}

/**
 * The table transition: the next table after one event, never changing the one it was given. The draw, discard,
 * meld and kan declaration handlers throw on an impossible state (a missing tile, player or caller).
 */
export function applyEvent(state: TableState, event: TableEvent): TableState {
    switch (event.type) {
        case "game_started": {
            return applyGameStarted(state, event);
        }
        case "round_started": {
            return applyRoundStarted(state, event);
        }
        case "draw": {
            return applyDraw(state, event);
        }
        case "discard": {
            return applyDiscard(state, event);
        }
        case "meld": {
            return applyMeld(state, event);
        }
        case "kan_declared": {
            return applyKanDeclared(state, event);
        }
        case "riichi_declared": {
            return applyRiichiDeclared(state, event);
        }
        case "dora_revealed": {
            return applyDoraRevealed(state, event);
        }
        case "game_end": {
            return applyGameEnd(state, event);
        }
        case "round_end": {
            return applyRoundEnd(state, event);
        }
        case "game_reconnected": {
            return applyGameReconnected(state, event);
        }
        case "ai_replacement":
        case "human_return": {
            return applySeatControl(state, event);
        }
        case "player_left":
        case "player_reconnected": {
            return applyPlayerPresence(state, event);
        }
        default: {
            return assertNever(event);
        }
    }
}
