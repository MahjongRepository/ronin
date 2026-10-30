import { describe, expect, it } from "vitest";

import { checkpointState, loadSeatScenario } from "#tests/fixtures/seat-transcripts";
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
            turn: null,
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

describe("decisionCountdown - a turn's base and bank", () => {
    const FIRST_DRAW = checkpointState("own_turn_seat_1", "first draw");

    function at(state: GameClientState, now: number): GameClientState {
        return { ...state, now };
    }

    it("counts the base down with the whole bank behind it, then the bank alone once the base ran out", () => {
        expect(decisionCountdown(FIRST_DRAW)).toEqual({
            kind: "running",
            move: "turn",
            secondsLeft: 35,
            turn: { bankSeconds: 30, baseSeconds: 5, inBank: false },
        });
        expect(decisionCountdown(at(FIRST_DRAW, 7999))).toMatchObject({
            turn: { bankSeconds: 30, baseSeconds: 1, inBank: false },
        });
        expect(decisionCountdown(at(FIRST_DRAW, 8000))).toMatchObject({
            secondsLeft: 30,
            turn: { bankSeconds: 30, baseSeconds: 0, inBank: true },
        });
        expect(decisionCountdown(at(FIRST_DRAW, 20_500))).toMatchObject({
            secondsLeft: 18,
            turn: { bankSeconds: 18, baseSeconds: 0, inBank: true },
        });
    });

    it("takes a reconnect's elapsed time off the base first, never restarting the turn's time", () => {
        const inBase = checkpointState("own_turn_seat_1", "draw re-sent");
        const inBank = checkpointState("bank_reconnect_seat_1", "draw re-sent");

        expect(decisionCountdown(inBase)).toMatchObject({
            secondsLeft: 34,
            turn: { bankSeconds: 30, baseSeconds: 4, inBank: false },
        });
        expect(decisionCountdown(inBank)).toMatchObject({
            secondsLeft: 29,
            turn: { bankSeconds: 29, baseSeconds: 0, inBank: true },
        });
    });

    it("wakes when the base or the time left shows a new second, and at the bank's start", () => {
        expect(nextCountdownChange(FIRST_DRAW)).toBe(4000);
        expect(nextCountdownChange(at(FIRST_DRAW, 7500))).toBe(8000);
        expect(nextCountdownChange(at(FIRST_DRAW, 8000))).toBe(9000);
    });
});

describe("nextCountdownChange - the game start pause", () => {
    const STARTED = checkpointState("own_turn_seat_1", "game started");

    it("wakes as the pause's shown second changes, and no more once it ran out ahead of the deal", () => {
        expect(nextCountdownChange(STARTED)).toBe(1000);
        expect(nextCountdownChange({ ...STARTED, now: 3000 })).toBeNull();
    });
});
