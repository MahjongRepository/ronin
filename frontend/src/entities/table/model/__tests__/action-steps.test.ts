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

    test("events with no dora_revealed have stateIndex equal to descriptionStateIndex", () => {
        const events: ReplayEvent[] = [
            event("game_started"),
            event("round_started"),
            event("draw"),
            event("discard"),
        ];

        const steps = buildActionSteps(events);

        for (const step of steps) {
            expect(step.stateIndex).toBe(step.descriptionStateIndex);
        }
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

        // Initial step + one step per stopping event
        expect(steps).toHaveLength(9);
        expect(steps.map((s) => s.stateIndex)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8]);
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

    test("first step stateIndex is always 0", () => {
        const steps = buildActionSteps([event("game_started"), event("draw")]);

        expect(steps[0].stateIndex).toBe(0);
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

    test("last step stateIndex is events.length even when events end with dora_revealed", () => {
        const events: ReplayEvent[] = [event("meld"), event("dora_revealed")];

        const steps = buildActionSteps(events);

        expect(steps[steps.length - 1].stateIndex).toBe(events.length);
    });

    test("orphaned dora_revealed at the start is skipped", () => {
        const events: ReplayEvent[] = [event("dora_revealed"), event("game_started")];

        const steps = buildActionSteps(events);

        // Initial step + game_started step
        expect(steps).toHaveLength(2);
        expect(steps[0]).toEqual<ActionStep>({ descriptionStateIndex: 0, stateIndex: 0 });
        expect(steps[1]).toEqual<ActionStep>({ descriptionStateIndex: 2, stateIndex: 2 });
    });

    test("all non-stopping events still produce a terminal step at events.length", () => {
        const events: ReplayEvent[] = [event("dora_revealed"), event("dora_revealed")];

        const steps = buildActionSteps(events);

        // Initial step + terminal step to ensure the final state is reachable
        expect(steps).toHaveLength(2);
        expect(steps[0]).toEqual<ActionStep>({ descriptionStateIndex: 0, stateIndex: 0 });
        expect(steps[1]).toEqual<ActionStep>({ descriptionStateIndex: 2, stateIndex: 2 });
    });
});
