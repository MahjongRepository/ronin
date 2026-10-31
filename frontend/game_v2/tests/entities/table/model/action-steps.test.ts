import { describe, expect, test } from "vitest";

import {
    makeAiReplacementLine,
    makeClosedKanEvent,
    makeDiscardEvent,
    makeDoraRevealedEvent,
    makeDrawEvent,
    makeGameEndEvent,
    makeGameStartedEvent,
    makeRiichiDeclaredEvent,
    makeRoundStartedEvent,
    makeTsumoRoundEnd,
} from "#tests/fixtures/events";
import {
    type ActionStep,
    type StepEvent,
    buildActionSteps,
} from "@/entities/table/model/action-steps";

function ranges(events: readonly StepEvent[]): [number, number, number][] {
    return buildActionSteps(events).map((step: ActionStep) => [
        step.firstEntry,
        step.moveEntry,
        step.stateIndex,
    ]);
}

describe("buildActionSteps", () => {
    test("opens on the deal with its first draw, the game start shown from there", () => {
        const events = [
            makeGameStartedEvent(),
            makeRoundStartedEvent(),
            makeDrawEvent(),
            makeDiscardEvent(),
        ];

        expect(ranges(events)).toEqual([
            [0, 1, 3],
            [3, 3, 4],
        ]);
    });

    test("folds the dora a kan turns into the kan's stop", () => {
        const events = [
            makeRoundStartedEvent(),
            makeDrawEvent(),
            makeClosedKanEvent(),
            makeDoraRevealedEvent(),
            makeDrawEvent(),
        ];

        expect(ranges(events)).toEqual([
            [0, 0, 2],
            [2, 2, 4],
            [4, 4, 5],
        ]);
    });

    test("tells a seat control line on the next stop when no bookkeeping follows it", () => {
        const events = [
            makeRoundStartedEvent(),
            makeDrawEvent(),
            makeDiscardEvent(),
            makeAiReplacementLine(),
            makeDrawEvent({ seat: 1 }),
        ];

        expect(ranges(events)).toEqual([
            [0, 0, 2],
            [2, 2, 3],
            [3, 4, 5],
        ]);
    });

    test("runs a riichi discard's stop through its acceptance past a seat control line between", () => {
        const events = [
            makeRoundStartedEvent(),
            makeDrawEvent(),
            makeDiscardEvent({ isRiichi: true }),
            makeAiReplacementLine(),
            makeRiichiDeclaredEvent(),
            makeAiReplacementLine({ seat: 3 }),
            makeDrawEvent({ seat: 1 }),
        ];

        expect(ranges(events)).toEqual([
            [0, 0, 2],
            [2, 2, 5],
            [5, 6, 7],
        ]);
    });

    test("runs a deal's stop through its first draw past a seat control line between", () => {
        const events = [
            makeRoundStartedEvent(),
            makeAiReplacementLine(),
            makeDrawEvent(),
            makeDiscardEvent(),
        ];

        expect(ranges(events)).toEqual([
            [0, 0, 3],
            [3, 3, 4],
        ]);
    });

    test("joins entries after the last move to the last stop", () => {
        const events = [
            makeRoundStartedEvent(),
            makeDrawEvent(),
            makeTsumoRoundEnd(),
            makeGameEndEvent(),
            makeAiReplacementLine(),
        ];

        expect(ranges(events)).toEqual([
            [0, 0, 2],
            [2, 2, 3],
            [3, 3, 5],
        ]);
    });

    test("makes no stop of a replay with no move", () => {
        expect(ranges([makeGameStartedEvent(), makeAiReplacementLine()])).toEqual([]);
    });
});
