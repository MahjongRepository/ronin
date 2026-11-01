import { describe, expect, it } from "vitest";

import { checkpointState, loadSeatScenario } from "#tests/fixtures/seat-transcripts";
import {
    type LiveClient,
    type SoundCue,
    decisionOf,
    readSoundSetting,
    runSeatScenario,
    scenarioStateIndex,
    soundCues,
    stepGameClient,
    timelineStates,
} from "@/entities/client";

/** The cues of the named scenario's steps after the one labelled `from` through the one labelled `to`, in order. */
function cuesAfter(name: string, from: string, to: string): readonly SoundCue[] {
    const { scenario } = loadSeatScenario(name);
    const states = timelineStates(runSeatScenario(scenario).timeline);
    const [start, end] = [from, to].map((label) => scenarioStateIndex(scenario, label));
    return states
        .slice(start, end)
        .flatMap((before, index) => soundCues(before, states[start + index + 1]));
}

/** The cues of each tick at `offsets` ms before the open decision's deadline, stepped one after the other. */
function cuesBeforeDeadline(
    state: LiveClient,
    offsets: readonly number[],
): (readonly SoundCue[])[] {
    const deadline = decisionOf(state)?.deadline;
    if (deadline === null || deadline === undefined) {
        throw new Error("no timed decision");
    }
    let before = state;
    return offsets.map((offset) => {
        const after = stepGameClient(before, { at: deadline - offset, kind: "tick" }).state;
        const cues = soundCues(before, after);
        before = after;
        return cues;
    });
}

describe("soundCues", () => {
    it("clicks every discard and voices each call as it shows, staying quiet for a reconnect's snapshot and its re-sent prompt", () => {
        const scenario = "riichi_reconnect_seat_1";

        expect([
            cuesAfter(scenario, "riichi chosen", "riichi accepted"),
            cuesAfter(scenario, "dropped", "ron prompt re-sent"),
            cuesAfter(scenario, "ron chosen", "round end"),
        ]).toEqual([["discard", "riichi"], [], ["ron"]]);
    });

    it("rings the gong with the voice of a win at a yakuman limit", () => {
        expect(cuesAfter("first_turn_win_seat_1", "tsumo chosen", "round end")).toEqual([
            "tsumo",
            "yakuman",
        ]);
    });

    it("beeps once for each of a long turn's last five seconds, and never for a call prompt of five seconds", () => {
        const turn = cuesBeforeDeadline(
            checkpointState("own_turn_seat_1", "first draw"),
            [6000, 5000, 4500, 4000, 1000],
        );
        const prompt = cuesBeforeDeadline(
            checkpointState("call_prompt_seat_1", "prompt"),
            [4000, 1000],
        );

        expect(turn).toEqual([[], ["beep"], [], ["beep"], ["beep"]]);
        expect(prompt).toEqual([[], []]);
    });
});

describe("readSoundSetting", () => {
    it("reads the v1 client's stored setting, and keeps the sound on for anything else", () => {
        expect(
            [{ sound_on: false }, { sound_on: "no" }, null, []].map((stored) =>
                readSoundSetting(stored),
            ),
        ).toEqual([
            { sound_on: false },
            { sound_on: true },
            { sound_on: true },
            { sound_on: true },
        ]);
    });
});
