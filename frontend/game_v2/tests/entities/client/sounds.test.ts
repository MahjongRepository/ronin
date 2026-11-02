import { assert, describe, expect, it } from "vitest";

import {
    checkpointState,
    loadSeatScenario,
    receivedPayload,
} from "#tests/fixtures/seat-transcripts";
import { wirePayloadList } from "#tests/fixtures/wire";
import {
    type LiveClient,
    NO_PLAY_UI,
    type SoundCue,
    decisionOf,
    playDisplay,
    readSoundSetting,
    runSeatScenario,
    scenarioStateIndex,
    soundCues,
    stepGameClient,
    timelineStates,
} from "@/entities/client";
import { CALLOUT_MS } from "@/entities/table";
import { ROUND_RESULT_TYPE } from "@/shared/protocol";

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
    it.each([
        ["call_prompt_seat_1", "prompt", "chi"],
        ["call_prompt_seat_1", "prompt", "pon"],
        ["call_prompt_seat_1", "prompt", "kan"],
        ["own_turn_seat_1", "first draw", "kan"],
        ["riichi_reconnect_seat_1", "ron prompt re-sent", "ron"],
        ["own_turn_seat_1", "first draw", "riichi"],
        ["first_turn_win_seat_1", "tenhou draw", "tsumo"],
    ])(
        "announces %s / %s / %s immediately without moving tiles or accepting a second answer",
        (name, label, kind) => {
            const before = checkpointState(name, label);
            const offer = decisionOf(before)?.offers.find((candidate) => candidate.kind === kind);
            assert(offer !== undefined);
            const event = {
                at: before.now,
                intent: { offer, type: "choose" },
                kind: "intent",
            } as const;
            const declared = stepGameClient(before, event);
            expect(declared.state.table).toBe(before.table);
            const display = playDisplay(declared.state, NO_PLAY_UI);
            expect({
                actions: display.actions,
                calls: display.callouts?.items.map(({ kind: called, position }) => [
                    called,
                    position,
                ]),
                countdown: display.countdown,
                decision: display.decisionStanding,
                sends: declared.effects.length,
                sounds: soundCues(before, declared.state),
            }).toEqual({
                actions: [],
                calls: [[kind, "bottom"]],
                countdown: null,
                decision: null,
                sends: 1,
                sounds: [kind],
            });

            const repeated = stepGameClient(declared.state, event);
            expect([
                repeated.effects,
                repeated.state.calls === declared.state.calls,
                soundCues(declared.state, repeated.state),
            ]).toEqual([[], true, []]);
        },
    );

    it("clicks every discard and voices each call as it shows, staying quiet for a reconnect's snapshot and its re-sent prompt", () => {
        const scenario = "riichi_reconnect_seat_1";

        expect([
            cuesAfter(scenario, "riichi chosen", "riichi accepted"),
            cuesAfter(scenario, "dropped", "ron prompt re-sent"),
            cuesAfter(scenario, "ron chosen", "round end"),
        ]).toEqual([["discard"], [], []]);
    });

    it("waits for the server's yakuman result to ring the gong after declaring the win", () => {
        expect(cuesAfter("first_turn_win_seat_1", "tenhou draw", "tsumo chosen")).toEqual([
            "tsumo",
        ]);
        expect(cuesAfter("first_turn_win_seat_1", "tsumo chosen", "round end")).toEqual([
            "yakuman",
        ]);
    });

    it("does not repeat a chi even when its confirmation arrives after the callout expires", () => {
        const { scenario } = loadSeatScenario("call_prompt_seat_1");
        const chosen = checkpointState("call_prompt_seat_1", "chi chosen");
        const at = chosen.now + CALLOUT_MS;
        const expired = stepGameClient(chosen, { at, kind: "tick" }).state;
        expect(expired.calls).toBeNull();
        const confirmed = stepGameClient(expired, {
            ...scenario.steps[scenarioStateIndex(scenario, "chi chosen")].event,
            at,
        }).state;
        expect(confirmed.sync.kind).toBe("in_step");
        expect(confirmed.table.players[1].melds).toHaveLength(1);
        expect(confirmed.calls).toBeNull();
        expect(soundCues(expired, confirmed)).toEqual([]);
    });

    it("announces another claimant's ron and shows both winners when the server resolves a double ron", () => {
        expect(cuesAfter("double_ron_seat_1", "ron chosen", "round end")).toEqual(["ron"]);
        const display = playDisplay(checkpointState("double_ron_seat_1", "round end"), NO_PLAY_UI);
        expect(display.callouts?.items.map(({ kind, position }) => [kind, position])).toEqual([
            ["ron", "bottom"],
            ["ron", "top"],
        ]);
    });

    it("replaces a local pon declaration with the server's ron result without ever forming the pon", () => {
        const before = checkpointState("call_prompt_seat_1", "prompt");
        const offer = decisionOf(before)?.offers.find((candidate) => candidate.kind === "pon");
        assert(offer !== undefined);
        const declared = stepGameClient(before, {
            at: before.now,
            intent: { offer, type: "choose" },
            kind: "intent",
        }).state;
        const { transcript } = loadSeatScenario("double_ron_seat_1");
        const result = receivedPayload(transcript, "round end");
        const winner = wirePayloadList(result, "wn").find((candidate) => candidate.ws === 3);
        assert(winner !== undefined);
        const resolved = stepGameClient(declared, {
            at: declared.now + 500,
            kind: "server_message",
            raw: { ...result, ...winner, rt: ROUND_RESULT_TYPE.RON },
        }).state;
        expect({
            calls: resolved.calls?.calls,
            melds: resolved.table.players[1].melds,
            phase: resolved.table.phase,
            sounds: soundCues(declared, resolved),
            sync: resolved.sync.kind,
        }).toEqual({
            calls: [{ kind: "ron", seat: 3 }],
            melds: [],
            phase: "round_ended",
            sounds: ["ron"],
            sync: "in_step",
        });
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
