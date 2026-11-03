import { describe, expect, expectTypeOf, it } from "vitest";

import {
    type GeneratedScenario,
    answeredBySwitch,
    branchAfter,
    checkpointState,
    expecting,
    insertedAfter,
    loadSeatScenario,
    receivedPayload,
    switchedOnBefore,
} from "#tests/fixtures/seat-transcripts";
import { wireRoundEnd, wireRuleRefusal } from "#tests/fixtures/wire";
import {
    type ClientEffect,
    type LiveClient,
    NO_PLAY_UI,
    type ReplayClient,
    type ScenarioRun,
    type ScenarioStep,
    type SeatScenario,
    decisionOf,
    desyncOf,
    playDisplay,
    roundConfirmOf,
    runSeatScenario,
    scenarioStateIndex,
    soundCues,
    stepGameClient,
    takesIntent,
    timelineStates,
} from "@/entities/client";
import {
    type ClientMessage,
    EVENT_TYPE,
    NUM_TILES,
    PLAYER_ACTION,
    buildDiscardAction,
    buildPassAction,
    buildResyncMessage,
} from "@/shared/protocol";

const ALL_OFF = { auto_discard: false, auto_win: false, no_calls: false };

function runClean(scenario: SeatScenario): ScenarioRun {
    const run = runSeatScenario(scenario);
    expect(run.mismatches).toEqual([]);
    return run;
}

function stateAt(scenario: SeatScenario, run: ScenarioRun, label: string): LiveClient {
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

function lastState(run: ScenarioRun): LiveClient {
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

function bySwitch(state: LiveClient): unknown {
    const status = decisionOf(state)?.status;
    return status?.kind === "submitted" ? status.bySwitch : status?.kind;
}

function sent(message: ClientMessage): ClientEffect {
    return { message, type: "send" };
}

function received(at: number, raw: Record<string, unknown>, label: string): ScenarioStep {
    return { event: { at, kind: "server_message", raw }, label };
}

/**
 * The reconnect with No calls on, where the reopened socket gets a prompt on a wait it never saw and a round end before
 * the snapshot admits it; then the snapshot of that wait, No calls turned on again (the round end's table left the
 * hand), the prompt re-sent, the player's pass, and the snapshot and prompt repeated once more.
 */
function earlyWaitBranch(): { readonly early: SeatScenario; readonly waitId: number } {
    const { scenario, transcript } = loadSeatScenario("reconnect_seat_1");
    const prompt = receivedPayload(transcript, "prompt re-sent");
    const waitId = Number(prompt.wi) + 1;
    const unseen = { ...prompt, wi: waitId };
    const snapshot = { ...receivedPayload(transcript, "reconnected"), wi: waitId };
    const noCalls = { playSwitch: "no_calls", type: "toggle_switch" } as const;
    const early = branchAfter(switchedOnBefore(scenario, "dropped", ["no_calls"]), "reopened", [
        received(5500, unseen, "early prompt"),
        received(5500, wireRoundEnd(waitId + 1), "early round end"),
        received(5500, snapshot, "admitted"),
        { event: { at: 5500, intent: noCalls, kind: "intent" } },
        received(5500, unseen, "prompt re-sent"),
        {
            effects: [sent(buildPassAction(waitId))],
            event: { at: 6000, intent: { type: "pass" }, kind: "intent" },
        },
        received(6100, snapshot, "snapshot again"),
        received(6100, unseen, "prompt again"),
    ]);
    return { early, waitId };
}

/** The discard of the tile a draw's payload drew, on its wait: what Auto discard sends, written by hand. */
function drawnDiscard(draw: Readonly<Record<string, unknown>>): ClientEffect {
    return sent(buildDiscardAction(Number(draw.d) % NUM_TILES, Number(draw.wi)));
}

/** The pass of the prompt a payload carries, on its wait: what No calls sends, written by hand. */
function promptPass(prompt: Readonly<Record<string, unknown>>): ClientEffect {
    return sent(buildPassAction(Number(prompt.wi)));
}

describe("automatic answers", () => {
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
        expect(decisionOf(stateAt(switched, run, "tsumo chosen"))?.status).toEqual(
            decisionOf(stateAt(switched, run, "tsumo draw"))?.status,
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
        const states = timelineStates(run.timeline);
        const index = scenarioStateIndex(switched, "chankan prompt");
        expect(soundCues(states[index - 1], states[index])).toEqual(["kan", "ron"]);
    });

    it("No calls passes a prompt of open kan, pon and chi before its controls show", () => {
        const { scenario, transcript } = loadSeatScenario("call_prompt_seat_1");
        const pass = promptPass(receivedPayload(transcript, "prompt"));
        const switched = switchedOnBefore(scenario, "prompt", ["no_calls"]);
        const passed = branchAfter(expecting(switched, "prompt", [pass]), "prompt", []);
        const run = runClean(passed);
        const prompt = stateAt(passed, run, "prompt");
        const display = playDisplay(prompt, NO_PLAY_UI);

        expect(bySwitch(prompt)).toBe("no_calls");
        expect([display.actions, display.decisionStanding]).toEqual([[], null]);
        expect(
            soundCues(
                timelineStates(run.timeline)[scenarioStateIndex(passed, "prompt") - 1],
                prompt,
            ),
        ).toEqual([]);
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

    it("discards a plain draw in riichi with every switch off, once even if the draw is repeated", () => {
        const { scenario, transcript } = loadSeatScenario("own_turn_seat_1");
        const { aa: _offers, ...plain } = receivedPayload(transcript, "tsumo draw");
        const refusal = wireRuleRefusal(Number(plain.wi));
        const unswitched = branchAfter(scenario, "furiten", [
            { ...received(13_000, plain, "plain"), effects: [drawnDiscard(plain)] },
            received(13_000, plain, "repeated"),
            received(13_001, refusal, "refused"),
        ]);
        const unswitchedRun = runClean(unswitched);
        const submitted = stateAt(unswitched, unswitchedRun, "plain");
        const display = playDisplay(submitted, NO_PLAY_UI);
        expect([
            bySwitch(submitted),
            submitted.switches,
            display.actions,
            display.countdown,
        ]).toEqual([null, ALL_OFF, [], null]);
        expect(decisionOf(stateAt(unswitched, unswitchedRun, "repeated"))).toEqual(
            decisionOf(submitted),
        );
        expect(bySwitch(stateAt(unswitched, unswitchedRun, "refused"))).toBe("open");
    });

    it("leaves a post-riichi kan and its replacement draw's tsumo to the player", () => {
        const { scenario } = loadSeatScenario("riichi_kan_seat_1");
        const run = runClean(scenario);
        const offered = stateAt(scenario, run, "kan offer");
        const display = playDisplay(offered, NO_PLAY_UI);

        expect(
            offered.table.players.find((player) => player.seat === offered.viewerSeat)?.isRiichi,
        ).toBe(true);
        expect([
            bySwitch(offered),
            display.actions.map((action) => action.label),
            display.tileIntents.size,
        ]).toEqual(["open", ["Kan"], 1]);
        expect(display.board?.players[0].hand.map((tile) => tile.state)).toEqual(
            Array(13).fill("waiting"),
        );
        const replacement = stateAt(scenario, run, "tsumo draw");
        expect(bySwitch(replacement)).toBe("open");
        expect(playDisplay(replacement, NO_PLAY_UI).actions.map((action) => action.label)).toEqual([
            "Tsumo",
        ]);
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

    it("never answers a new wait while the client cannot send: a prompt or round end before the snapshot admits the reconnect is owed by no one, and the prompt re-sent after it is the player's to answer, once", () => {
        const { early, waitId } = earlyWaitBranch();
        const run = runClean(early);
        const before = stateAt(early, run, "early prompt");
        const roundEnd = stateAt(early, run, "early round end");
        const resent = stateAt(early, run, "prompt re-sent");

        expect(before.session).toMatchObject({
            identity: { kind: "reconnect" },
            status: "identifying",
        });
        expect([before.switches.no_calls, before.highestOpenedWaitId, decisionOf(before)]).toEqual([
            true,
            waitId,
            null,
        ]);
        expect([roundEnd.session.status, roundEnd.table.phase, roundConfirmOf(roundEnd)]).toEqual([
            "identifying",
            "round_ended",
            null,
        ]);
        expect([resent.switches.no_calls, bySwitch(resent)]).toEqual([true, "open"]);
        expect(decisionOf(stateAt(early, run, "prompt again"))?.status).toMatchObject({
            bySwitch: null,
            intent: { type: "pass" },
            kind: "submitted",
        });
    });

    it("takes a play switch only on a live seat: never once the session ended, nor on a replay's board", () => {
        const toggle = {
            at: 4000,
            intent: { playSwitch: "auto_win", type: "toggle_switch" },
            kind: "intent",
        } as const;
        const ended = stepGameClient(checkpointState("own_turn_seat_1", "first draw"), {
            at: 3900,
            code: 4002,
            kind: "transport_closed",
            reason: "",
        }).state;

        expect([ended.session.status, ended.table.phase]).toEqual(["ended", "in_round"]);
        expect([takesIntent(ended, toggle.intent), stepGameClient(ended, toggle)]).toEqual([
            false,
            { effects: [], state: { ...ended, now: 4000 } },
        ]);
        expectTypeOf<ReplayClient>().not.toExtend<Parameters<typeof takesIntent>[0]>();
        expectTypeOf<ReplayClient>().not.toExtend<Parameters<typeof stepGameClient>[0]>();
    });

    it.each([
        { aa: [{ a: 999 }], name: "an action code it does not know" },
        { aa: [{ a: PLAYER_ACTION.RIICHI }], name: "a riichi with no discard" },
        { aa: [{ a: PLAYER_ACTION.KAN }], name: "a kan with no tile type" },
        { aa: [{ a: PLAYER_ACTION.RIICHI, tl: [] }], name: "a riichi with an empty discard list" },
    ])("Auto discard never answers a draw offering $name, a loss of step instead", ({ aa }) => {
        const turn = checkpointState("own_turn_seat_1", "first draw");
        const seat = turn.viewerSeat ?? 0;
        const [drawnTile] = turn.table.players[seat].tiles;
        const switchedOn = stepGameClient(turn, {
            at: 3100,
            intent: { playSwitch: "auto_discard", type: "toggle_switch" },
            kind: "intent",
        }).state;
        function drawOffering(offers: unknown): ReturnType<typeof stepGameClient> {
            return stepGameClient(switchedOn, {
                at: 3200,
                kind: "server_message",
                raw: {
                    aa: offers,
                    bk: 30,
                    d: seat * NUM_TILES + drawnTile,
                    t: EVENT_TYPE.DRAW,
                    tr: 69,
                    wi: 999,
                },
            });
        }

        const unreadable = drawOffering(aa);
        expect(drawOffering([]).effects).toEqual([sent(buildDiscardAction(drawnTile, 999))]);
        expect(unreadable.effects.map((effect) => effect.type)).toEqual([
            "report_protocol_failure",
            "send",
        ]);
        expect(unreadable.effects[1]).toEqual(sent(buildResyncMessage()));
        expect([decisionOf(unreadable.state), desyncOf(unreadable.state)?.cause]).toEqual([
            null,
            "unreadable_message",
        ]);
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
