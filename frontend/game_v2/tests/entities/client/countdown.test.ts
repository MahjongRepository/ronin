import { assert, describe, expect, it } from "vitest";

import { checkpointState, loadSeatScenario } from "#tests/fixtures/seat-transcripts";
import {
    type LiveClient,
    decisionCountdown,
    decisionOf,
    nextCountdownChange,
    roundConfirmOf,
    runSeatScenario,
    scenarioStateIndex,
    stepGameClient,
    timelineStates,
} from "@/entities/client";

const { scenario } = loadSeatScenario("call_prompt_seat_1");

function stateAt(label: string): LiveClient {
    const run = runSeatScenario(scenario);
    expect(run.mismatches).toEqual([]);
    return timelineStates(run.timeline)[scenarioStateIndex(scenario, label)];
}

const PROMPT = stateAt("prompt");
const EXPIRED = stepGameClient(PROMPT, { at: 28_000, kind: "tick" }).state;

describe("decisionCountdown", () => {
    it("counts the open prompt's seconds down from the state's logical now, reading 1 until the deadline", () => {
        expect(decisionCountdown({ ...PROMPT, now: 27_999 })).toEqual({
            clock: { bankSeconds: 1, baseSeconds: 0, inBank: true },
            kind: "running",
            move: "call",
            secondsLeft: 1,
        });
    });

    it("shows a prompt past its deadline as expired, an answered one as none, and one without a deadline as untimed", () => {
        const prompt = decisionOf(PROMPT);
        assert(prompt !== null);
        const untimed: LiveClient = {
            ...PROMPT,
            sync: {
                kind: "in_step",
                pending: { decision: { ...prompt, deadline: null }, kind: "decision" },
            },
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
        expect(nextCountdownChange({ ...PROMPT, now: 27_500 })).toBe(28_000);
        expect(nextCountdownChange(EXPIRED)).toBeNull();
    });
});

describe("decisionCountdown - a turn's base and bank", () => {
    const FIRST_DRAW = checkpointState("own_turn_seat_1", "first draw");

    function at(state: LiveClient, now: number): LiveClient {
        return { ...state, now };
    }

    it("counts the base down with the whole bank behind it, then the bank alone once the base ran out", () => {
        expect(decisionCountdown(FIRST_DRAW)).toEqual({
            clock: { bankSeconds: 20, baseSeconds: 5, inBank: false },
            kind: "running",
            move: "turn",
            secondsLeft: 25,
        });
        expect(decisionCountdown(at(FIRST_DRAW, 7999))).toMatchObject({
            clock: { bankSeconds: 20, baseSeconds: 1, inBank: false },
        });
        expect(decisionCountdown(at(FIRST_DRAW, 8000))).toMatchObject({
            clock: { bankSeconds: 20, baseSeconds: 0, inBank: true },
            secondsLeft: 20,
        });
        expect(decisionCountdown(at(FIRST_DRAW, 20_500))).toMatchObject({
            clock: { bankSeconds: 8, baseSeconds: 0, inBank: true },
            secondsLeft: 8,
        });
    });

    it("takes a reconnect's elapsed time off the base first, never restarting the turn's time", () => {
        const inBase = checkpointState("own_turn_seat_1", "draw re-sent");
        const inBank = checkpointState("bank_reconnect_seat_1", "draw re-sent");

        expect(decisionCountdown(inBase)).toMatchObject({
            clock: { bankSeconds: 20, baseSeconds: 4, inBank: false },
            secondsLeft: 24,
        });
        expect(decisionCountdown(inBank)).toMatchObject({
            clock: { bankSeconds: 19, baseSeconds: 0, inBank: true },
            secondsLeft: 19,
        });
    });

    it("wakes when the base or the time left shows a new second, and at the bank's start", () => {
        expect(nextCountdownChange(FIRST_DRAW)).toBe(4000);
        expect(nextCountdownChange(at(FIRST_DRAW, 7500))).toBe(8000);
        expect(nextCountdownChange(at(FIRST_DRAW, 8000))).toBe(9000);
    });
});

describe("nextCountdownChange - the start confirm", () => {
    const DEALT = stateAt("dealt");

    it("wakes as the start confirm's shown second changes, and no more once its time ran out ahead of the first draw", () => {
        const owed = roundConfirmOf(DEALT);
        assert(owed?.kind === "owed" && owed.deadline !== null);

        expect(nextCountdownChange(DEALT)).toBe(owed.deadline - 9000);
        expect(nextCountdownChange({ ...DEALT, now: owed.deadline })).toBeNull();
    });
});
