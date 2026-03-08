import { describe, expect, test } from "vitest";

import { type ActionStep, buildActionSteps } from "@/entities/table/model/action-steps";
import { type ReplayEvent } from "@/entities/table/model/types";

/** Creates a minimal ReplayEvent with only the type field set. */
function event(type: ReplayEvent["type"]): ReplayEvent {
    return { type } as ReplayEvent;
}

describe("buildActionSteps", () => {
    test("empty events returns single step at index 0", () => {
        const steps = buildActionSteps([]);

        expect(steps).toEqual<ActionStep[]>([{ descriptionStateIndex: 0, stateIndex: 0 }]);
    });

    test("all stopping event types produce action steps", () => {
        const events: ReplayEvent[] = [
            event("game_started"),
            event("round_started"),
            event("draw"),
            event("discard"),
            event("meld"),
            event("riichi_declared"),
            event("round_end"),
            event("game_end"),
        ];

        const steps = buildActionSteps(events);

        // Initial step (past game_started) + round_started (batched with draw) + 5 remaining stopping events
        expect(steps).toHaveLength(7);
        expect(steps.map((s) => s.stateIndex)).toEqual([1, 3, 4, 5, 6, 7, 8]);
    });

    test("last step stateIndex is always events.length", () => {
        const events: ReplayEvent[] = [
            event("game_started"),
            event("round_started"),
            event("draw"),
        ];

        const steps = buildActionSteps(events);

        expect(steps[steps.length - 1].stateIndex).toBe(events.length);
    });

    describe("non-stopping event batching", () => {
        test("first draw after round_started is batched with it", () => {
            const events: ReplayEvent[] = [
                event("game_started"),
                event("round_started"),
                event("draw"),
                event("discard"),
            ];

            const steps = buildActionSteps(events);

            // round_started step: description at state 2 (round_started), display at state 3 (past draw)
            const roundStep = steps.find((s) => s.descriptionStateIndex === 2);
            expect(roundStep).toBeDefined();
            expect(roundStep!.stateIndex).toBe(3);
        });

        test("draw after discard is a normal stopping event", () => {
            const events: ReplayEvent[] = [
                event("round_started"),
                event("draw"),
                event("discard"),
                event("draw"),
            ];

            const steps = buildActionSteps(events);

            // initial + round_started (batched with first draw) + discard + second draw
            expect(steps).toHaveLength(4);
            expect(steps.map((s) => s.stateIndex)).toEqual([0, 2, 3, 4]);
        });

        test("dora_revealed after kan is batched — stateIndex past dora, descriptionStateIndex at kan", () => {
            const events: ReplayEvent[] = [
                event("game_started"),
                event("round_started"),
                event("draw"),
                event("discard"),
                event("meld"), // kan at event index 4 → state index 5
                event("dora_revealed"), // bookkeeping at event index 5 → state index 6
                event("draw"),
            ];

            const steps = buildActionSteps(events);

            // Find the step for the kan meld
            const kanStep = steps.find((s) => s.descriptionStateIndex === 5);
            expect(kanStep).toBeDefined();
            // Display state should be past the dora_revealed
            expect(kanStep!.stateIndex).toBe(6);
            // Description should point to the kan
            expect(kanStep!.descriptionStateIndex).toBe(5);
        });

        test("multiple consecutive non-stopping events are all batched into one step", () => {
            const events: ReplayEvent[] = [
                event("meld"), // stopping event at index 0
                event("dora_revealed"), // non-stopping at index 1
                event("dora_revealed"), // non-stopping at index 2
                event("dora_revealed"), // non-stopping at index 3
                event("draw"), // stopping event at index 4
            ];

            const steps = buildActionSteps(events);

            // Initial step + meld step (batched with 3 dora) + draw step
            expect(steps).toHaveLength(3);

            // Meld step: description at state 1 (the meld), display at state 4 (past all doras)
            expect(steps[1]).toEqual<ActionStep>({ descriptionStateIndex: 1, stateIndex: 4 });

            // Draw step
            expect(steps[2]).toEqual<ActionStep>({ descriptionStateIndex: 5, stateIndex: 5 });
        });

        test("last step stateIndex is events.length even when events end with dora_revealed", () => {
            const events: ReplayEvent[] = [event("meld"), event("dora_revealed")];

            const steps = buildActionSteps(events);

            expect(steps[steps.length - 1].stateIndex).toBe(events.length);
        });
    });

    describe("initial step advancement", () => {
        test("first step stateIndex advances past leading non-stopping events", () => {
            const steps = buildActionSteps([event("game_started"), event("draw")]);

            // game_started is non-stopping, so the initial step lands on state 1
            expect(steps[0].stateIndex).toBe(1);
        });

        test("leading non-stopping events are absorbed into the initial step", () => {
            const events: ReplayEvent[] = [event("dora_revealed"), event("game_started")];

            const steps = buildActionSteps(events);

            // Both events are non-stopping, so a single step lands at the terminal state
            expect(steps).toHaveLength(1);
            expect(steps[0]).toEqual<ActionStep>({ descriptionStateIndex: 2, stateIndex: 2 });
        });

        test("all non-stopping events are absorbed into a single initial step", () => {
            const events: ReplayEvent[] = [event("dora_revealed"), event("dora_revealed")];

            const steps = buildActionSteps(events);

            // The initial step advances past all non-stopping events to the terminal state
            expect(steps).toHaveLength(1);
            expect(steps[0]).toEqual<ActionStep>({ descriptionStateIndex: 2, stateIndex: 2 });
        });
    });
});
