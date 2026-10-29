import { describe, expect, it } from "vitest";

import { loadSeatScenario } from "#tests/fixtures/seat-transcripts";
import {
    type GameClientState,
    decisionCountdown,
    nextCountdownChange,
    runSeatScenario,
    scenarioStateIndex,
    stepGameClient,
    timelineStates,
} from "@/entities/client";

const { scenario } = loadSeatScenario("call_prompt_seat_1");

function stateAt(label: string): GameClientState {
    const run = runSeatScenario(scenario);
    expect(run.mismatches).toEqual([]);
    return timelineStates(run.timeline)[scenarioStateIndex(scenario, label)];
}

const PROMPT = stateAt("prompt");
const EXPIRED = stepGameClient(PROMPT, { at: 8000, kind: "tick" }).state;

describe("decisionCountdown", () => {
    it("counts the open prompt's seconds down from the state's logical now, reading 1 until the deadline", () => {
        expect(decisionCountdown({ ...PROMPT, now: 7999 })).toEqual({
            kind: "running",
            move: "call",
            secondsLeft: 1,
        });
    });

    it("shows a prompt past its deadline as expired, an answered one as none, and one without a deadline as untimed", () => {
        const untimed = {
            ...PROMPT,
            decision: PROMPT.decision && { ...PROMPT.decision, deadline: null },
        };

        expect(decisionCountdown(EXPIRED)).toEqual({ kind: "expired", move: "call" });
        expect(decisionCountdown(stateAt("chi chosen"))).toBeNull();
        expect(decisionCountdown(untimed)).toEqual({ kind: "untimed", move: "call" });
    });
});

describe("nextCountdownChange", () => {
    it("wakes when the shown second changes, the last time at the deadline, and never once it expired", () => {
        expect(nextCountdownChange(PROMPT)).toBe(4000);
        expect(nextCountdownChange({ ...PROMPT, now: 4000 })).toBe(5000);
        expect(nextCountdownChange({ ...PROMPT, now: 7500 })).toBe(8000);
        expect(nextCountdownChange(EXPIRED)).toBeNull();
    });
});
