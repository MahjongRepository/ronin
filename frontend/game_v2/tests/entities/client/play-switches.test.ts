import { describe, expect, it } from "vitest";

import {
    type GeneratedScenario,
    answeredBySwitch,
    branchAfter,
    expecting,
    insertedAfter,
    loadSeatScenario,
    receivedPayload,
    switchedOnBefore,
} from "#tests/fixtures/seat-transcripts";
import { wireRuleRefusal } from "#tests/fixtures/wire";
import {
    type ClientEffect,
    type GameClientState,
    NO_PLAY_UI,
    type ScenarioRun,
    type ScenarioStep,
    type SeatScenario,
    playDisplay,
    runSeatScenario,
    scenarioStateIndex,
    timelineStates,
} from "@/entities/client";
import {
    type ClientMessage,
    NUM_TILES,
    buildDiscardAction,
    buildPassAction,
} from "@/shared/protocol";

const ALL_OFF = { auto_discard: false, auto_win: false, no_calls: false };

function runClean(scenario: SeatScenario): ScenarioRun {
    const run = runSeatScenario(scenario);
    expect(run.mismatches).toEqual([]);
    return run;
}

function stateAt(scenario: SeatScenario, run: ScenarioRun, label: string): GameClientState {
    return timelineStates(run.timeline)[scenarioStateIndex(scenario, label)];
}

function stepAt(scenario: SeatScenario, label: string): ScenarioStep["event"] {
    return scenario.steps[scenarioStateIndex(scenario, label) - 1].event;
}

function stepEffects(scenario: SeatScenario, label: string): readonly ClientEffect[] {
    return scenario.steps[scenarioStateIndex(scenario, label) - 1].effects ?? [];
}

/**
 * The generated drop, reopen and snapshot of a transcript's reconnect, played again after the step labelled `label`,
 * the snapshot naming the wait `waitId`: a second drop that missed what came between.
 */
function rejoinedAfter(
    { scenario, transcript }: GeneratedScenario,
    label: string,
    waitId: unknown,
): readonly ScenarioStep[] {
    const shift = stepAt(scenario, label).at - stepAt(scenario, "dropped").at;
    const rejoining = scenario.steps
        .slice(
            scenarioStateIndex(scenario, "dropped") - 1,
            scenarioStateIndex(scenario, "reopened"),
        )
        .map(({ effects, event }) => ({ effects, event: { ...event, at: event.at + shift } }));
    const at = stepAt(scenario, "reconnected").at + shift;
    const snapshot = { ...receivedPayload(transcript, "reconnected"), wi: waitId };
    return [...rejoining, { event: { at, kind: "server_message", raw: snapshot } }];
}

function lastState(run: ScenarioRun): GameClientState {
    return timelineStates(run.timeline).at(-1) ?? run.timeline.start;
}

/**
 * A branch of `switched` (a generated scenario with switches turned on) that drops after the step labelled `label`
 * and reconnects as `generated` later does, from its drop through its snapshot: the drop missing what came between.
 */
function droppedAfter(
    switched: SeatScenario,
    generated: SeatScenario,
    label: string,
): SeatScenario {
    const reconnecting = generated.steps.slice(
        scenarioStateIndex(generated, "dropped") - 1,
        scenarioStateIndex(generated, "reconnected"),
    );
    const kept = switched.steps.slice(0, scenarioStateIndex(switched, label));
    return { ...switched, steps: [...kept, ...reconnecting] };
}

function bySwitch(state: GameClientState): unknown {
    const status = state.decision?.status;
    return status?.kind === "submitted" ? status.bySwitch : status?.kind;
}

function sent(message: ClientMessage): ClientEffect {
    return { message, type: "send" };
}

/** The discard of the tile a draw's payload drew, on its wait: what Auto discard sends, written by hand. */
function drawnDiscard(draw: Readonly<Record<string, unknown>>): ClientEffect {
    return sent(buildDiscardAction(Number(draw.d) % NUM_TILES, Number(draw.wi)));
}

/** The pass of the prompt a payload carries, on its wait: what No calls sends, written by hand. */
function promptPass(prompt: Readonly<Record<string, unknown>>): ClientEffect {
    return sent(buildPassAction(Number(prompt.wi)));
}

describe("switchAnswer", () => {
    it("Auto win takes the tsumo at its draw over Auto discard, leaving the prompt open when turned on; the press after sends nothing", () => {
        const { scenario } = loadSeatScenario("own_turn_seat_1");
        const switched = answeredBySwitch(
            switchedOnBefore(scenario, "passed", ["auto_win", "auto_discard"]),
            "tsumo draw",
            "tsumo chosen",
        );
        const run = runClean(switched);

        expect(bySwitch(stateAt(switched, run, "passed"))).toBeNull();
        expect(bySwitch(stateAt(switched, run, "tsumo draw"))).toBe("auto_win");
        expect(stateAt(switched, run, "tsumo chosen").decision?.status).toEqual(
            stateAt(switched, run, "tsumo draw").decision?.status,
        );
    });

    it("Auto win takes a chankan prompt's ron at once, which No calls never passes", () => {
        const { scenario } = loadSeatScenario("chankan_robbed_seat_3");
        const switched = answeredBySwitch(
            switchedOnBefore(scenario, "chankan prompt", ["auto_win", "no_calls"]),
            "chankan prompt",
            "ron chosen",
        );
        const run = runClean(switched);

        expect(bySwitch(stateAt(switched, run, "chankan prompt"))).toBe("auto_win");
    });

    it("No calls passes a prompt of open kan, pon and chi before its controls show", () => {
        const { scenario, transcript } = loadSeatScenario("call_prompt_seat_1");
        const pass = promptPass(receivedPayload(transcript, "prompt"));
        const switched = switchedOnBefore(scenario, "prompt", ["no_calls"]);
        const passed = branchAfter(expecting(switched, "prompt", [pass]), "prompt", []);
        const prompt = stateAt(passed, runClean(passed), "prompt");
        const display = playDisplay(prompt, NO_PLAY_UI);

        expect(bySwitch(prompt)).toBe("no_calls");
        expect([display.actions, display.decisionStanding]).toEqual([[], null]);
    });

    it("No calls and Auto discard leave riichi, a closed kan, a ron and a tsumo to the player, kept through a reconnect and off at the deal", () => {
        const { scenario } = loadSeatScenario("own_turn_seat_1");
        const switched = switchedOnBefore(scenario, "first draw", ["no_calls", "auto_discard"]);
        const run = runClean(switched);
        const on = { ...ALL_OFF, auto_discard: true, no_calls: true };

        expect(stateAt(switched, run, "draw re-sent").switches).toEqual(on);
        expect(stateAt(switched, run, "round end").switches).toEqual(on);
        expect(stateAt(switched, run, "next round").switches).toEqual(ALL_OFF);
    });

    it("leaves a kyuushu offer to the player with every switch on", () => {
        const { scenario } = loadSeatScenario("game_end_reconnect_seat_1");
        const switched = switchedOnBefore(scenario, "first draw", [
            "auto_win",
            "no_calls",
            "auto_discard",
        ]);

        const run = runClean(switched);

        expect(bySwitch(stateAt(switched, run, "kyuushu chosen"))).toBeNull();
    });

    it("Auto discard discards a plain draw's tile, never on the turn after the viewer's chi", () => {
        const { scenario, transcript } = loadSeatScenario("call_prompt_seat_1");
        const discard = drawnDiscard(receivedPayload(transcript, "next turn"));
        const switchedOn = switchedOnBefore(scenario, "prompt", ["auto_discard"]);
        const switched = expecting(switchedOn, "next turn", [discard]);
        const run = runClean(switched);

        expect(bySwitch(stateAt(switched, run, "discarded"))).toBeNull();
        expect(bySwitch(stateAt(switched, run, "next turn"))).toBe("auto_discard");
    });

    it("Auto discard discards a plain draw in riichi, which the board never discards on its own", () => {
        const { scenario, transcript } = loadSeatScenario("own_turn_seat_1");
        const { aa: _offers, ...plain } = receivedPayload(transcript, "tsumo draw");
        const plainDraw = { event: { at: 13_000, kind: "server_message", raw: plain } } as const;
        const unswitched = branchAfter(scenario, "furiten", [{ ...plainDraw, label: "plain" }]);
        const switchedOn = switchedOnBefore(scenario, "furiten", ["auto_discard"]);
        const switched = branchAfter(switchedOn, "furiten", [
            { ...plainDraw, effects: [drawnDiscard(plain)], label: "plain" },
        ]);
        const unswitchedRun = runClean(unswitched);
        const switchedRun = runClean(switched);

        expect(bySwitch(stateAt(unswitched, unswitchedRun, "plain"))).toBe("open");
        expect(bySwitch(stateAt(switched, switchedRun, "plain"))).toBe("auto_discard");
    });
});

describe("stepGameClient - play switches", () => {
    it("never answers a wait re-sent after a reconnect, seen with the switch on or off, and No calls stays on through it", () => {
        const { scenario, transcript } = loadSeatScenario("reconnect_seat_1");
        const pass = promptPass(receivedPayload(transcript, "prompt"));
        const switched = expecting(switchedOnBefore(scenario, "prompt", ["no_calls"]), "prompt", [
            pass,
        ]);
        const switchedLate = switchedOnBefore(scenario, "dropped", ["no_calls"]);
        const run = runClean(switched);
        const resent = stateAt(switched, run, "prompt re-sent");
        const resentLate = stateAt(switchedLate, runClean(switchedLate), "prompt re-sent");

        expect(bySwitch(stateAt(switched, run, "prompt"))).toBe("no_calls");
        expect([bySwitch(resent), bySwitch(resentLate), resent.switches.no_calls]).toEqual([
            "open",
            "open",
            true,
        ]);
        expect(playDisplay(resent, NO_PLAY_UI).decisionStanding).toBe("open");
    });

    it("answers a wait first seen on the reconnect, its first sending lost to the drop", () => {
        const { scenario, transcript } = loadSeatScenario("reconnect_seat_1");
        const pass = promptPass(receivedPayload(transcript, "prompt re-sent"));
        const switched = switchedOnBefore(scenario, "prompt", ["no_calls"]);
        const lost = switched.steps.toSpliced(scenarioStateIndex(switched, "prompt") - 1, 1);
        const missed = expecting({ ...switched, steps: lost }, "prompt re-sent", [pass]);
        const branch = branchAfter(missed, "prompt re-sent", []);
        const run = runClean(branch);

        expect(bySwitch(stateAt(branch, run, "prompt re-sent"))).toBe("no_calls");
    });

    it("answers a new wait first seen on a later reconnect whose snapshot names it", () => {
        const generated = loadSeatScenario("reconnect_seat_1");
        const { scenario, transcript } = generated;
        const switchedOn = switchedOnBefore(scenario, "prompt", ["no_calls", "auto_win"]);
        const passed = expecting(switchedOn, "prompt", [
            promptPass(receivedPayload(transcript, "prompt")),
        ]);
        const ronPrompt = receivedPayload(transcript, "ron prompt");
        const rejoined = rejoinedAfter(generated, "discarded", ronPrompt.wi);
        const missed = branchAfter(passed, "discarded", [
            ...rejoined,
            {
                effects: stepEffects(scenario, "ron chosen"),
                event: {
                    at: rejoined.at(-1)?.event.at ?? 0,
                    kind: "server_message",
                    raw: ronPrompt,
                },
                label: "ron prompt",
            },
        ]);
        const run = runClean(missed);

        expect(bySwitch(stateAt(missed, run, "ron prompt"))).toBe("auto_win");
    });

    it("never answers again a decision the server's refusal reopened", () => {
        const { scenario, transcript } = loadSeatScenario("anchor_seat_1");
        const ownTurn = receivedPayload(transcript, "own turn");
        const discard = drawnDiscard(ownTurn);
        const switchedOn = switchedOnBefore(scenario, "own turn", ["auto_discard"]);
        const refusal = {
            at: 20_200,
            kind: "server_message",
            raw: wireRuleRefusal(Number(ownTurn.wi)),
        } as const;
        const switched = insertedAfter(expecting(switchedOn, "own turn", [discard]), "own turn", [
            { event: refusal, label: "refused" },
        ]);
        const run = runClean(switched);

        expect(bySwitch(stateAt(switched, run, "own turn"))).toBe("auto_discard");
        expect(bySwitch(stateAt(switched, run, "refused"))).toBe("open");
        expect(bySwitch(stateAt(switched, run, "discarded"))).toBeNull();
    });

    it("No calls leaves a prompt offering ron and chi to the player", () => {
        const { scenario } = loadSeatScenario("double_ron_seat_1");
        const switched = switchedOnBefore(scenario, "ron prompt", ["no_calls"]);
        const run = runClean(switched);

        expect(bySwitch(stateAt(switched, run, "ron chosen"))).toBeNull();
    });

    it("turns the switches off on a reconnect's snapshot of a round result pending, and offers none between hands", () => {
        const { scenario } = loadSeatScenario("double_ron_seat_1");
        const switched = switchedOnBefore(scenario, "ron chosen", ["auto_win", "no_calls"]);
        const droppedInHand = droppedAfter(switched, scenario, "ron chosen");
        const run = runClean(switched);
        const roundEnd = stateAt(switched, run, "round end");

        expect(roundEnd.switches).toEqual({ ...ALL_OFF, auto_win: true, no_calls: true });
        expect(playDisplay(roundEnd, NO_PLAY_UI).switches).toEqual([]);
        expect(stateAt(switched, run, "reconnected").switches).toEqual(ALL_OFF);
        expect(lastState(runClean(droppedInHand)).switches).toEqual(ALL_OFF);
    });

    it("turns the switches off on a reconnect's snapshot of the next hand, the drop having missed its deal", () => {
        const { scenario } = loadSeatScenario("game_end_reconnect_seat_1");
        const switched = switchedOnBefore(scenario, "kyuushu chosen", ["auto_win"]);
        const inHand = droppedAfter(switched, scenario, "kyuushu chosen");
        const atResult = droppedAfter(switched, scenario, "kyuushu round end");
        const atResultRun = runClean(atResult);

        expect(stateAt(atResult, atResultRun, "kyuushu round end").switches.auto_win).toBe(true);
        expect(stateAt(atResult, atResultRun, "reconnected").switches).toEqual(ALL_OFF);
        expect(lastState(runClean(inHand)).switches).toEqual(ALL_OFF);
    });
});
