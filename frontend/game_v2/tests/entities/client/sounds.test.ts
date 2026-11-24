import { assert, describe, expect, it } from "vitest";

import {
    checkpointState,
    loadSeatScenario,
    receivedPayload,
} from "#tests/fixtures/seat-transcripts";
import { wirePayloadList, wireRuleRefusal } from "#tests/fixtures/wire";
import {
    type LiveClient,
    NO_PLAY_UI,
    type SoundCue,
    decisionOf,
    playDisplay,
    runSeatScenario,
    scenarioStateIndex,
    soundCues,
    stepGameClient,
    timelineStates,
} from "@/entities/client";
import { CALLOUT_MS } from "@/entities/table";
import { EVENT_TYPE, WIRE_KEY } from "@/shared/protocol";

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
        ["call_prompt_seat_1", "prompt", ["decision"]],
        ["own_turn_seat_1", "first draw", ["draw", "decision"]],
        ["first_turn_win_seat_1", "tenhou draw", ["decision"]],
        ["double_ron_seat_1", "ron prompt", ["decision"]],
        ["call_prompt_seat_1", "turn", []],
        ["own_turn_seat_1", "rinshan", ["draw", "decision"]],
        ["game_end_reconnect_seat_1", "first draw", ["draw"]],
    ] as const)(
        "chimes only for a new call, riichi or win offer at %s / %s",
        (name, label, expected) => {
            const { scenario } = loadSeatScenario(name);
            const run = runSeatScenario(scenario);
            expect(run.mismatches).toEqual([]);
            const states = timelineStates(run.timeline);
            const index = scenarioStateIndex(scenario, label);
            const opened = states[index];
            expect(decisionOf(opened)?.status.kind).toBe("open");
            expect(soundCues(states[index - 1], opened)).toEqual(expected);

            const ticked = stepGameClient(opened, { at: opened.now + 50, kind: "tick" }).state;
            expect(soundCues(opened, ticked)).toEqual([]);
        },
    );

    it("does not chime again for a repeated prompt or a refused answer reopening it", () => {
        const opened = checkpointState("call_prompt_seat_1", "prompt");
        const repeated = stepGameClient(opened, {
            at: opened.now,
            kind: "server_message",
            raw: receivedPayload(loadSeatScenario("call_prompt_seat_1").transcript, "prompt"),
        }).state;
        expect(decisionOf(repeated)?.status.kind).toBe("open");
        expect(soundCues(opened, repeated)).toEqual([]);

        const chosen = checkpointState("first_turn_win_seat_1", "tsumo chosen");
        const decision = decisionOf(chosen);
        assert(decision?.status.kind === "submitted");
        const refused = stepGameClient(chosen, {
            at: chosen.now,
            kind: "server_message",
            raw: wireRuleRefusal(decision.waitId),
        }).state;
        expect(decisionOf(refused)?.status.kind).toBe("open");
        expect([refused.calls, soundCues(chosen, refused)]).toEqual([null, []]);
    });

    it.each([
        ["call_prompt_seat_1", "prompt", "chi"],
        ["call_prompt_seat_1", "prompt", "pon"],
        ["call_prompt_seat_1", "prompt", "kan"],
        ["riichi_reconnect_seat_1", "ron prompt re-sent", "ron"],
        ["own_turn_seat_1", "first draw", "kan"],
        ["added_kan_seat_1", "kan offer", "kan"],
        ["own_turn_seat_1", "first draw", "riichi"],
        ["first_turn_win_seat_1", "tenhou draw", "tsumo"],
    ] as const)(
        "submits %s / %s / %s once and waits silently for the server",
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
                calls: display.callouts,
                countdown: display.countdown,
                decision: display.decisionStanding,
                sends: declared.effects.length,
                sounds: soundCues(before, declared.state),
            }).toEqual({
                actions: [],
                calls: playDisplay(before, NO_PLAY_UI).callouts,
                countdown: null,
                decision: null,
                sends: 1,
                sounds: [],
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
        ]).toEqual([["discard", "riichi"], [], ["ron"]]);
    });

    it("ticks for an opponent's draw after the discard it follows, but not for the round's opening draw, a reconnect's snapshot or its re-sent draw", () => {
        const scenario = "call_prompt_seat_1";

        expect([
            cuesAfter(scenario, "dealt", "prompt"),
            cuesAfter(scenario, "discarded", "seat 2 drew"),
            cuesAfter(scenario, "dropped", "turn re-sent"),
        ]).toEqual([["discard", "decision"], ["discard", "draw"], []]);
    });

    it("voices tsumo and plays the yakuman gong together on confirmation", () => {
        expect(cuesAfter("first_turn_win_seat_1", "tenhou draw", "tsumo chosen")).toEqual([]);
        expect(cuesAfter("first_turn_win_seat_1", "tsumo chosen", "round end")).toEqual([
            "tsumo",
            "yakuman",
        ]);
    });

    it("restores a missed discard from a reconnect snapshot silently", () => {
        const { transcript } = loadSeatScenario("call_prompt_seat_1");
        const before = checkpointState("call_prompt_seat_1", "dealt");
        const after = stepGameClient(before, {
            at: before.now + 7000,
            kind: "server_message",
            raw: receivedPayload(transcript, "reconnected"),
        }).state;
        expect(after.table.players[0].discards).toHaveLength(1);
        expect(after.table.players[1].melds).toHaveLength(1);
        expect(soundCues(before, after)).toEqual([]);
    });

    it("announces a confirmed chi even after a long wait for the meld", () => {
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
        expect(confirmed.calls?.calls).toEqual([{ kind: "chi", seat: 1 }]);
        expect(soundCues(expired, confirmed)).toEqual(["chi"]);
    });
});

describe("contested calls", () => {
    it("announces double ron once and shows both winners together at resolution", () => {
        expect(checkpointState("double_ron_seat_1", "ron chosen").calls).toBeNull();
        expect(cuesAfter("double_ron_seat_1", "ron prompt", "ron chosen")).toEqual([]);
        expect(cuesAfter("double_ron_seat_1", "ron chosen", "round end")).toEqual(["ron"]);
        const display = playDisplay(checkpointState("double_ron_seat_1", "round end"), NO_PLAY_UI);
        expect(display.callouts?.items.map(({ kind, position }) => [kind, position])).toEqual([
            ["ron", "bottom"],
            ["ron", "top"],
        ]);
    });

    it("shows only the paid winner when head bump settles competing rons", () => {
        const name = "double_ron_seat_1";
        const result = receivedPayload(loadSeatScenario(name).transcript, "round end");
        const [winner] = wirePayloadList(result, WIRE_KEY.WINNERS);
        expect(winner[WIRE_KEY.WINNER_SEAT]).toBe(1);
        const before = checkpointState(name, "ron chosen");
        const after = stepGameClient(before, {
            at: before.now + 500,
            kind: "server_message",
            raw: {
                ...result,
                [WIRE_KEY.HEAD_BUMPED_SEATS]: [3],
                [WIRE_KEY.SCORE_CHANGES]: winner[WIRE_KEY.SCORE_CHANGES],
                [WIRE_KEY.WINNERS]: [winner],
            },
        }).state;
        expect(after.table.roundEndResult?.headBumpedSeats).toEqual([3]);
        expect(after.calls?.calls).toEqual([{ kind: "ron", seat: 1 }]);
        expect(soundCues(before, after)).toEqual(["ron"]);
    });

    it("announces only the other seat's pon when it outranks the submitted chi", () => {
        const before = checkpointState("chi_prompt_seat_1", "prompt");
        const offer = decisionOf(before)?.offers.find((candidate) => candidate.kind === "chi");
        assert(offer !== undefined);
        const submitted = stepGameClient(before, {
            at: before.now,
            intent: { offer, type: "choose" },
            kind: "intent",
        }).state;
        expect([submitted.calls, soundCues(before, submitted)]).toEqual([null, []]);

        const seatTwoPonOnThreeMan = 16_530;
        const resolved = stepGameClient(submitted, {
            at: submitted.now + 500,
            kind: "server_message",
            raw: {
                [WIRE_KEY.EVENT_TYPE]: EVENT_TYPE.MELD,
                [WIRE_KEY.PACKED_MELD]: seatTwoPonOnThreeMan,
            },
        }).state;
        expect(resolved).toMatchObject({
            calls: { calls: [{ kind: "pon", seat: 2 }] },
            sync: { kind: "in_step" },
        });
        expect(resolved.table.players[1].melds).toEqual([]);
        expect(soundCues(submitted, resolved)).toEqual(["pon"]);
    });

    it("announces the winning ron when it takes priority over the submitted pon", () => {
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
        const winner = wirePayloadList(result, WIRE_KEY.WINNERS).find(
            (candidate) => candidate[WIRE_KEY.WINNER_SEAT] === 3,
        );
        assert(winner !== undefined);
        const resolved = stepGameClient(declared, {
            at: declared.now + 500,
            kind: "server_message",
            raw: {
                ...result,
                [WIRE_KEY.SCORE_CHANGES]: winner[WIRE_KEY.SCORE_CHANGES],
                [WIRE_KEY.WINNERS]: [winner],
            },
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
});

describe("decision countdown", () => {
    it.each([
        ["own_turn_seat_1", "first draw"],
        ["call_prompt_seat_1", "prompt"],
        ["own_turn_seat_1", "draw re-sent"],
    ])("beeps once at the base deadline and each last second for %s / %s", (name, label) => {
        const opened = checkpointState(name, label);
        const decision = decisionOf(opened);
        assert(decision?.deadline !== null && decision?.deadline !== undefined);
        expect(decision.baseDeadline).toBe(decision.deadline - 20_000);

        const cues = cuesBeforeDeadline(
            opened,
            [20_001, 20_000, 20_000, 19_999, 6000, 5000, 4500, 4000, 1000, 0],
        );
        expect(cues).toEqual([[], ["beep"], [], [], [], ["beep"], [], ["beep"], ["beep"], []]);
    });
});

describe("soundCues after bank entry", () => {
    it("does not replay the base-time beep when reconnecting after the bank started", () => {
        const { scenario } = loadSeatScenario("bank_reconnect_seat_1");
        const states = timelineStates(runSeatScenario(scenario).timeline);
        const index = scenarioStateIndex(scenario, "draw re-sent");
        const resumed = states[index];
        const decision = decisionOf(resumed);
        assert(decision?.baseDeadline !== null && decision?.baseDeadline !== undefined);
        expect(decision.baseDeadline).toBeLessThanOrEqual(resumed.now);
        expect(soundCues(states[index - 1], resumed)).toEqual([]);

        const ticked = stepGameClient(resumed, { at: resumed.now + 1000, kind: "tick" }).state;
        expect(soundCues(resumed, ticked)).toEqual([]);
    });

    it("plays only one beep when the base ends with five seconds left", () => {
        const { scenario, transcript } = loadSeatScenario("own_turn_seat_1");
        const states = timelineStates(runSeatScenario(scenario).timeline);
        const before = states[scenarioStateIndex(scenario, "first draw") - 1];
        const opened = stepGameClient(before, {
            at: before.now,
            kind: "server_message",
            raw: { ...receivedPayload(transcript, "first draw"), [WIRE_KEY.BANK_SECONDS]: 5 },
        }).state;
        expect(decisionOf(opened)?.status.kind).toBe("open");
        expect(cuesBeforeDeadline(opened, [5001, 5000, 5000, 4000])).toEqual([
            [],
            ["beep"],
            [],
            ["beep"],
        ]);
    });
});
