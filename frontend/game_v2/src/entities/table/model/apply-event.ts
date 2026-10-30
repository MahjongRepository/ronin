import { assertNever } from "@/shared/lib";
import {
    type DiscardEvent,
    type DoraRevealedEvent,
    type DrawEvent,
    type DrawNoticeEvent,
    type GameEndEvent,
    type GameStartedEvent,
    type RiichiDeclaredEvent,
    type RoundStartedEvent,
    type SeatControlLine,
} from "@/shared/protocol";

import { DesyncError } from "./desync-error";
import { applyKanDeclared } from "./handlers/kan-declared";
import { applyMeld } from "./handlers/meld";
import { applyGameReconnected } from "./handlers/reconnect";
import { applyRoundEnd } from "./handlers/round-end";
import { requirePlayer, requireRiichiCost, takeFromHand, updatePlayer } from "./helpers";
import { createInitialPlayerState } from "./initial-state";
import { type GamePhase, type PlayerState, type TableEvent, type TableState } from "./types";

/** Live wall size after dealing: 136 total - 14 dead wall - 52 dealt (13 × 4 players). */
const TILES_AFTER_DEAL = 136 - 14 - 13 * 4;
const DEALT_HAND_SIZE = 13;
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
        gameId: event.gameId,
        gameType: event.gameType,
        phase: "pre_game",
        players,
        riichiCost: event.riichiCost,
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
        drawnConcealed: false,
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
        revealedSeats: [],
        riichiSticks: event.riichiSticks,
        roundEndResult: null,
        roundNumber: event.roundNumber,
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

/** Another seat's draw, its tile private to that seat: a face-down tile joins its hand, from the wall, in its turn. */
function applyDrawNotice(state: TableState, event: DrawNoticeEvent): TableState {
    const player = requirePlayer(state, event.seat);
    return {
        ...state,
        currentPlayerSeat: event.seat,
        players: updatePlayer(state.players, event.seat, {
            concealedCount: player.concealedCount + 1,
            drawnConcealed: true,
        }),
        tilesRemaining: state.tilesRemaining - 1,
    };
}

function applyDiscard(state: TableState, event: DiscardEvent): TableState {
    const player = requirePlayer(state, event.seat);
    const hand = takeFromHand(player, [event.tileId]);
    if (hand === null) {
        throw new DesyncError(
            `Discarded tile ${event.tileId} not found in hand of seat ${event.seat}`,
        );
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
            drawnConcealed: false,
            drawnTileId: null,
            tiles: hand.tiles.toSorted((tileA, tileB) => (tileA >> 2) - (tileB >> 2)),
        }),
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
            score: player.score - requireRiichiCost(state),
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
            endCause: event.endCause,
            leftoverRiichiBonus: event.leftoverRiichiBonus,
            leftoverSticks: event.leftoverRiichiSticks,
            numRounds: event.numRounds,
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

/**
 * A seat control line, a replay's or the live session's: an AI player takes the seat for its human, or the human takes
 * it back.
 */
function applySeatControl(state: TableState, line: SeatControlLine): TableState {
    const aiStandIn = line.type === "ai_replacement" ? line.reason : null;
    return { ...state, players: updatePlayer(state.players, line.seat, { aiStandIn }) };
}

/**
 * Where the table stands for the order of events: `unseated` before any game start, `out_of_step` from a live
 * client's loss of step until a snapshot, else the table's phase.
 */
type OrderPhase = GamePhase | "unseated" | "out_of_step";

const ANY_PHASE: readonly OrderPhase[] = [
    "unseated",
    "pre_game",
    "in_round",
    "round_ended",
    "game_ended",
    "out_of_step",
];
const IN_ROUND: readonly OrderPhase[] = ["in_round"];

/**
 * The phases that take each event; any other is an impossible server sequence. The snapshot rebuilds the table
 * whatever it held, and a seat control line or a loss of step changes no order. Out of step, the table missed the
 * messages that would have moved its phase, so it takes the game's last round end and the game's end on any table.
 */
const PHASES_TAKING: Readonly<Record<TableEvent["type"], readonly OrderPhase[]>> = {
    ai_replacement: ANY_PHASE,
    discard: IN_ROUND,
    dora_revealed: IN_ROUND,
    draw: IN_ROUND,
    draw_notice: IN_ROUND,
    game_end: ["round_ended", "out_of_step"],
    game_reconnected: ANY_PHASE,
    game_started: ["unseated"],
    human_return: ANY_PHASE,
    kan_declared: IN_ROUND,
    lost_step: ANY_PHASE,
    meld: IN_ROUND,
    riichi_declared: IN_ROUND,
    round_end: ["in_round", "out_of_step"],
    round_started: ["pre_game", "round_ended"],
};

function orderPhase(state: TableState): OrderPhase {
    if (!state.roundHistoryInStep) {
        return "out_of_step";
    }
    return state.phase === "pre_game" && state.players.length === 0 ? "unseated" : state.phase;
}

/**
 * The table transition: the next table after one event, never changing the one it was given. An event outside the
 * phases that take it (`PHASES_TAKING`) throws a `DesyncError`, as do the draw, discard, meld and kan declaration
 * handlers on an impossible state (a missing tile, player or caller).
 */
export function applyEvent(state: TableState, event: TableEvent): TableState {
    const phase = orderPhase(state);
    if (!PHASES_TAKING[event.type].includes(phase)) {
        throw new DesyncError(`A ${event.type} event reached a table in phase ${phase}`);
    }
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
        case "draw_notice": {
            return applyDrawNotice(state, event);
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
        case "lost_step": {
            return { ...state, roundEndResult: null, roundHistoryInStep: false };
        }
        default: {
            return assertNever(event);
        }
    }
}
