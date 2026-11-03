import { assert, describe, expect, it } from "vitest";

import { clientEvent, forbiddingIo } from "#tests/fixtures/scenario";
import {
    branchAfter,
    expecting,
    loadSeatScenario,
    receivedPayload,
    scenarioFromTranscript,
    switchedOnBefore,
} from "#tests/fixtures/seat-transcripts";
import {
    WIRE_SEAT_TO_AI,
    type WirePayload,
    wireGameError,
    wireRuleRefusal,
    wireSessionError,
} from "#tests/fixtures/wire";
import {
    type LiveClient,
    NO_PLAY_UI,
    type ScenarioRun,
    type ScenarioStep,
    type SeatScenario,
    decisionOf,
    desyncOf,
    nextDeadline,
    parseSeatTranscript,
    playDisplay,
    roundConfirmOf,
    runSeatScenario,
    scenarioStateIndex,
    stepGameClient,
    timelineStates,
} from "@/entities/client";
import { WIN_CALLOUT_CONTEXT_MS } from "@/entities/client/model/calls";
import { CALLOUT_MS, roundEndDisplay, tableStateToDisplayState } from "@/entities/table";
import { SEAT_TRANSCRIPTS } from "@/fixtures/seat-transcripts";
import {
    CALL_TYPE,
    CLIENT_MESSAGE_TYPE,
    EVENT_TYPE,
    GAME_ACTION,
    GAME_ERROR_CODE,
    KAN_TYPE,
    SESSION_ERROR_CODE,
    buildConfirmRoundAction,
    buildDiscardAction,
    buildJoinGameMessage,
    buildPonAction,
    buildResyncMessage,
} from "@/shared/protocol";

const ANCHOR = loadSeatScenario("anchor_seat_1");
const CALL_PROMPT = loadSeatScenario("call_prompt_seat_1");
const OWN_TURN = loadSeatScenario("own_turn_seat_1");
const RECONNECT = loadSeatScenario("reconnect_seat_1");
const RIICHI_RECONNECT = loadSeatScenario("riichi_reconnect_seat_1");
const CHANKAN_ROBBED_DECLARER = loadSeatScenario("chankan_robbed_seat_1");
const CHANKAN_ROBBED_ROBBER = loadSeatScenario("chankan_robbed_seat_3");
const CHANKAN_PASSED = loadSeatScenario("chankan_passed_seat_3");
const DOUBLE_RON = loadSeatScenario("double_ron_seat_1");
const FINAL_ROUND = loadSeatScenario("final_round_seat_1");
const FIRST_TURN_WIN_DEALER = loadSeatScenario("first_turn_win_seat_1");
const FIRST_TURN_WIN_LAST_SEAT = loadSeatScenario("first_turn_win_seat_3");
const GAME_END_RECONNECT = loadSeatScenario("game_end_reconnect_seat_1");
const RESYNC = loadSeatScenario("resync_seat_1");
const RESYNC_BEFORE_DEAL = loadSeatScenario("resync_before_deal_seat_1");
const { closed } = clientEvent;
const NINE_MAN_COPIES = [32, 33, 34, 35];
const ALICE_VIEW = { bottomSeat: 1, reveal: "bottom" } as const;

const CALLED_THREE_MAN = 8;
const HAKU = 126;
const PON_THREE_MAN = { offer: { kind: "pon", tileId: CALLED_THREE_MAN }, type: "choose" } as const;
const PON_THREE_MAN_SENT = { message: buildPonAction(CALLED_THREE_MAN, 1), type: "send" } as const;
const TICKET = "<game ticket>";

function runClean(scenario: SeatScenario): ScenarioRun {
    const run = runSeatScenario(scenario);
    expect(run.mismatches).toEqual([]);
    return run;
}

function stateAt(scenario: SeatScenario, run: ScenarioRun, label: string): LiveClient {
    return timelineStates(run.timeline)[scenarioStateIndex(scenario, label)];
}

function lastState(run: ScenarioRun): LiveClient {
    return timelineStates(run.timeline).at(-1) ?? run.timeline.start;
}

function lateError(at: number, raw: WirePayload, label: string): ScenarioStep {
    return { event: { at, kind: "server_message", raw }, label };
}

function discardAt(at: number, tileId: number): ScenarioStep["event"] {
    return { at, intent: { tileId, type: "discard" }, kind: "intent" };
}

/** The table's seats as their known tiles, concealed count, then the tile ids of their discards. */
function seatsAt(state: LiveClient): (number | number[])[][] {
    return state.table.players.map((player) => [
        player.tiles.length,
        player.concealedCount,
        player.discards.map((discard) => discard.tileId),
    ]);
}

describe("seatScenarioFromTranscript", () => {
    it("runs every generated transcript with exactly the effects the client's policy adds to it", () => {
        expect([...SEAT_TRANSCRIPTS.keys()].toSorted()).toEqual([
            "anchor_seat_1",
            "bank_reconnect_seat_1",
            "call_prompt_seat_1",
            "chankan_passed_seat_3",
            "chankan_robbed_seat_1",
            "chankan_robbed_seat_3",
            "double_ron_seat_1",
            "final_round_seat_1",
            "first_turn_win_seat_1",
            "first_turn_win_seat_3",
            "game_end_reconnect_seat_1",
            "kan_choice_seat_1",
            "own_turn_seat_1",
            "reconnect_seat_1",
            "resync_before_deal_seat_1",
            "resync_seat_1",
            "riichi_kan_seat_1",
            "riichi_reconnect_seat_1",
            "seat_left_seat_1",
            "seat_left_seat_3",
        ]);
        for (const name of SEAT_TRANSCRIPTS.keys()) {
            expect(runSeatScenario(loadSeatScenario(name).scenario).mismatches).toEqual([]);
        }
    });

    it("refuses a transcript whose sent action carries a key the client's builders never write", () => {
        const raw = {
            events: [
                {
                    at: 0,
                    kind: "sent",
                    message: { a: GAME_ACTION.PASS, t: 3, ti: 8, wi: 1 },
                },
            ],
            game_id: "g",
            scenario: "s",
            seat: 1,
        };

        expect(parseSeatTranscript(raw)[0]).toBeInstanceOf(Error);
    });

    it("reports a round confirm the client would not send: one for a round end the server waits on for nothing", () => {
        const { transcript } = OWN_TURN;
        const unawaited = transcript.events.map((event) => {
            if (event.kind !== "received" || event.label !== "round end") {
                return event;
            }
            const { at: _advanceSeconds, wi: _waitId, ...payload } = event.payload;
            return { ...event, payload };
        });
        const { scenario } = scenarioFromTranscript({ ...transcript, events: unawaited });
        const confirm = { message: buildConfirmRoundAction(5), type: "send" } as const;

        expect(runSeatScenario(scenario).mismatches).toMatchObject([
            { actual: [], expected: [confirm], kind: "effects", label: "confirmed" },
        ]);
    });

    it("expects the JOIN_GAME the transcript recorded on a reopen before the seat was admitted", () => {
        const join = { game_ticket: TICKET, t: CLIENT_MESSAGE_TYPE.JOIN_GAME };
        const [, transcript] = parseSeatTranscript({
            events: [
                { at: 0, kind: "opened" },
                { at: 0, kind: "sent", message: join },
                { at: 100, kind: "received", payload: WIRE_SEAT_TO_AI },
                { at: 200, code: 1006, kind: "closed", reason: "" },
                { at: 1200, kind: "opened", label: "reopened" },
                { at: 1200, kind: "sent", message: join },
            ],
            game_id: "g",
            scenario: "joining",
            seat: 0,
        });
        if (transcript === null) {
            throw new Error("the joining transcript does not parse");
        }
        const { scenario } = scenarioFromTranscript(transcript);
        const reopened = scenario.steps[scenarioStateIndex(scenario, "reopened") - 1];

        expect(reopened.effects).toEqual([
            { message: buildJoinGameMessage(scenario.handoff.gameTicket), type: "send" },
        ]);
        expect(
            runSeatScenario(scenario).mismatches.filter(({ kind }) => kind === "effects"),
        ).toEqual([]);
    });
});

describe("runSeatScenario", () => {
    it("reports a step whose effects part from the ones the scenario names", () => {
        const { scenario } = RECONNECT;
        const silentPon = scenario.steps.map((step): ScenarioStep =>
            step.label === "pon chosen" ? { ...step, effects: [] } : step,
        );
        const run = runSeatScenario({ ...scenario, steps: silentPon });

        expect(run.mismatches).toEqual([
            {
                actual: [{ message: buildPonAction(HAKU, 1), type: "send" }],
                expected: [],
                kind: "effects",
                label: "pon chosen",
                step: scenarioStateIndex(scenario, "pon chosen") - 1,
            },
        ]);
    });
});

describe("stepGameClient - generated call prompt", () => {
    const { scenario, transcript } = CALL_PROMPT;

    it("opens the prompt with its open kan, pon and both chis on the prompt's wait, running no IO", () => {
        const { calls, result } = forbiddingIo(() => {
            const run = runClean(scenario);
            return {
                dealt: stateAt(scenario, run, "dealt"),
                prompt: stateAt(scenario, run, "prompt"),
            };
        });
        const { dealt, prompt } = result;

        expect(calls).toEqual([0, 0, 0, 0]);
        expect(decisionOf(dealt)).toBeNull();
        expect(decisionOf(prompt)).toEqual({
            baseDeadline: 3000 + 5000,
            callType: CALL_TYPE.MELD,
            deadline: 3000 + 25_000,
            fromSeat: 0,
            kind: "call",
            offers: [
                { kanType: KAN_TYPE.OPEN, kind: "kan", tileId: CALLED_THREE_MAN },
                { kind: "pon", tileId: CALLED_THREE_MAN },
                { kind: "chi", sequence: [4, 12], tileId: CALLED_THREE_MAN },
                { kind: "chi", sequence: [0, 4], tileId: CALLED_THREE_MAN },
            ],
            openedAt: 3000,
            status: { kind: "open" },
            tileId: CALLED_THREE_MAN,
            waitId: receivedPayload(transcript, "prompt").wi,
        });
        expect(prompt.table.players[1].tiles).toEqual(receivedPayload(transcript, "dealt").mt);
        expect(seatsAt(prompt)).toEqual([
            [0, 13, [CALLED_THREE_MAN]],
            [13, 0, []],
            [0, 13, []],
            [0, 13, []],
        ]);
        expect(prompt.table.tilesRemaining).toBe(69);
        expect(nextDeadline(prompt)).toBe(28_000);
    });

    it("sends the chi once: a second choice before the meld arrives sends nothing", () => {
        const chi = {
            offer: { kind: "chi", sequence: [0, 4], tileId: CALLED_THREE_MAN },
            type: "choose",
        } as const;
        const twice = branchAfter(scenario, "chi chosen", [
            { event: { at: 5000, intent: chi, kind: "intent" }, label: "chi again" },
        ]);
        const run = runClean(twice);
        const submitted = {
            at: 5000,
            bySwitch: null,
            intent: chi,
            kind: "submitted",
        };

        expect(decisionOf(stateAt(twice, run, "chi chosen"))?.status).toEqual(submitted);
        expect(decisionOf(stateAt(twice, run, "chi again"))?.status).toEqual(submitted);
        expect(nextDeadline(stateAt(twice, run, "chi again"))).toBe(submitted.at + CALLOUT_MS);
    });

    it("opens the turn after the chi with the kuikae types the server named", () => {
        const run = runClean(scenario);
        const turn = stateAt(scenario, run, "turn");
        const turnPayload = receivedPayload(transcript, "turn");

        expect(decisionOf(turn)).toMatchObject({
            deadline: 5000 + (5 + 20) * 1000,
            kind: "turn",
            offers: [],
            opening: { kind: "after_call", kuikaeTileTypes: turnPayload.kt },
            waitId: turnPayload.wi,
        });
        expect(turn.table.players[1].melds.map((meld) => meld.tileIds)).toEqual([[0, 4, 8]]);
        expect(turn.table.players[1].tiles).toHaveLength(11);
    });

    it("drops the turn after the chi with the socket, and the turn re-sent after the takeover keeps its kuikae, no drawn tile and its deadline", () => {
        const run = runClean(scenario);
        const resent = stateAt(scenario, run, "turn re-sent");
        const resentPayload = receivedPayload(transcript, "turn re-sent");

        expect(decisionOf(stateAt(scenario, run, "dropped"))).toBeNull();
        expect(decisionOf(resent)).toMatchObject({
            deadline: 5000 + (5 + 20) * 1000,
            kind: "turn",
            offers: [],
            openedAt: 7000,
            opening: { kind: "after_call", kuikaeTileTypes: resentPayload.kt },
            status: { kind: "open" },
            waitId: receivedPayload(transcript, "turn").wi,
        });
        expect(resent.table.players[1].melds.map((meld) => meld.tileIds)).toEqual([[0, 4, 8]]);
        expect([resent.table.players[1].tiles.length, resent.table.players[1].drawnTileId]).toEqual(
            [11, null],
        );
    });

    it("keeps a decision open on an intent it does not take, sending nothing: a discard kuikae forbids or a pass on the turn, a discard on the prompt", () => {
        const pass = { at: 6100, intent: { type: "pass" }, kind: "intent" } as const;
        const kuikae = branchAfter(scenario, "turn", [
            { event: discardAt(6000, 9), label: "kuikae discard" },
            { event: pass, label: "pass" },
        ]);
        const onPrompt = branchAfter(scenario, "pon prompt", [
            { event: discardAt(12_100, 56), label: "prompt discard" },
        ]);
        const run = runClean(kuikae);
        const promptRun = runClean(onPrompt);
        const turn = decisionOf(stateAt(kuikae, run, "turn"));
        const prompt = decisionOf(stateAt(onPrompt, promptRun, "pon prompt"));

        expect([turn?.status.kind, prompt?.kind]).toEqual(["open", "call"]);
        expect([
            decisionOf(stateAt(kuikae, run, "kuikae discard")),
            decisionOf(stateAt(kuikae, run, "pass")),
            decisionOf(stateAt(onPrompt, promptRun, "prompt discard")),
        ]).toEqual([turn, turn, prompt]);
    });

    it("moves the turn, the wall and the drawer's hand on another seat's draw notice, ahead of its discard", () => {
        const { table } = stateAt(scenario, runClean(scenario), "seat 2 drew");

        expect({
            handSizes: table.players.map((player) => player.tiles.length + player.concealedCount),
            tilesRemaining: table.tilesRemaining,
            turn: table.currentPlayerSeat,
        }).toEqual({ handSizes: [13, 10, 14, 13], tilesRemaining: 68, turn: 2 });
        expect(table.players[2].discards).toEqual([]);
    });

    it("closes a prompt left open when the next seat's draw notice shows the server passed for it", () => {
        const notice = { s: 3, t: EVENT_TYPE.DRAW_NOTICE, tr: 67 };
        const passedOver = branchAfter(scenario, "pon prompt", [
            { event: { at: 13_000, kind: "server_message", raw: notice }, label: "seat 3 drew" },
        ]);
        const run = runClean(passedOver);

        expect(decisionOf(stateAt(passedOver, run, "pon prompt"))?.status.kind).toBe("open");
        expect(decisionOf(stateAt(passedOver, run, "seat 3 drew"))).toBeNull();
    });

    it("passes the pon prompt, and the next draw opens the turn with the bank the server left", () => {
        const run = runClean(scenario);
        const next = stateAt(scenario, run, "next turn");
        const drawPayload = receivedPayload(transcript, "next turn");

        expect(decisionOf(stateAt(scenario, run, "pon prompt"))).toMatchObject({
            fromSeat: 2,
            offers: [{ kind: "pon", tileId: 98 }],
        });
        expect(decisionOf(stateAt(scenario, run, "passed"))?.status.kind).toBe("submitted");
        expect(decisionOf(next)).toMatchObject({
            deadline: 14_000 + (5 + 18) * 1000,
            kind: "turn",
            opening: { drawnTileId: 72, kind: "draw" },
            waitId: drawPayload.wi,
        });
        expect(next.table.players[1].drawnTileId).toBe(72);
        expect(next.table.tilesRemaining).toBe(65);
    });

    it("keeps an expired prompt for display: a late choice still sends once, with or without a tick first", () => {
        const late = { at: 28_500, intent: PON_THREE_MAN, kind: "intent" } as const;
        const again = { at: 28_750, intent: PON_THREE_MAN, kind: "intent" } as const;
        const ticked = branchAfter(scenario, "prompt", [
            { event: { at: 27_999, kind: "tick" }, label: "just before" },
            { event: { at: 28_000, kind: "tick" }, label: "deadline" },
            { effects: [PON_THREE_MAN_SENT], event: late, label: "late" },
            { event: again },
        ]);
        const unticked = branchAfter(scenario, "prompt", [
            { effects: [PON_THREE_MAN_SENT], event: late, label: "late" },
            { event: again },
        ]);
        const tickedRun = runClean(ticked);
        const untickedRun = runClean(unticked);

        expect(decisionOf(stateAt(ticked, tickedRun, "just before"))?.status).toEqual({
            kind: "open",
        });
        expect(decisionOf(stateAt(ticked, tickedRun, "deadline"))?.status).toEqual({
            kind: "expired",
        });
        expect(nextDeadline(stateAt(ticked, tickedRun, "deadline"))).toBeNull();
        expect(decisionOf(stateAt(ticked, tickedRun, "late"))).toEqual(
            decisionOf(stateAt(unticked, untickedRun, "late")),
        );
    });
});

describe("stepGameClient - generated own turn", () => {
    const { scenario, transcript } = OWN_TURN;

    it("opens the first draw's riichi and closed-kan offers, the kan answered with a tile of its type", () => {
        const run = runClean(scenario);

        expect(decisionOf(stateAt(scenario, run, "first draw"))).toEqual({
            baseDeadline: 3000 + 5 * 1000,
            deadline: 3000 + (5 + 20) * 1000,
            kind: "turn",
            offers: [
                { kind: "riichi", tileId: 0 },
                { kind: "riichi", tileId: 1 },
                { kind: "riichi", tileId: 2 },
                { kind: "riichi", tileId: 3 },
                { kanType: KAN_TYPE.CLOSED, kind: "kan", tileId: 0 },
            ],
            openedAt: 3000,
            opening: { drawnTileId: 3, kind: "draw" },
            status: { kind: "open" },
            waitId: receivedPayload(transcript, "first draw").wi,
        });
    });

    it("drops the turn with the socket, and the draw re-sent after the takeover keeps its deadline", () => {
        const run = runClean(scenario);
        const dropped = stateAt(scenario, run, "dropped");
        const resent = stateAt(scenario, run, "draw re-sent");
        const [, alice] = resent.table.players;

        expect([decisionOf(dropped), dropped.session?.status]).toEqual([null, "awaiting_retry"]);
        expect(decisionOf(stateAt(scenario, run, "reconnected"))).toBeNull();
        expect(decisionOf(resent)).toMatchObject({
            deadline: 3000 + (5 + 20) * 1000,
            openedAt: 4500,
            status: { kind: "open" },
            waitId: receivedPayload(transcript, "draw re-sent").wi,
        });
        expect(decisionOf(resent)?.offers).toEqual(
            decisionOf(stateAt(scenario, run, "first draw"))?.offers,
        );
        expect([alice.tiles.length, alice.drawnTileId, resent.table.tilesRemaining]).toEqual([
            14, 3, 68,
        ]);
    });

    it("declares the closed kan, and the rinshan draw opens the next turn on its own wait", () => {
        const run = runClean(scenario);
        const rinshan = stateAt(scenario, run, "rinshan");
        const [, alice] = rinshan.table.players;

        expect(decisionOf(rinshan)).toMatchObject({
            offers: [{ kind: "riichi", tileId: 120 }],
            waitId: receivedPayload(transcript, "rinshan").wi,
        });
        expect(alice.melds.map((meld) => [meld.meldType, meld.tileIds])).toEqual([
            ["closed_kan", [0, 1, 2, 3]],
        ]);
        expect([alice.tiles.length, alice.drawnTileId, rinshan.table.tilesRemaining]).toEqual([
            11, 120, 67,
        ]);
    });

    it("offers only ron on a ron prompt in riichi, and passing it leaves the seat furiten", () => {
        const run = runClean(scenario);

        expect(decisionOf(stateAt(scenario, run, "ron prompt"))).toMatchObject({
            callType: CALL_TYPE.RON,
            fromSeat: 2,
            offers: [{ kind: "ron" }],
            tileId: 92,
        });
        expect(stateAt(scenario, run, "ron prompt").table.players[1].isRiichi).toBe(true);
        expect(stateAt(scenario, run, "passed").furiten).toBe(false);
        expect(stateAt(scenario, run, "furiten").furiten).toBe(true);
    });

    it("in riichi takes only the drawn tile as the turn's discard", () => {
        const riichiTurn = branchAfter(scenario, "tsumo draw", [
            { event: discardAt(14_000, 40), label: "not the drawn tile" },
            {
                effects: [{ message: buildDiscardAction(104, 4), type: "send" }],
                event: discardAt(14_250, 104),
            },
        ]);
        const run = runClean(riichiTurn);

        expect(decisionOf(stateAt(riichiTurn, run, "not the drawn tile"))).toBe(
            decisionOf(stateAt(riichiTurn, run, "tsumo draw")),
        );
    });

    it("settles the tsumo at the round end and owes its confirm, counted down, until the player presses OK", () => {
        const run = runClean(scenario);
        const roundEnd = stateAt(scenario, run, "round end");

        expect(decisionOf(stateAt(scenario, run, "tsumo draw"))?.offers).toEqual([
            { kind: "tsumo" },
        ]);
        expect(decisionOf(roundEnd)).toBeNull();
        expect(roundEnd.table.roundEndResult?.winners.map((winner) => winner.seat)).toEqual([1]);
        expect(roundEnd.table.players.map((player) => player.score)).toEqual([
            21_000, 33_000, 23_000, 23_000,
        ]);
        const waitId = receivedPayload(transcript, "round end").wi;
        expect(roundConfirmOf(roundEnd)).toEqual({
            deadline: 15_000 + 10_000,
            kind: "owed",
            waitId,
        });
        expect(roundConfirmOf(stateAt(scenario, run, "confirmed"))).toEqual({
            deadline: 25_000,
            kind: "sent",
            waitId,
        });
        expect(roundConfirmOf(stateAt(scenario, run, "next round"))).toBeNull();
    });

    it("deals the next round to the winner as dealer, furiten cleared and the bank restored to 20 seconds", () => {
        const run = runClean(scenario);
        const nextRound = stateAt(scenario, run, "next round");

        expect([nextRound.table.dealerSeat, nextRound.furiten]).toEqual([1, false]);
        expect(tableStateToDisplayState(nextRound.table, ALICE_VIEW)?.center.roundDisplay).toBe(
            "East 2",
        );
        expect(nextRound.table.players[1].tiles).toEqual(
            receivedPayload(transcript, "next round").mt,
        );
        expect(decisionOf(stateAt(scenario, run, "dealer draw"))?.deadline).toBe(
            16_000 + (5 + 20) * 1000,
        );
    });
});

/** The scenario with the payload of the step labelled `label` edited to a shape the server never sends. */
function editedAt(
    scenario: SeatScenario,
    label: string,
    edit: (raw: WirePayload) => WirePayload,
): SeatScenario {
    const steps = scenario.steps.map((step): ScenarioStep => {
        const { event } = step;
        return step.label === label && event.kind === "server_message"
            ? { ...step, event: { ...event, raw: edit(event.raw) } }
            : step;
    });
    return { ...scenario, steps };
}

function withoutKey(key: string): (raw: WirePayload) => WirePayload {
    return (raw) => Object.fromEntries(Object.entries(raw).filter(([name]) => name !== key));
}

/** What the run's step labelled `label` described, by effect type, and every message the run sent from it on. */
function effectsFrom(scenario: SeatScenario, run: ScenarioRun, label: string): unknown[] {
    const entries = run.timeline.entries.slice(scenarioStateIndex(scenario, label) - 1);
    const sent = entries.flatMap(({ effects }) =>
        effects.flatMap((effect) => (effect.type === "send" ? [effect.message] : [])),
    );
    return [entries[0]?.effects.map((effect) => effect.type), sent];
}

describe("stepGameClient - incomplete or out-of-row live messages", () => {
    const RESYNC_MESSAGE = buildResyncMessage();

    it("goes out of step on a live deal naming no hand, so Auto discard answers nothing and only snapshots are asked for", () => {
        const noHand = editedAt(ANCHOR.scenario, "east 2 dealt", withoutKey("mt"));
        const variant = switchedOnBefore(noHand, "own turn", ["auto_discard"]);
        const run = runSeatScenario(variant);
        const [dealt, sent] = effectsFrom(variant, run, "east 2 dealt");

        expect(dealt).toEqual(["report_protocol_failure", "send"]);
        expect(sent).toEqual([RESYNC_MESSAGE, RESYNC_MESSAGE]);
        expect(decisionOf(stateAt(variant, run, "own turn"))).toBeNull();
    });

    it("goes out of step on a prompt after the round end rather than let it replace the confirm, Auto win on", () => {
        const { scenario, transcript } = DOUBLE_RON;
        const { at } = scenario.steps[scenarioStateIndex(scenario, "round end") - 1].event;
        const prompt = { ...receivedPayload(transcript, "ron prompt"), wi: 999 };
        const variant = branchAfter(
            switchedOnBefore(scenario, "round end", ["auto_win"]),
            "round end",
            [{ event: { at, kind: "server_message", raw: prompt }, label: "stale prompt" }],
        );
        const run = runSeatScenario(variant);
        const prompted = stateAt(variant, run, "stale prompt");

        expect(roundConfirmOf(stateAt(variant, run, "round end"))?.kind).toBe("owed");
        expect(effectsFrom(variant, run, "stale prompt")).toEqual([
            ["report_protocol_failure", "send"],
            [RESYNC_MESSAGE],
        ]);
        expect([roundConfirmOf(prompted), desyncOf(prompted)?.cause]).toEqual([
            null,
            "impossible_state",
        ]);
    });
});

describe("stepGameClient - generated first turns", () => {
    const KYUUSHU = { offer: { kind: "kyuushu" }, type: "choose" } as const;

    /** Each seat's river as its tiles' ids, and the open decision's offers. */
    function firstTurnAt(state: LiveClient): unknown[] {
        return [
            state.table.players.map((player) => player.discards.map((discard) => discard.tileId)),
            decisionOf(state)?.offers,
        ];
    }

    function winnersAndScores(state: LiveClient): unknown[] {
        return [
            state.table.roundEndResult?.winners.map((winner) => winner.seat),
            state.table.players.map((player) => player.score),
        ];
    }

    it("offers kyuushu alone on the first draw and sends it once: pressed again before the round end, nothing", () => {
        const { scenario } = GAME_END_RECONNECT;
        const twice = branchAfter(scenario, "kyuushu chosen", [
            { event: { at: 5000, intent: KYUUSHU, kind: "intent" }, label: "kyuushu again" },
        ]);
        const run = runClean(twice);
        const submitted = {
            at: 5000,
            bySwitch: null,
            intent: KYUUSHU,
            kind: "submitted",
        };

        expect(firstTurnAt(stateAt(twice, run, "first draw"))).toEqual([
            [[124], [], [], []],
            [{ kind: "kyuushu" }],
        ]);
        expect(decisionOf(stateAt(twice, run, "kyuushu chosen"))?.status).toEqual(submitted);
        expect(decisionOf(stateAt(twice, run, "kyuushu again"))?.status).toEqual(submitted);
    });

    it("tenhou: the dealer's first draw offers tsumo over empty rivers, and the win takes 16,000 from each seat", () => {
        const { scenario } = FIRST_TURN_WIN_DEALER;
        const run = runClean(scenario);

        const [discards, offers] = firstTurnAt(stateAt(scenario, run, "tenhou draw"));

        expect(discards).toEqual([[], [], [], []]);
        expect(offers).toContainEqual({ kind: "tsumo" });
        expect(winnersAndScores(stateAt(scenario, run, "round end"))).toEqual([
            [1],
            [-7000, 65_000, 1000, 41_000],
        ]);
    });

    it("chiihou: the last seat's first draw offers tsumo over the three earlier seats' first discards", () => {
        const { scenario } = FIRST_TURN_WIN_LAST_SEAT;
        const run = runClean(scenario);
        const [discards, offers] = firstTurnAt(stateAt(scenario, run, "chiihou draw"));

        expect(discards).toEqual([[112], [116], [120], []]);
        expect(offers).toContainEqual({ kind: "tsumo" });
        expect(winnersAndScores(stateAt(scenario, run, "round end"))).toEqual([
            [3],
            [9000, 17_000, 17_000, 57_000],
        ]);
    });
});

describe("stepGameClient - generated riichi reconnect", () => {
    const { scenario } = RIICHI_RECONNECT;

    function sticksAndScores(state: LiveClient): (number | number[])[] {
        return [state.table.riichiSticks, state.table.players.map((player) => player.score)];
    }

    it("deposits the game's 2,000 riichi cost once the riichi passes; the snapshot already holds it and the ron settles once", () => {
        const run = runClean(scenario);
        const reconnected = stateAt(scenario, run, "reconnected");

        expect(sticksAndScores(stateAt(scenario, run, "riichi chosen"))).toEqual([
            0,
            [25_000, 25_000, 25_000, 25_000],
        ]);
        expect(sticksAndScores(stateAt(scenario, run, "riichi accepted"))).toEqual([
            1,
            [25_000, 23_000, 25_000, 25_000],
        ]);
        expect(sticksAndScores(reconnected)).toEqual([1, [25_000, 23_000, 25_000, 25_000]]);
        expect(reconnected.table.players[1].isRiichi).toBe(true);
        expect(sticksAndScores(stateAt(scenario, run, "round end"))).toEqual([
            0,
            [25_000, 29_700, 19_800, 25_000],
        ]);
    });

    it("pays the stick the ron collected at the game's 1,500 stick value, apart from the cost and from honba", () => {
        const { table } = stateAt(scenario, runClean(scenario), "round end");
        const result = table.roundEndResult;
        expect(result?.winners.map((winner) => [winner.honbaBonus, winner.riichiBonus])).toEqual([
            [0, 1500],
        ]);
        assert(result !== null);
        const { body } = roundEndDisplay({ players: table.players, result }, 0);
        expect(body.kind === "win" && body.notes).toEqual(["Riichi +1,500"]);
    });
});

describe("stepGameClient - generated round advance", () => {
    it("closes an unconfirmed result when the server's timeout deals the next round, having sent nothing", () => {
        const { scenario } = RIICHI_RECONNECT;
        const run = runClean(scenario);
        const nextRound = stateAt(scenario, run, "next round");

        expect(roundConfirmOf(stateAt(scenario, run, "round end"))).toMatchObject({
            deadline: 7000 + 10_000,
            kind: "owed",
        });
        expect([roundConfirmOf(nextRound), nextRound.table.phase]).toEqual([null, "in_round"]);
    });

    it("counts a double ron's confirm down for both results, and a reconnect's snapshot keeps that deadline", () => {
        const { scenario, transcript } = DOUBLE_RON;
        const run = runClean(scenario);
        const owed = {
            deadline: 5500 + 2 * 10_000,
            kind: "owed",
            waitId: receivedPayload(transcript, "round end").wi,
        };

        expect(roundConfirmOf(stateAt(scenario, run, "round end"))).toEqual(owed);
        expect(roundConfirmOf(stateAt(scenario, run, "dropped"))).toBeNull();
        expect(roundConfirmOf(stateAt(scenario, run, "reconnected"))).toEqual(owed);
    });

    it("keeps an owed confirm through late errors for an earlier move, then sends it once and waits", () => {
        const { scenario, transcript } = OWN_TURN;
        const waitId = 5;
        const confirm = { at: 15_300, intent: { type: "confirm_result" }, kind: "intent" } as const;
        const branch = branchAfter(scenario, "round end", [
            lateError(
                15_100,
                wireGameError(GAME_ERROR_CODE.STALE_ACTION, waitId - 1),
                "late stale",
            ),
            lateError(15_200, wireRuleRefusal(waitId - 1), "late refusal"),
            {
                effects: [{ message: buildConfirmRoundAction(waitId), type: "send" }],
                event: confirm,
            },
            lateError(
                15_400,
                wireGameError(GAME_ERROR_CODE.STALE_ACTION, waitId),
                "stale after confirm",
            ),
            lateError(15_500, wireRuleRefusal(waitId - 1), "refusal after confirm"),
            { event: { ...confirm, at: 15_600 } },
        ]);
        const run = runClean(branch);
        const owed = { deadline: 25_000, kind: "owed", waitId };

        expect(receivedPayload(transcript, "round end").wi).toBe(waitId);
        expect(roundConfirmOf(stateAt(branch, run, "late stale"))).toEqual(owed);
        expect(roundConfirmOf(stateAt(branch, run, "late refusal"))).toEqual(owed);
        expect(roundConfirmOf(stateAt(branch, run, "refusal after confirm"))).toEqual({
            ...owed,
            kind: "sent",
        });
    });

    it("reopens a sent confirm only for a rate limit naming its wait, never one naming none or an earlier wait", () => {
        const rateLimited = SESSION_ERROR_CODE.RATE_LIMITED;
        const confirm = { at: 15_100, intent: { type: "confirm_result" }, kind: "intent" } as const;
        const sent = { message: buildConfirmRoundAction(5), type: "send" } as const;
        const branch = branchAfter(OWN_TURN.scenario, "round end", [
            { effects: [sent], event: confirm },
            lateError(15_200, wireSessionError(rateLimited), "unnamed"),
            lateError(15_300, wireSessionError(rateLimited, 4), "earlier"),
            { event: { ...confirm, at: 15_400 } },
            lateError(15_500, wireSessionError(rateLimited, 5), "matching"),
            { effects: [sent], event: { ...confirm, at: 15_600 } },
        ]);
        const run = runClean(branch);
        const confirmSent = {
            notice: null,
            sync: { pending: { confirm: { kind: "sent", waitId: 5 } } },
        };

        expect(stateAt(branch, run, "unnamed")).toMatchObject(confirmSent);
        expect(stateAt(branch, run, "earlier")).toMatchObject(confirmSent);
        expect(stateAt(branch, run, "matching")).toMatchObject({
            notice: { code: rateLimited, kind: "refused" },
            sync: { pending: { confirm: { kind: "owed", waitId: 5 } } },
        });
    });

    it("waits for the others once the player confirmed, until the last confirm deals the next round", () => {
        const { scenario } = CHANKAN_ROBBED_ROBBER;
        const run = runClean(scenario);

        expect(roundConfirmOf(stateAt(scenario, run, "confirmed"))).toMatchObject({ kind: "sent" });
        expect(roundConfirmOf(lastState(run))).toBeNull();
    });

    it("keeps the game's last result over the game's end until the player dismisses it, sending nothing", () => {
        const { scenario } = FINAL_ROUND;
        const run = runClean(scenario);
        const roundEnd = stateAt(scenario, run, "round end");
        const gameEnd = stateAt(scenario, run, "game end");
        const dismissed = stepGameClient(lastState(run), {
            at: 6000,
            intent: { type: "confirm_result" },
            kind: "intent",
        });

        expect(roundConfirmOf(roundEnd)).toBeNull();
        expect([gameEnd.showsLastResult, gameEnd.table.phase]).toEqual([true, "game_ended"]);
        expect(gameEnd.table.roundEndResult).toBe(roundEnd.table.roundEndResult);
        expect(lastState(run).session?.status).toBe("ended");
        expect([dismissed.effects, dismissed.state.showsLastResult]).toEqual([[], false]);
    });

    it("keeps the last win's call through the game's end and the socket's close, until its own time ends it", () => {
        const { scenario } = FINAL_ROUND;
        const run = runClean(scenario);
        const ron = {
            at: 5000,
            calls: [{ kind: "ron", seat: 1 }],
            until: 5000 + WIN_CALLOUT_CONTEXT_MS,
        };
        const afterClose = lastState(run);

        expect(stateAt(scenario, run, "round end").calls).toEqual(ron);
        expect(stateAt(scenario, run, "game end").calls).toEqual(ron);
        expect([afterClose.calls, nextDeadline(afterClose)]).toEqual([ron, ron.until]);
        expect(stepGameClient(afterClose, { at: ron.until, kind: "tick" }).state.calls).toBeNull();
    });

    it("drops the last win's call when the session fails instead", () => {
        const { scenario } = FINAL_ROUND;
        const roundEnd = stateAt(scenario, runClean(scenario), "round end");
        const failed = stepGameClient(roundEnd, closed(5100, 4002)).state;

        expect([failed.session?.status, failed.calls]).toEqual(["ended", null]);
    });
});

describe("stepGameClient - generated reconnect", () => {
    const { scenario, transcript } = RECONNECT;
    const resentWaitId = Number(receivedPayload(transcript, "prompt re-sent").wi);
    const ponHaku = { offer: { kind: "pon", tileId: HAKU }, type: "choose" } as const;
    const ponHakuSent = { message: buildPonAction(HAKU, resentWaitId), type: "send" } as const;

    it("drops the prompt with the socket, and the prompt re-sent after the snapshot keeps its deadline", () => {
        const run = runClean(scenario);
        const dropped = stateAt(scenario, run, "dropped");
        const reconnected = stateAt(scenario, run, "reconnected");
        const resent = stateAt(scenario, run, "prompt re-sent");

        expect(decisionOf(stateAt(scenario, run, "prompt"))?.deadline).toBe(28_000);
        expect([decisionOf(dropped), dropped.session?.status]).toEqual([null, "awaiting_retry"]);
        expect([decisionOf(reconnected), reconnected.session?.status]).toEqual([null, "playing"]);
        expect(seatsAt(reconnected)).toEqual([
            [0, 13, [HAKU]],
            [13, 0, []],
            [0, 13, []],
            [0, 13, []],
        ]);
        expect(decisionOf(resent)).toMatchObject({
            deadline: 28_000,
            offers: [{ kind: "pon", tileId: HAKU }],
            status: { kind: "open" },
            waitId: receivedPayload(transcript, "prompt re-sent").wi,
        });
    });

    it("pons the re-sent prompt, keeps haku back by kuikae, and rons into the round end", () => {
        const run = runClean(scenario);
        const turn = stateAt(scenario, run, "turn");
        const roundEnd = stateAt(scenario, run, "round end");

        expect(decisionOf(turn)).toMatchObject({
            kind: "turn",
            opening: { kind: "after_call", kuikaeTileTypes: [31] },
        });
        expect(turn.table.players[1].melds.map((meld) => meld.tileIds)).toEqual([[124, 125, HAKU]]);
        expect(decisionOf(stateAt(scenario, run, "ron prompt"))?.offers).toEqual([{ kind: "ron" }]);
        expect(decisionOf(roundEnd)).toBeNull();
        expect(roundEnd.table.roundEndResult?.winners.map((winner) => winner.seat)).toEqual([1]);
        expect(roundEnd.table.players.map((player) => player.score)).toEqual([
            25_000, 26_000, 24_000, 25_000,
        ]);
        expect(roundConfirmOf(roundEnd)).toMatchObject({ deadline: 20_000, kind: "owed" });
    });

    it("ends on a newer tab's 4002 takeover: no confirm, retry or deadline left pending", () => {
        const last = lastState(runClean(scenario));

        expect(last.session).toMatchObject({
            reason: { code: 4002, kind: "closed", reason: "replaced_by_new_connection" },
            status: "ended",
        });
        expect([decisionOf(last), roundConfirmOf(last), nextDeadline(last)]).toEqual([
            null,
            null,
            null,
        ]);
    });

    it("reopens an answer the game refused or the rate limit dropped, not one refused as stale", () => {
        const rateLimited = wireSessionError(SESSION_ERROR_CODE.RATE_LIMITED, resentWaitId);
        const refused = branchAfter(scenario, "pon chosen", [
            lateError(6600, wireRuleRefusal(resentWaitId), "refused"),
            { effects: [ponHakuSent], event: { at: 6700, intent: ponHaku, kind: "intent" } },
            lateError(6800, rateLimited, "dropped"),
            { effects: [ponHakuSent], event: { at: 6900, intent: ponHaku, kind: "intent" } },
            lateError(7000, wireGameError(GAME_ERROR_CODE.STALE_ACTION, resentWaitId), "stale"),
            { event: { at: 7100, intent: ponHaku, kind: "intent" } },
        ]);
        const run = runClean(refused);

        expect(stateAt(refused, run, "refused").notice).toMatchObject({ code: "invalid_pon" });
        expect(decisionOf(stateAt(refused, run, "stale"))?.status).toMatchObject({
            at: 6900,
            kind: "submitted",
        });
    });

    it("reopens a refused answer past the prompt's deadline as expired at once, still taking one answer", () => {
        const late = branchAfter(scenario, "pon chosen", [
            lateError(28_100, wireRuleRefusal(resentWaitId), "refused late"),
            { effects: [ponHakuSent], event: { at: 28_200, intent: ponHaku, kind: "intent" } },
            { event: { at: 28_300, intent: ponHaku, kind: "intent" }, label: "again" },
        ]);
        const run = runClean(late);
        const refused = stateAt(late, run, "refused late");

        expect(decisionOf(refused)).toMatchObject({
            deadline: 28_000,
            status: { kind: "expired" },
        });
        expect(refused.notice).toMatchObject({ code: "invalid_pon", kind: "refused" });
        expect(nextDeadline(refused)).toBe(refused.notice?.until);
        expect(decisionOf(stateAt(late, run, "again"))?.status).toMatchObject({
            at: 28_200,
            kind: "submitted",
        });
    });

    it("reopens nothing and shows nothing for a rate limit naming no wait or another wait than the answer's", () => {
        const rateLimited = SESSION_ERROR_CODE.RATE_LIMITED;
        const branch = branchAfter(scenario, "pon chosen", [
            lateError(6600, wireSessionError(rateLimited), "unnamed"),
            lateError(6700, wireSessionError(rateLimited, resentWaitId - 1), "another wait"),
            { event: { at: 6800, intent: ponHaku, kind: "intent" } },
            lateError(6900, wireSessionError(rateLimited, resentWaitId), "matching"),
            { effects: [ponHakuSent], event: { at: 7000, intent: ponHaku, kind: "intent" } },
        ]);
        const run = runClean(branch);
        const chosen = stateAt(branch, run, "pon chosen");
        const unchanged = [decisionOf(chosen)?.status, chosen.notice];

        expect(decisionOf(chosen)?.status.kind).toBe("submitted");
        expect(
            [stateAt(branch, run, "unnamed"), stateAt(branch, run, "another wait")].map((state) => [
                decisionOf(state)?.status,
                state.notice,
            ]),
        ).toEqual([unchanged, unchanged]);
        expect(stateAt(branch, run, "matching")).toMatchObject({
            notice: { code: rateLimited, kind: "refused" },
            sync: { pending: { decision: { status: { kind: "open" } } } },
        });
    });
});

describe("stepGameClient - generated resync", () => {
    const { scenario, transcript } = RESYNC;
    const resync = { message: buildResyncMessage(), type: "send" } as const;

    it("asks for the seat's state on its own socket after a frame it cannot decode, and the snapshot and draw re-sent reopen the turn timed by the server", () => {
        const run = runClean(scenario);
        const asked = stateAt(scenario, run, "turn resync asked");
        const resent = stateAt(scenario, run, "draw re-sent");

        expect(decisionOf(stateAt(scenario, run, "first draw"))?.status.kind).toBe("open");
        expect([decisionOf(asked), desyncOf(asked)?.request]).toEqual([
            null,
            { due: 4000 + 10_000, kind: "sent" },
        ]);
        expect(desyncOf(stateAt(scenario, run, "turn snapshot"))).toBeNull();
        expect(decisionOf(resent)).toMatchObject({
            baseDeadline: 3000 + 5000,
            deadline: 3000 + (5 + 20) * 1000,
            offers: [{ kind: "kyuushu" }],
            openedAt: 4000,
            status: { kind: "open" },
            waitId: receivedPayload(transcript, "first draw").wi,
        });
        expect([resent.session?.status, resent.resyncRequests]).toEqual(["playing", 1]);
    });

    it("owes the round confirm again after a resync during the round advance, on the deadline the server's elapsed time and timeout name", () => {
        const run = runClean(scenario);
        const waitId = receivedPayload(transcript, "round end").wi;
        const owed = { deadline: 5000 + 10_000, kind: "owed", waitId };

        expect(roundConfirmOf(stateAt(scenario, run, "round end"))).toEqual(owed);
        expect(roundConfirmOf(stateAt(scenario, run, "advance resync asked"))).toBeNull();
        expect(roundConfirmOf(stateAt(scenario, run, "advance snapshot"))).toEqual(owed);
        expect(stateAt(scenario, run, "advance snapshot").table.phase).toBe("round_ended");
        expect(roundConfirmOf(stateAt(scenario, run, "confirmed"))).toEqual({
            ...owed,
            kind: "sent",
        });
        const next = stateAt(scenario, run, "next round");
        expect([roundConfirmOf(next), next.table.phase, next.resyncRequests]).toEqual([
            null,
            "in_round",
            2,
        ]);
    });

    it("asks again at the first deal when the server refuses its resync before dealing", () => {
        const before = RESYNC_BEFORE_DEAL.scenario;
        const refused = stateAt(before, runClean(before), "refused");
        const atDeal = branchAfter(before, "refused", [
            { event: { at: 2999, kind: "tick" } },
            { effects: [resync], event: { at: 3000, kind: "tick" }, label: "deal due" },
        ]);

        expect(receivedPayload(RESYNC_BEFORE_DEAL.transcript, "refused").code).toBe(
            SESSION_ERROR_CODE.GAME_NOT_STARTED,
        );
        expect([desyncOf(refused)?.request, nextDeadline(refused), refused.firstDealDue]).toEqual([
            { due: 3000, kind: "at_deal" },
            3000,
            3000,
        ]);
        const atDealRun = runClean(atDeal);
        expect(desyncOf(stateAt(atDeal, atDealRun, "deal due"))?.request).toEqual({
            due: 3000 + 10_000,
            kind: "sent",
        });
    });

    function receivedAt4000(label: string): ScenarioStep {
        const raw = receivedPayload(transcript, label);
        return { event: { at: 4000, kind: "server_message", raw }, label };
    }

    /** The scenario with its JOIN_GAME's answer a frame that did not decode, answered by the next snapshot. */
    function undecodedJoinAnswer(): SeatScenario {
        const undecoded = scenario.steps.map((step): ScenarioStep =>
            step.label === "joined"
                ? {
                      effects: [{ detail: "non-binary", type: "report_protocol_failure" }],
                      event: { at: 0, detail: "non-binary", kind: "frame_undecodable" },
                      label: "joined",
                  }
                : step,
        );
        return branchAfter(
            expecting({ ...scenario, steps: undecoded }, "dealt", [resync]),
            "first draw",
            [receivedAt4000("turn snapshot"), receivedAt4000("draw re-sent")],
        );
    }

    it("recovers from a JOIN_GAME answer it cannot decode by asking at the first deal, the snapshot admitting it", () => {
        const branch = undecodedJoinAnswer();
        const run = runClean(branch);
        const joined = stateAt(branch, run, "joined");
        const started = stateAt(branch, run, "game started");
        const resent = stateAt(branch, run, "draw re-sent");

        expect([joined.session?.status, desyncOf(joined)?.request]).toEqual([
            "identifying",
            { kind: "on_game_message" },
        ]);
        expect([started.session?.status, desyncOf(started)?.request]).toEqual([
            "identifying",
            { due: 3000, kind: "at_deal" },
        ]);
        expect(decisionOf(stateAt(branch, run, "first draw"))).toBeNull();
        expect([resent.session?.status, desyncOf(resent), resent.resyncRequests]).toEqual([
            "playing",
            null,
            1,
        ]);
        expect(decisionOf(resent)).toMatchObject({
            offers: [{ kind: "kyuushu" }],
            waitId: receivedPayload(transcript, "first draw").wi,
        });
    });
});

describe("stepGameClient - generated anchor", () => {
    const { scenario, transcript } = ANCHOR;
    const SIX_PIN = 56;
    const THREE_PIN = 44;
    const CHARLIES_FIVE_SOU = 90;
    const CHUN_PON = [["pon", [132, 133, 134]]];
    const BOB_IN_RIICHI = [false, false, false, true];

    /** The round shown, the viewer, each seat's river length, Charlie's melds, who is in riichi and the viewer's melds. */
    function boardAt(state: LiveClient): unknown[] {
        const { players } = state.table;
        return [
            tableStateToDisplayState(state.table, ALICE_VIEW)?.center.roundDisplay,
            state.viewerSeat,
            players.map((player) => player.discards.length),
            players[2].melds.map((meld) => [meld.meldType, meld.tileIds]),
            players.map((player) => player.isRiichi),
            players[1].melds,
        ];
    }

    it("own turn: East 2 dealt from the staged wall, the tenth draw opens a plain turn, nine discards a seat", () => {
        const run = runClean(scenario);
        const dealt = stateAt(scenario, run, "east 2 dealt");
        const turn = stateAt(scenario, run, "own turn");

        expect(dealt.table.players[1].tiles).toEqual(
            receivedPayload(transcript, "east 2 dealt").mt,
        );
        expect([dealt.table.dealerSeat, dealt.table.players.map((player) => player.score)]).toEqual(
            [1, [23_000, 25_000, 25_000, 27_000]],
        );
        expect(boardAt(turn)).toEqual(["East 2", 1, [9, 9, 9, 9], CHUN_PON, BOB_IN_RIICHI, []]);
        expect([turn.now, turn.table.players[1].drawnTileId]).toEqual([20_000, SIX_PIN]);
        expect(decisionOf(turn)).toMatchObject({
            baseDeadline: 20_000 + 5000,
            deadline: 20_000 + (5 + 20) * 1000,
            kind: "turn",
            offers: [],
            waitId: receivedPayload(transcript, "own turn").wi,
        });
    });

    it("call offer: Charlie's 5s offers the viewer a pon alone, counted down, and she passes it", () => {
        const run = runClean(scenario);
        const offer = stateAt(scenario, run, "call offer");

        expect(boardAt(offer)).toEqual(["East 2", 1, [9, 10, 10, 9], CHUN_PON, BOB_IN_RIICHI, []]);
        expect(offer.now).toBe(21_000);
        expect(decisionOf(offer)).toEqual({
            baseDeadline: 21_000 + 5000,
            callType: CALL_TYPE.MELD,
            deadline: 21_000 + 25_000,
            fromSeat: 2,
            kind: "call",
            offers: [{ kind: "pon", tileId: CHARLIES_FIVE_SOU }],
            openedAt: 21_000,
            status: { kind: "open" },
            tileId: CHARLIES_FIVE_SOU,
            waitId: receivedPayload(transcript, "call offer").wi,
        });
        expect(decisionOf(stateAt(scenario, run, "passed"))?.status.kind).toBe("submitted");
    });

    it("riichi offer: the eleventh draw offers riichi on 3p or 6p, and the toggle leaves only those to discard", () => {
        const riichi = stateAt(scenario, runClean(scenario), "riichi offer");
        const picking = { ...NO_PLAY_UI, riichiPickWaitId: decisionOf(riichi)?.waitId ?? null };

        expect(boardAt(riichi)).toEqual([
            "East 2",
            1,
            [10, 10, 10, 10],
            CHUN_PON,
            BOB_IN_RIICHI,
            [],
        ]);
        expect(riichi.now).toBe(22_500);
        expect(decisionOf(riichi)).toMatchObject({
            deadline: 22_500 + (5 + 20) * 1000,
            kind: "turn",
            offers: [
                { kind: "riichi", tileId: THREE_PIN },
                { kind: "riichi", tileId: SIX_PIN },
            ],
        });
        expect([...playDisplay(riichi, picking).tileIntents.keys()]).toEqual([THREE_PIN, SIX_PIN]);
    });
});

/** The wall, then the kan declarer's (seat 1's) closed hand size, its melds' types and tile ids. */
function declarerAt(state: LiveClient): unknown[] {
    const [, declarer] = state.table.players;
    return [
        state.table.tilesRemaining,
        declarer.tiles.length + declarer.concealedCount,
        declarer.melds.map((meld) => [meld.meldType, meld.tileIds]),
    ];
}

/** The state after the step labelled `label`, stepped once more with the same event, as no transcript sends it. */
function steppedAgain(scenario: SeatScenario, run: ScenarioRun, label: string): LiveClient {
    const index = scenarioStateIndex(scenario, label);
    return stepGameClient(timelineStates(run.timeline)[index], scenario.steps[index - 1].event)
        .state;
}

describe("stepGameClient - generated chankan", () => {
    it("robber: the prompt shows the closed kan declared, and the ron that robs it takes nothing more", () => {
        const { scenario } = CHANKAN_ROBBED_ROBBER;
        const run = runClean(scenario);
        const prompt = stateAt(scenario, run, "chankan prompt");
        const roundEnd = stateAt(scenario, run, "round end");
        const kan = [10, [["closed_kan", NINE_MAN_COPIES]]];

        expect(declarerAt(stateAt(scenario, run, "discarded"))).toEqual([66, 13, []]);
        expect(declarerAt(prompt)).toEqual([64, ...kan]);
        expect(decisionOf(prompt)).toMatchObject({
            callType: CALL_TYPE.CHANKAN,
            offers: [{ kind: "ron" }],
        });
        expect(declarerAt(roundEnd)).toEqual([64, ...kan]);
        expect(roundEnd.table.roundEndResult?.winners).toMatchObject([
            { seat: 3, winningTile: 32 },
        ]);
    });

    it("declarer: the round end takes the robbed kan's four tiles out of the known hand once", () => {
        const { scenario } = CHANKAN_ROBBED_DECLARER;
        const run = runClean(scenario);
        const kanDraw = stateAt(scenario, run, "kan draw");
        const roundEnd = stateAt(scenario, run, "round end");

        expect(declarerAt(kanDraw)).toEqual([64, 14, []]);
        expect(decisionOf(kanDraw)?.offers).toEqual([
            { kanType: KAN_TYPE.CLOSED, kind: "kan", tileId: 32 },
        ]);
        expect(declarerAt(roundEnd)).toEqual([64, 10, [["closed_kan", NINE_MAN_COPIES]]]);
        expect(roundEnd.table.players[1].tiles).not.toContain(35);
    });

    it("declarer: the snapshot of the round advance shows the kan its result robbed, as the round end did", () => {
        const { scenario } = CHANKAN_ROBBED_DECLARER;
        const run = runClean(scenario);
        const roundEnd = stateAt(scenario, run, "round end");
        const reconnected = stateAt(scenario, run, "reconnected");

        expect(reconnected.table.phase).toBe("round_ended");
        expect(declarerAt(reconnected)).toEqual(declarerAt(roundEnd));
        expect(reconnected.table.players[1].tiles).toEqual(roundEnd.table.players[1].tiles);
        expect(roundConfirmOf(reconnected)).toEqual(roundConfirmOf(roundEnd));
    });

    it("robber who passes: the prompt shows the added kan, a reconnect re-shows it once, the meld completes it", () => {
        const { scenario } = CHANKAN_PASSED;
        const run = runClean(scenario);
        const kan = [65, 10, [["added_kan", [56, 57, 58, 59]]]];

        expect([
            declarerAt(stateAt(scenario, run, "chankan prompt")),
            declarerAt(steppedAgain(scenario, run, "chankan prompt")),
        ]).toEqual([kan, kan]);
        expect(declarerAt(stateAt(scenario, run, "reconnected"))).toEqual([
            65,
            11,
            [["pon", [56, 57, 58]]],
        ]);
        expect(declarerAt(stateAt(scenario, run, "prompt re-sent"))).toEqual(kan);
        const completed = stateAt(scenario, run, "kan");
        expect(declarerAt(completed)).toEqual(kan);
        expect(completed.table.players[1].melds[0]).toMatchObject({ addedTileId: 59 });
        expect(decisionOf(completed)).toBeNull();
    });
});
