import { tile136toString } from "@/entities/tile";
import {
    type AbortiveDrawRoundEnd,
    type DiscardEvent,
    type DoraRevealedEvent,
    type DoubleRonRoundEnd,
    type DrawEvent,
    type GameEndEvent,
    type GameStartedEvent,
    type NagashiManganRoundEnd,
    ROUND_RESULT_TYPE,
    type RiichiDeclaredEvent,
    type RonRoundEnd,
    type RoundEndEvent,
    type RoundStartedEvent,
    type TsumoRoundEnd,
} from "@/shared/protocol";

import { applyMeld } from "./handlers/meld";
import { updatePlayer } from "./helpers";
import { createInitialPlayerState } from "./initial-state";
import {
    type GamePhase,
    type PlayerState,
    type ReplayEvent,
    type RoundEndResult,
    type TableState,
    type WinnerResult,
} from "./types";

function assertNever(value: never): never {
    throw new Error(`Unhandled replay event type: ${(value as { type: string }).type}`);
}

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
        gameEndResult: null,
        gameId: event.gameId,
        lastEventDescription: "Game started",
        phase: "pre_game" as GamePhase,
        players,
        roundEndResult: null,
    };
}

function applyRoundStarted(state: TableState, event: RoundStartedEvent): TableState {
    const players = state.players.map((p) => {
        const view = event.players.find((pv) => pv.seat === p.seat);
        return {
            ...p,
            discards: [],
            drawnTileId: null,
            isRiichi: false,
            melds: [],
            score: view?.score ?? p.score,
            tiles: view?.tiles ?? [],
        };
    });
    return {
        ...state,
        currentPlayerSeat: event.currentPlayerSeat,
        dealerSeat: event.dealerSeat,
        doraIndicators: [...event.doraIndicators],
        honbaSticks: event.honbaSticks,
        lastEventDescription: "Round started",
        phase: "in_round" as GamePhase,
        players,
        riichiSticks: event.riichiSticks,
        roundEndResult: null,
        roundNumber: event.roundNumber,
        roundWind: event.wind,
    };
}

function applyDraw(state: TableState, event: DrawEvent): TableState {
    const player = state.players.find((p) => p.seat === event.seat);
    if (!player) {
        throw new Error(`No player found for seat ${event.seat}`);
    }
    const tileName = tile136toString(event.tileId);
    return {
        ...state,
        currentPlayerSeat: event.seat,
        lastEventDescription: `${player.name} drew ${tileName}`,
        players: updatePlayer(state.players, event.seat, {
            drawnTileId: event.tileId,
            tiles: [...player.tiles, event.tileId],
        }),
    };
}

function applyDiscard(state: TableState, event: DiscardEvent): TableState {
    const player = state.players.find((p) => p.seat === event.seat);
    if (!player) {
        throw new Error(`No player found for seat ${event.seat}`);
    }
    const tileName = tile136toString(event.tileId);
    const updatedTiles = player.tiles.slice();
    const idx = updatedTiles.indexOf(event.tileId);
    if (idx !== -1) {
        updatedTiles.splice(idx, 1);
    }
    return {
        ...state,
        lastEventDescription: `${player.name} discarded ${tileName}`,
        players: updatePlayer(state.players, event.seat, {
            discards: [
                ...player.discards,
                {
                    isRiichi: event.isRiichi,
                    isTsumogiri: event.isTsumogiri,
                    tileId: event.tileId,
                },
            ],
            drawnTileId: null,
            tiles: updatedTiles,
        }),
    };
}

function applyRiichiDeclared(state: TableState, event: RiichiDeclaredEvent): TableState {
    const player = state.players.find((p) => p.seat === event.seat);
    return {
        ...state,
        lastEventDescription: `${player?.name ?? `Seat ${event.seat}`} declared riichi`,
        players: updatePlayer(state.players, event.seat, {
            isRiichi: true,
        }),
    };
}

function applyDoraRevealed(state: TableState, event: DoraRevealedEvent): TableState {
    const tileName = tile136toString(event.tileId);
    return {
        ...state,
        doraIndicators: [...state.doraIndicators, event.tileId],
        lastEventDescription: `New dora indicator: ${tileName}`,
    };
}

function applyGameEnd(state: TableState, event: GameEndEvent): TableState {
    const winner = state.players.find((p) => p.seat === event.winnerSeat);
    const players = state.players.map((p) => {
        const standing = event.standings.find((s) => s.seat === p.seat);
        return standing ? { ...p, score: standing.score } : p;
    });
    return {
        ...state,
        gameEndResult: {
            standings: event.standings.map((s) => ({
                finalScore: s.finalScore,
                score: s.score,
                seat: s.seat,
            })),
            winnerSeat: event.winnerSeat,
        },
        lastEventDescription: `Game over - Winner: ${winner?.name ?? `Seat ${event.winnerSeat}`}`,
        phase: "game_ended" as GamePhase,
        players,
        roundEndResult: null,
    };
}

function playerName(state: TableState, seat: number): string {
    return state.players.find((p) => p.seat === seat)?.name ?? `Seat ${seat}`;
}

function updateScoresFromMap(
    players: PlayerState[],
    scores: Record<string, number>,
): PlayerState[] {
    return players.map((p) => {
        const score = scores[String(p.seat)];
        return score !== undefined ? { ...p, score } : p;
    });
}

function tsumoDescription(state: TableState, event: RoundEndEvent): string {
    const re = event as TsumoRoundEnd;
    return `Tsumo by ${playerName(state, re.winnerSeat)}`;
}

function ronDescription(state: TableState, event: RoundEndEvent): string {
    const re = event as RonRoundEnd;
    return `Ron by ${playerName(state, re.winnerSeat)} from ${playerName(state, re.loserSeat)}`;
}

function doubleRonDescription(state: TableState, event: RoundEndEvent): string {
    const re = event as DoubleRonRoundEnd;
    const names = re.winners.map((w) => playerName(state, w.winnerSeat));
    return `Double ron by ${names.join(" and ")}`;
}

function nagashiDescription(state: TableState, event: RoundEndEvent): string {
    const re = event as NagashiManganRoundEnd;
    const names = re.qualifyingSeats.map((seat) => playerName(state, seat));
    return `Nagashi mangan by ${names.join(" and ")}`;
}

function roundEndDescription(state: TableState, event: RoundEndEvent): string {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO:
            return tsumoDescription(state, event);
        case ROUND_RESULT_TYPE.RON:
            return ronDescription(state, event);
        case ROUND_RESULT_TYPE.DOUBLE_RON:
            return doubleRonDescription(state, event);
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
            return "Exhaustive draw";
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW:
            return `Abortive draw: ${(event as AbortiveDrawRoundEnd).reason}`;
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN:
            return nagashiDescription(state, event);
        default: {
            const _exhaustive: never = event;
            return `Round ended (unknown result type: ${String(_exhaustive)})`;
        }
    }
}

function extractWinnerFromSingle(event: TsumoRoundEnd | RonRoundEnd): WinnerResult {
    return {
        closedTiles: event.closedTiles,
        handResult: event.handResult,
        melds: event.melds,
        seat: event.winnerSeat,
        winningTile: event.winningTile,
    };
}

function extractRoundEndResult(event: RoundEndEvent): RoundEndResult {
    switch (event.resultType) {
        case ROUND_RESULT_TYPE.TSUMO:
            return {
                resultType: event.resultType,
                scoreChanges: event.scoreChanges,
                winners: [extractWinnerFromSingle(event)],
            };
        case ROUND_RESULT_TYPE.RON:
            return {
                loserSeat: event.loserSeat,
                resultType: event.resultType,
                scoreChanges: event.scoreChanges,
                winners: [extractWinnerFromSingle(event)],
            };
        case ROUND_RESULT_TYPE.DOUBLE_RON:
            return {
                loserSeat: event.loserSeat,
                resultType: event.resultType,
                scoreChanges: event.scoreChanges,
                winners: event.winners.map((w) => ({
                    closedTiles: w.closedTiles,
                    handResult: w.handResult,
                    melds: w.melds,
                    seat: w.winnerSeat,
                    winningTile: event.winningTile,
                })),
            };
        case ROUND_RESULT_TYPE.EXHAUSTIVE_DRAW:
        case ROUND_RESULT_TYPE.ABORTIVE_DRAW:
        case ROUND_RESULT_TYPE.NAGASHI_MANGAN:
            return {
                resultType: event.resultType,
                scoreChanges: event.scoreChanges,
                winners: [],
            };
        default: {
            const _exhaustive: never = event;
            return _exhaustive;
        }
    }
}

function applyRoundEnd(state: TableState, event: RoundEndEvent): TableState {
    return {
        ...state,
        lastEventDescription: roundEndDescription(state, event),
        phase: "round_ended" as GamePhase,
        players: updateScoresFromMap(state.players, event.scores),
        roundEndResult: extractRoundEndResult(event),
    };
}

export function applyEvent(state: TableState, event: ReplayEvent): TableState {
    switch (event.type) {
        case "game_started":
            return applyGameStarted(state, event);
        case "round_started":
            return applyRoundStarted(state, event);
        case "draw":
            return applyDraw(state, event);
        case "discard":
            return applyDiscard(state, event);
        case "meld":
            return applyMeld(state, event);
        case "riichi_declared":
            return applyRiichiDeclared(state, event);
        case "dora_revealed":
            return applyDoraRevealed(state, event);
        case "game_end":
            return applyGameEnd(state, event);
        case "round_end":
            return applyRoundEnd(state, event);
        default:
            return assertNever(event);
    }
}
