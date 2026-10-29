import { describe, expect, test } from "vitest";

import {
    makeDrawEvent,
    makeGameEndEvent,
    makeGameStartedEvent,
    makeRoundStartedEvent,
    makeTsumoRoundEnd,
} from "#tests/fixtures/events";
import { loadEngineReplay } from "#tests/fixtures/replays";
import { buildActionSteps } from "@/entities/table/model/action-steps";
import { applyEvent } from "@/entities/table/model/apply-event";
import { createInitialTableState } from "@/entities/table/model/initial-state";
import {
    type NavigationIndex,
    buildNavigationIndex,
    roundForStep,
    turnsForStep,
} from "@/entities/table/model/navigation-index";
import { type ReplayEvent, type TableState } from "@/entities/table/model/types";

function buildNavInputs(events: readonly ReplayEvent[]) {
    const states: TableState[] = [createInitialTableState()];
    for (const event of events) {
        states.push(applyEvent(states[states.length - 1], event));
    }
    const actionSteps = buildActionSteps(events);
    return { actionSteps, events, states };
}

function buildTwoRoundNavIndex() {
    const events: ReplayEvent[] = [
        makeGameStartedEvent(),
        makeRoundStartedEvent({ honbaSticks: 0, roundNumber: 1, wind: 0 }),
        makeDrawEvent({ seat: 0, tileId: 52 }),
        makeTsumoRoundEnd({ winnerSeat: 0 }),
        makeRoundStartedEvent({ dealerSeat: 1, honbaSticks: 1, roundNumber: 2, wind: 0 }),
        makeDrawEvent({ seat: 0, tileId: 53 }),
        makeTsumoRoundEnd({ winnerSeat: 0 }),
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
            roundInWind: 1,
            wind: 0,
        });

        expect(navIndex.rounds[1]).toMatchObject({
            honba: 1,
            resultDescription: "Tsumo by Alice",
            roundInWind: 2,
            wind: 0,
        });
    });

    test("turnsForStep returns correct draw-based turns within a round", () => {
        const events: ReplayEvent[] = [
            makeGameStartedEvent(),
            makeRoundStartedEvent(),
            makeDrawEvent({ seat: 0, tileId: 52 }),
            makeDrawEvent({ seat: 1, tileId: 53 }),
            makeDrawEvent({ seat: 2, tileId: 54 }),
            makeTsumoRoundEnd({ winnerSeat: 2 }),
            makeGameEndEvent(),
        ];

        const { actionSteps, states } = buildNavInputs(events);
        const navIndex = buildNavigationIndex(events, actionSteps, states);
        const turns = turnsForStep(navIndex, navIndex.rounds[0].actionStepIndex);

        // First draw is batched with round_started, so only 2 separate turns
        expect(turns).toHaveLength(2);
        expect(turns[0]).toMatchObject({ playerName: "Bot-1", turnNumber: 1 });
        expect(turns[1]).toMatchObject({ playerName: "Bot-2", turnNumber: 2 });
    });

    test("roundForStep returns correct round at boundaries and mid-round", () => {
        const { navIndex } = buildTwoRoundNavIndex();

        const round1 = roundForStep(navIndex, navIndex.rounds[0].actionStepIndex);
        expect(round1?.roundInWind).toBe(1);

        const midRound1 = roundForStep(navIndex, navIndex.rounds[0].actionStepIndex + 1);
        expect(midRound1?.roundInWind).toBe(1);

        const round2 = roundForStep(navIndex, navIndex.rounds[1].actionStepIndex);
        expect(round2?.roundInWind).toBe(2);
    });

    test("step at game_started (before any round) returns undefined / empty", () => {
        const { navIndex } = buildTwoRoundNavIndex();

        // Step 0 is the initial step (post-game_started, pre_game phase)
        expect(roundForStep(navIndex, 0)).toBeUndefined();
        expect(turnsForStep(navIndex, 0)).toEqual([]);
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
            makeDrawEvent({ seat: 0, tileId: 52 }),
            makeDrawEvent({ seat: 1, tileId: 53 }),
            makeTsumoRoundEnd({ winnerSeat: 0 }),
            makeRoundStartedEvent({ roundNumber: 2, wind: 0 }),
            makeDrawEvent({ seat: 0, tileId: 54 }),
            makeTsumoRoundEnd({ winnerSeat: 0 }),
            makeGameEndEvent(),
        ];

        const { actionSteps, states } = buildNavInputs(events);
        const navIndex = buildNavigationIndex(events, actionSteps, states);

        const [round1Turns, round2Turns] = navIndex.turnsByRound;
        // First draw in each round is batched with round_started
        expect(round1Turns).toHaveLength(1);
        expect(round1Turns[0].turnNumber).toBe(1);

        expect(round2Turns).toHaveLength(0);
    });
});

describe("single-round game", () => {
    function buildSingleRoundNavIndex() {
        const events: ReplayEvent[] = [
            makeGameStartedEvent(),
            makeRoundStartedEvent({ honbaSticks: 0, roundNumber: 1, wind: 0 }),
            makeDrawEvent({ seat: 0, tileId: 52 }),
            makeDrawEvent({ seat: 1, tileId: 53 }),
            makeTsumoRoundEnd({ winnerSeat: 0 }),
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
            roundInWind: 1,
            wind: 0,
        });
    });

    test("turns are collected for the single round", () => {
        const { navIndex } = buildSingleRoundNavIndex();

        expect(navIndex.turnsByRound).toHaveLength(1);
        // First draw is batched with round_started, only second draw is a turn
        expect(navIndex.turnsByRound[0]).toHaveLength(1);
        expect(navIndex.turnsByRound[0][0]).toMatchObject({ playerName: "Bot-1", turnNumber: 1 });
    });

    test("roundForStep returns the round for mid-round steps", () => {
        const { navIndex } = buildSingleRoundNavIndex();
        const roundStep = navIndex.rounds[0].actionStepIndex;

        expect(roundForStep(navIndex, roundStep)?.roundInWind).toBe(1);
        expect(roundForStep(navIndex, roundStep + 1)?.roundInWind).toBe(1);
    });
});

describe("game ending mid-round (no round_end before game_end)", () => {
    function buildMidRoundEndNavIndex() {
        const events: ReplayEvent[] = [
            makeGameStartedEvent(),
            makeRoundStartedEvent({ honbaSticks: 0, roundNumber: 1, wind: 0 }),
            makeDrawEvent({ seat: 0, tileId: 52 }),
            makeDrawEvent({ seat: 1, tileId: 53 }),
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
        // First draw is batched with round_started, only second draw is a turn
        expect(navIndex.turnsByRound[0]).toHaveLength(1);
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

describe("buildNavigationIndex - engine replays", () => {
    function roundsOf(name: string): (string | number)[][] {
        const { events, tables } = loadEngineReplay(name);
        const navIndex = buildNavigationIndex(events, buildActionSteps(events), tables);
        return navIndex.rounds.map((round) => [
            round.wind,
            round.roundInWind,
            round.honba,
            round.resultDescription,
        ]);
    }

    test("numbers each round within its wind from a first dealer off seat 0, a dealer's repeat keeping it", () => {
        expect(roundsOf("eager_game")).toEqual([
            [0, 1, 0, "Tsumo by Diana"],
            [0, 2, 0, "Tsumo by Bob"],
            [0, 2, 1, "Ron by Charlie from Alice"],
            [0, 3, 0, "Exhaustive draw"],
            [0, 4, 1, "Ron by Charlie from Diana"],
            [1, 1, 0, "Ron by Bob from Charlie"],
            [1, 2, 0, "Tsumo by Charlie"],
            [1, 3, 0, "Ron by Bob from Alice"],
            [1, 4, 0, "Tsumo by Diana"],
        ]);
    });

    test("starts each wind over at 1, into the West round", () => {
        expect(roundsOf("full_game").map(([wind, round]) => [wind, round])).toEqual([
            [0, 1],
            [0, 2],
            [0, 3],
            [0, 4],
            [1, 1],
            [1, 2],
            [1, 3],
            [1, 4],
            [2, 1],
            [2, 2],
            [2, 3],
            [2, 4],
        ]);
    });
});
