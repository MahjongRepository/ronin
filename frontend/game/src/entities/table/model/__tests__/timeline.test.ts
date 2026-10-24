import { describe, expect, test } from "vitest";

import { buildTimeline } from "@/entities/table/model/timeline";
import { type ReplayEvent } from "@/entities/table/model/types";
import {
    type DiscardEvent,
    type DrawEvent,
    type GameEndEvent,
    type GameStartedEvent,
    ROUND_RESULT_TYPE,
    type RoundStartedEvent,
    type TsumoRoundEnd,
} from "@/shared/protocol";

function makeGameStartedEvent(): GameStartedEvent {
    return {
        dealerDice: [
            [2, 3],
            [4, 5],
        ],
        dealerSeat: 0,
        gameId: "timeline-test",
        players: [
            { isAiPlayer: false, name: "Alice", seat: 0 },
            { isAiPlayer: true, name: "Bot-1", seat: 1 },
            { isAiPlayer: true, name: "Bot-2", seat: 2 },
            { isAiPlayer: false, name: "Bob", seat: 3 },
        ],
        type: "game_started",
    };
}

function makeRoundStartedEvent(): RoundStartedEvent {
    return {
        currentPlayerSeat: 0,
        dealerSeat: 0,
        dice: [3, 4],
        doraIndicators: [10],
        honbaSticks: 0,
        myTiles: null,
        players: [
            { score: 25000, seat: 0, tiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] },
            { score: 25000, seat: 1, tiles: [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25] },
            { score: 25000, seat: 2, tiles: [26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38] },
            { score: 25000, seat: 3, tiles: [39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51] },
        ],
        riichiSticks: 0,
        roundNumber: 1,
        seat: null,
        type: "round_started",
        wind: 0,
    };
}

function makeDrawEvent(): DrawEvent {
    return {
        availableActions: [],
        seat: 0,
        tileId: 52,
        type: "draw",
    };
}

function makeDiscardEvent(): DiscardEvent {
    return {
        isRiichi: false,
        isTsumogiri: false,
        seat: 0,
        tileId: 0,
        type: "discard",
    };
}

function makeRoundEndEvent(): TsumoRoundEnd {
    return {
        closedTiles: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 52],
        handResult: { fu: 30, han: 4, yaku: [{ han: 1, yakuId: 0 }] },
        melds: [],
        paoSeat: null,
        resultType: ROUND_RESULT_TYPE.TSUMO,
        riichiSticksCollected: 0,
        scoreChanges: { "0": 12000, "1": -4000, "2": -4000, "3": -4000 },
        scores: { "0": 37000, "1": 21000, "2": 21000, "3": 21000 },
        type: "round_end",
        uraDoraIndicators: null,
        winnerSeat: 0,
        winningTile: 52,
    };
}

function makeGameEndEvent(): GameEndEvent {
    return {
        numRounds: 1,
        standings: [
            { finalScore: 47.0, score: 37000, seat: 0 },
            { finalScore: -9.0, score: 21000, seat: 1 },
            { finalScore: -9.0, score: 21000, seat: 2 },
            { finalScore: -29.0, score: 21000, seat: 3 },
        ],
        type: "game_end",
        winnerSeat: 0,
    };
}

describe("buildTimeline", () => {
    describe("basic timeline structure", () => {
        test("empty events produces a single initial state", () => {
            const states = buildTimeline([]);

            expect(states).toHaveLength(1);
            expect(states[0].phase).toBe("pre_game");
            expect(states[0].players).toHaveLength(0);
            expect(states[0].gameId).toBe("");
        });

        test("returns events.length + 1 states for any event sequence", () => {
            const events: ReplayEvent[] = [makeGameStartedEvent(), makeRoundStartedEvent()];
            const states = buildTimeline(events);

            expect(states).toHaveLength(3);
        });

        test("state at index 0 is always the initial state before any events", () => {
            const events: ReplayEvent[] = [makeGameStartedEvent()];
            const states = buildTimeline(events);

            expect(states[0].phase).toBe("pre_game");
            expect(states[0].players).toHaveLength(0);
            expect(states[0].gameId).toBe("");
        });
    });

    describe("intermediate states", () => {
        function buildDrawTimeline() {
            const events: ReplayEvent[] = [
                makeGameStartedEvent(),
                makeRoundStartedEvent(),
                makeDrawEvent(),
            ];
            return buildTimeline(events);
        }

        test("game_started creates players and sets gameId", () => {
            const [initial, afterGameStarted] = buildDrawTimeline();

            expect(initial.players).toHaveLength(0);
            expect(afterGameStarted.phase).toBe("pre_game");
            expect(afterGameStarted.players).toHaveLength(4);
            expect(afterGameStarted.gameId).toBe("timeline-test");
        });

        test("round_started deals tiles and enters in_round phase", () => {
            const [, , afterRoundStarted] = buildDrawTimeline();

            expect(afterRoundStarted.phase).toBe("in_round");
            expect(afterRoundStarted.players[0].tiles).toHaveLength(13);
            expect(afterRoundStarted.doraIndicators).toEqual([10]);
            expect(afterRoundStarted.roundWind).toBe(0);
        });

        test("draw adds a tile to the player's hand", () => {
            const [, , , afterDraw] = buildDrawTimeline();

            expect(afterDraw.players[0].tiles).toHaveLength(14);
            expect(afterDraw.players[0].tiles).toContain(52);
            expect(afterDraw.players[0].drawnTileId).toBe(52);
        });

        test("earlier states are not mutated by later events", () => {
            const events: ReplayEvent[] = [
                makeGameStartedEvent(),
                makeRoundStartedEvent(),
                makeDrawEvent(),
                makeDiscardEvent(),
            ];
            const [, , stateAfterRound, stateAfterDraw, stateAfterDiscard] = buildTimeline(events);

            expect(stateAfterRound.players[0].tiles).toHaveLength(13);
            expect(stateAfterRound.players[0].discards).toHaveLength(0);

            expect(stateAfterDraw.players[0].tiles).toHaveLength(14);
            expect(stateAfterDraw.players[0].drawnTileId).toBe(52);

            expect(stateAfterDiscard.players[0].tiles).toHaveLength(13);
            expect(stateAfterDiscard.players[0].discards).toHaveLength(1);
        });
    });

    describe("full game lifecycle", () => {
        test("produces correct final and round-end states", () => {
            const events: ReplayEvent[] = [
                makeGameStartedEvent(),
                makeRoundStartedEvent(),
                makeRoundEndEvent(),
                makeGameEndEvent(),
            ];
            const [, , , stateAfterRoundEnd, finalState] = buildTimeline(events);

            expect(finalState.phase).toBe("game_ended");
            expect(finalState.players[0].score).toBe(37000);
            expect(finalState.lastEventDescription).toBe("Game over - Winner: Alice");

            expect(stateAfterRoundEnd.phase).toBe("round_ended");
            expect(stateAfterRoundEnd.players[0].score).toBe(37000);
        });
    });
});
