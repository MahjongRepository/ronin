import { describe, expect, test } from "vitest";

import { buildActionSteps } from "@/entities/table/model/action-steps";
import {
    type NavigationIndex,
    buildNavigationIndex,
    roundForStep,
    turnsForStep,
} from "@/entities/table/model/navigation-index";
import { buildTimeline } from "@/entities/table/model/timeline";
import { type ReplayEvent } from "@/entities/table/model/types";
import {
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
        gameId: "test-game",
        players: [
            { isAiPlayer: false, name: "Alice", seat: 0 },
            { isAiPlayer: true, name: "Bot-1", seat: 1 },
            { isAiPlayer: true, name: "Bot-2", seat: 2 },
            { isAiPlayer: false, name: "Bob", seat: 3 },
        ],
        type: "game_started",
    };
}

function makeRoundStartedEvent(overrides?: Partial<RoundStartedEvent>): RoundStartedEvent {
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
        ...overrides,
    };
}

function makeDrawEvent(seat: number, tileId: number): DrawEvent {
    return {
        availableActions: [],
        seat,
        tileId,
        type: "draw",
    };
}

function makeTsumoRoundEnd(winnerSeat: number, scores: Record<string, number>): TsumoRoundEnd {
    return {
        closedTiles: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
        handResult: { fu: 30, han: 4, yaku: [{ han: 1, yakuId: 0 }] },
        melds: [],
        resultType: ROUND_RESULT_TYPE.TSUMO,
        scoreChanges: scores,
        scores,
        type: "round_end",
        winnerSeat,
        winningTile: 52,
    } as TsumoRoundEnd;
}

function makeGameEndEvent(): GameEndEvent {
    return {
        numRounds: 2,
        standings: [
            { finalScore: 40, score: 40000, seat: 0 },
            { finalScore: 20, score: 20000, seat: 1 },
            { finalScore: 20, score: 20000, seat: 2 },
            { finalScore: 20, score: 20000, seat: 3 },
        ],
        type: "game_end",
        winnerSeat: 0,
    };
}

/** Helper to build all three inputs for buildNavigationIndex from events. */
function buildNavInputs(events: ReplayEvent[]) {
    const states = buildTimeline(events);
    const actionSteps = buildActionSteps(events);
    return { actionSteps, events, states };
}

/** Helper to build a 2-round game's navigation index. */
function buildTwoRoundNavIndex() {
    const events: ReplayEvent[] = [
        makeGameStartedEvent(),
        makeRoundStartedEvent({ honbaSticks: 0, roundNumber: 1, wind: 0 }),
        makeDrawEvent(0, 52),
        makeTsumoRoundEnd(0, { "0": 33000, "1": 22300, "2": 22300, "3": 22300 }),
        makeRoundStartedEvent({ honbaSticks: 1, roundNumber: 2, wind: 0 }),
        makeDrawEvent(0, 53),
        makeTsumoRoundEnd(0, { "0": 41000, "1": 19600, "2": 19600, "3": 19600 }),
        makeGameEndEvent(),
    ];
    const { actionSteps, states } = buildNavInputs(events);
    return { actionSteps, events, navIndex: buildNavigationIndex(events, actionSteps, states) };
}

describe("buildNavigationIndex", () => {
    test("game with 2 rounds has 2 entries with correct wind/number/honba/result", () => {
        const { navIndex } = buildTwoRoundNavIndex();

        expect(navIndex.rounds).toHaveLength(2);

        expect(navIndex.rounds[0]).toMatchObject({
            honba: 0,
            resultDescription: "Tsumo by Alice",
            roundNumber: 1,
            wind: 0,
        });

        expect(navIndex.rounds[1]).toMatchObject({
            honba: 1,
            resultDescription: "Tsumo by Alice",
            roundNumber: 2,
            wind: 0,
        });
    });

    test("turnsForStep returns correct draw-based turns within a round", () => {
        const events: ReplayEvent[] = [
            makeGameStartedEvent(),
            makeRoundStartedEvent(),
            makeDrawEvent(0, 52),
            makeDrawEvent(1, 53),
            makeDrawEvent(2, 54),
            makeTsumoRoundEnd(2, { "0": 22000, "1": 22000, "2": 34000, "3": 22000 }),
            makeGameEndEvent(),
        ];

        const { actionSteps, states } = buildNavInputs(events);
        const navIndex = buildNavigationIndex(events, actionSteps, states);
        const turns = turnsForStep(navIndex, navIndex.rounds[0].actionStepIndex);

        expect(turns).toHaveLength(3);
        expect(turns[0]).toMatchObject({ playerName: "Alice", turnNumber: 1 });
        expect(turns[1]).toMatchObject({ playerName: "Bot-1", turnNumber: 2 });
        expect(turns[2]).toMatchObject({ playerName: "Bot-2", turnNumber: 3 });
    });

    test("roundForStep returns correct round at boundaries and mid-round", () => {
        const { navIndex } = buildTwoRoundNavIndex();

        const round1 = roundForStep(navIndex, navIndex.rounds[0].actionStepIndex);
        expect(round1?.roundNumber).toBe(1);

        const midRound1 = roundForStep(navIndex, navIndex.rounds[0].actionStepIndex + 1);
        expect(midRound1?.roundNumber).toBe(1);

        const round2 = roundForStep(navIndex, navIndex.rounds[1].actionStepIndex);
        expect(round2?.roundNumber).toBe(2);
    });

    test("step at game_started (before any round) returns undefined / empty", () => {
        const { navIndex } = buildTwoRoundNavIndex();

        expect(roundForStep(navIndex, 0)).toBeUndefined();
        expect(roundForStep(navIndex, 1)).toBeUndefined();
        expect(turnsForStep(navIndex, 0)).toEqual([]);
        expect(turnsForStep(navIndex, 1)).toEqual([]);
    });

    test("stepToRoundIndex has correct length matching actionSteps length", () => {
        const { actionSteps, navIndex } = buildTwoRoundNavIndex();

        expect(navIndex.stepToRoundIndex).toHaveLength(actionSteps.length);
    });

    test("game_end step is not part of any round", () => {
        const { actionSteps, navIndex } = buildTwoRoundNavIndex();
        const lastStep = actionSteps.length - 1;

        expect(roundForStep(navIndex, lastStep)).toBeUndefined();
    });

    test("turn numbers are 1-based and reset for each round", () => {
        const events: ReplayEvent[] = [
            makeGameStartedEvent(),
            makeRoundStartedEvent({ roundNumber: 1, wind: 0 }),
            makeDrawEvent(0, 52),
            makeDrawEvent(1, 53),
            makeTsumoRoundEnd(0, { "0": 33000, "1": 22300, "2": 22300, "3": 22300 }),
            makeRoundStartedEvent({ roundNumber: 2, wind: 0 }),
            makeDrawEvent(0, 54),
            makeTsumoRoundEnd(0, { "0": 41000, "1": 19600, "2": 19600, "3": 19600 }),
            makeGameEndEvent(),
        ];

        const { actionSteps, states } = buildNavInputs(events);
        const navIndex = buildNavigationIndex(events, actionSteps, states);

        const [round1Turns, round2Turns] = navIndex.turnsByRound;
        expect(round1Turns).toHaveLength(2);
        expect(round1Turns[0].turnNumber).toBe(1);
        expect(round1Turns[1].turnNumber).toBe(2);

        expect(round2Turns).toHaveLength(1);
        expect(round2Turns[0].turnNumber).toBe(1);
    });
});

describe("single-round game", () => {
    function buildSingleRoundNavIndex() {
        const events: ReplayEvent[] = [
            makeGameStartedEvent(),
            makeRoundStartedEvent({ honbaSticks: 0, roundNumber: 1, wind: 0 }),
            makeDrawEvent(0, 52),
            makeDrawEvent(1, 53),
            makeTsumoRoundEnd(0, { "0": 33000, "1": 22300, "2": 22300, "3": 22300 }),
            makeGameEndEvent(),
        ];
        const { actionSteps, states } = buildNavInputs(events);
        return { actionSteps, events, navIndex: buildNavigationIndex(events, actionSteps, states) };
    }

    test("produces exactly one round entry", () => {
        const { navIndex } = buildSingleRoundNavIndex();

        expect(navIndex.rounds).toHaveLength(1);
        expect(navIndex.rounds[0]).toMatchObject({
            honba: 0,
            resultDescription: "Tsumo by Alice",
            roundNumber: 1,
            wind: 0,
        });
    });

    test("turns are collected for the single round", () => {
        const { navIndex } = buildSingleRoundNavIndex();

        expect(navIndex.turnsByRound).toHaveLength(1);
        expect(navIndex.turnsByRound[0]).toHaveLength(2);
        expect(navIndex.turnsByRound[0][0]).toMatchObject({ playerName: "Alice", turnNumber: 1 });
        expect(navIndex.turnsByRound[0][1]).toMatchObject({ playerName: "Bot-1", turnNumber: 2 });
    });

    test("roundForStep returns the round for mid-round steps", () => {
        const { navIndex } = buildSingleRoundNavIndex();
        const roundStep = navIndex.rounds[0].actionStepIndex;

        expect(roundForStep(navIndex, roundStep)?.roundNumber).toBe(1);
        expect(roundForStep(navIndex, roundStep + 1)?.roundNumber).toBe(1);
    });
});

describe("game ending mid-round (no round_end before game_end)", () => {
    function buildMidRoundEndNavIndex() {
        const events: ReplayEvent[] = [
            makeGameStartedEvent(),
            makeRoundStartedEvent({ honbaSticks: 0, roundNumber: 1, wind: 0 }),
            makeDrawEvent(0, 52),
            makeDrawEvent(1, 53),
            // game_end directly without round_end
            makeGameEndEvent(),
        ];
        const { actionSteps, states } = buildNavInputs(events);
        return { actionSteps, events, navIndex: buildNavigationIndex(events, actionSteps, states) };
    }

    test("round has empty resultDescription when no round_end precedes game_end", () => {
        const { navIndex } = buildMidRoundEndNavIndex();

        expect(navIndex.rounds).toHaveLength(1);
        expect(navIndex.rounds[0].resultDescription).toBe("");
    });

    test("turns are still collected for the incomplete round", () => {
        const { navIndex } = buildMidRoundEndNavIndex();

        expect(navIndex.turnsByRound).toHaveLength(1);
        expect(navIndex.turnsByRound[0]).toHaveLength(2);
    });

    test("game_end step is not assigned to any round", () => {
        const { actionSteps, navIndex } = buildMidRoundEndNavIndex();
        const lastStep = actionSteps.length - 1;

        expect(roundForStep(navIndex, lastStep)).toBeUndefined();
    });
});

describe("roundForStep", () => {
    test("returns undefined for out-of-bounds step", () => {
        const navIndex: NavigationIndex = {
            rounds: [],
            stepToRoundIndex: [-1],
            turnsByRound: [],
        };

        expect(roundForStep(navIndex, 999)).toBeUndefined();
    });
});

describe("turnsForStep", () => {
    test("returns empty array for step with no round", () => {
        const navIndex: NavigationIndex = {
            rounds: [],
            stepToRoundIndex: [-1, -1],
            turnsByRound: [],
        };

        expect(turnsForStep(navIndex, 0)).toEqual([]);
        expect(turnsForStep(navIndex, 1)).toEqual([]);
    });
});
