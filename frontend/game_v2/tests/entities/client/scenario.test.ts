import { describe, expect, it } from "vitest";

import { clientEvent, forbiddingIo } from "#tests/fixtures/scenario";
import {
    branchAfter,
    loadSeatScenario,
    receivedPayload,
    scenarioFromTranscript,
} from "#tests/fixtures/seat-transcripts";
import {
    WIRE_SEAT_TO_AI,
    type WirePayload,
    wireGameError,
    wireRuleRefusal,
    wireSessionError,
} from "#tests/fixtures/wire";
import {
    type GameClientState,
    NO_PLAY_UI,
    type ScenarioRun,
    type ScenarioStep,
    type SeatScenario,
    nextDeadline,
    parseSeatTranscript,
    playDisplay,
    runSeatScenario,
    scenarioStateIndex,
    stepGameClient,
    timelineStates,
} from "@/entities/client";
import { tableStateToDisplayState } from "@/entities/table";
import { standingsDisplay } from "@/entities/table/lib/standings-display";
import { SEAT_TRANSCRIPTS } from "@/fixtures/seat-transcripts";
import {
    CALL_TYPE,
    CLIENT_MESSAGE_TYPE,
    EVENT_TYPE,
    GAME_ACTION,
    GAME_ERROR_CODE,
    KAN_TYPE,
    SESSION_ERROR_CODE,
    buildChiAction,
    buildConfirmRoundAction,
    buildDiscardAction,
    buildJoinGameMessage,
    buildPonAction,
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

function stateAt(scenario: SeatScenario, run: ScenarioRun, label: string): GameClientState {
    return timelineStates(run.timeline)[scenarioStateIndex(scenario, label)];
}

function lastState(run: ScenarioRun): GameClientState {
    return timelineStates(run.timeline).at(-1) ?? run.timeline.start;
}

function lateError(at: number, raw: WirePayload, label: string): ScenarioStep {
    return { event: { at, kind: "server_message", raw }, label };
}

function discardAt(at: number, tileId: number): ScenarioStep["event"] {
    return { at, intent: { tileId, type: "discard" }, kind: "intent" };
}

/** The table's seats as their known tiles, concealed count, then the tile ids of their discards. */
function seatsAt(state: GameClientState): (number | number[])[][] {
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
            "game_end_reconnect_seat_1",
            "kan_choice_seat_1",
            "own_turn_seat_1",
            "reconnect_seat_1",
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
            const { wi: _waitId, ...payload } = event.payload;
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
        expect(dealt.decision).toBeNull();
        expect(prompt.decision).toEqual({
            callType: CALL_TYPE.MELD,
            deadline: 3000 + 5000,
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
        expect(nextDeadline(prompt)).toBe(8000);
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
            kind: "submitted",
            message: buildChiAction(CALLED_THREE_MAN, [0, 4], 1),
        };

        expect(stateAt(twice, run, "chi chosen").decision?.status).toEqual(submitted);
        expect(stateAt(twice, run, "chi again").decision?.status).toEqual(submitted);
        expect(nextDeadline(stateAt(twice, run, "chi again"))).toBeNull();
    });

    it("opens the turn after the chi with the kuikae types the server named", () => {
        const run = runClean(scenario);
        const turn = stateAt(scenario, run, "turn");
        const turnPayload = receivedPayload(transcript, "turn");

        expect(turn.decision).toMatchObject({
            deadline: 5000 + (5 + 30) * 1000,
            kind: "turn",
            kuikaeTileTypes: turnPayload.kt,
            offers: [],
            waitId: turnPayload.wi,
        });
        expect(turn.table.players[1].melds.map((meld) => meld.tileIds)).toEqual([[0, 4, 8]]);
        expect(turn.table.players[1].tiles).toHaveLength(11);
    });

    it("keeps the turn open on a discard kuikae forbids, sending nothing", () => {
        const kuikae = branchAfter(scenario, "turn", [
            {
                event: { at: 6000, intent: { tileId: 9, type: "discard" }, kind: "intent" },
                label: "kuikae discard",
            },
        ]);
        const run = runClean(kuikae);

        expect(stateAt(kuikae, run, "kuikae discard").decision).toBe(
            stateAt(kuikae, run, "turn").decision,
        );
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
        const notice = { s: 3, t: EVENT_TYPE.DRAW_NOTICE };
        const passedOver = branchAfter(scenario, "pon prompt", [
            { event: { at: 13_000, kind: "server_message", raw: notice }, label: "seat 3 drew" },
        ]);
        const run = runClean(passedOver);

        expect(stateAt(passedOver, run, "pon prompt").decision?.status.kind).toBe("open");
        expect(stateAt(passedOver, run, "seat 3 drew").decision).toBeNull();
    });

    it("passes the pon prompt, and the next draw opens the turn with the bank the server left", () => {
        const run = runClean(scenario);
        const next = stateAt(scenario, run, "next turn");
        const drawPayload = receivedPayload(transcript, "next turn");

        expect(stateAt(scenario, run, "pon prompt").decision).toMatchObject({
            fromSeat: 2,
            offers: [{ kind: "pon", tileId: 98 }],
        });
        expect(stateAt(scenario, run, "passed").decision?.status.kind).toBe("submitted");
        expect(next.decision).toMatchObject({
            deadline: 14_000 + (5 + 28) * 1000,
            kind: "turn",
            kuikaeTileTypes: [],
            waitId: drawPayload.wi,
        });
        expect(next.table.players[1].drawnTileId).toBe(72);
        expect(next.table.tilesRemaining).toBe(65);
    });

    it("keeps an expired prompt for display: a late choice still sends once, with or without a tick first", () => {
        const late = { at: 8500, intent: PON_THREE_MAN, kind: "intent" } as const;
        const again = { at: 8750, intent: PON_THREE_MAN, kind: "intent" } as const;
        const ticked = branchAfter(scenario, "prompt", [
            { event: { at: 7999, kind: "tick" }, label: "just before" },
            { event: { at: 8000, kind: "tick" }, label: "deadline" },
            { effects: [PON_THREE_MAN_SENT], event: late, label: "late" },
            { event: again },
        ]);
        const unticked = branchAfter(scenario, "prompt", [
            { effects: [PON_THREE_MAN_SENT], event: late, label: "late" },
            { event: again },
        ]);
        const tickedRun = runClean(ticked);
        const untickedRun = runClean(unticked);

        expect(stateAt(ticked, tickedRun, "just before").decision?.status).toEqual({
            kind: "open",
        });
        expect(stateAt(ticked, tickedRun, "deadline").decision?.status).toEqual({
            kind: "expired",
        });
        expect(nextDeadline(stateAt(ticked, tickedRun, "deadline"))).toBeNull();
        expect(stateAt(ticked, tickedRun, "late").decision).toEqual(
            stateAt(unticked, untickedRun, "late").decision,
        );
    });
});

describe("stepGameClient - generated own turn", () => {
    const { scenario, transcript } = OWN_TURN;

    it("opens the first draw's riichi and closed-kan offers, the kan answered with a tile of its type", () => {
        const run = runClean(scenario);

        expect(stateAt(scenario, run, "first draw").decision).toEqual({
            baseDeadline: 3000 + 5 * 1000,
            deadline: 3000 + (5 + 30) * 1000,
            drawnTileId: 3,
            kind: "turn",
            kuikaeTileTypes: [],
            offers: [
                { kind: "riichi", tileId: 0 },
                { kind: "riichi", tileId: 1 },
                { kind: "riichi", tileId: 2 },
                { kind: "riichi", tileId: 3 },
                { kanType: KAN_TYPE.CLOSED, kind: "kan", tileId: 0 },
            ],
            openedAt: 3000,
            status: { kind: "open" },
            waitId: receivedPayload(transcript, "first draw").wi,
        });
    });

    it("drops the turn with the socket, and the draw re-sent after the takeover keeps its deadline", () => {
        const run = runClean(scenario);
        const dropped = stateAt(scenario, run, "dropped");
        const resent = stateAt(scenario, run, "draw re-sent");
        const [, alice] = resent.table.players;

        expect([dropped.decision, dropped.session?.status]).toEqual([null, "reconnecting"]);
        expect(stateAt(scenario, run, "reconnected").decision).toBeNull();
        expect(resent.decision).toMatchObject({
            deadline: 3000 + (5 + 30) * 1000,
            openedAt: 4500,
            status: { kind: "open" },
            waitId: receivedPayload(transcript, "draw re-sent").wi,
        });
        expect(resent.decision?.offers).toEqual(
            stateAt(scenario, run, "first draw").decision?.offers,
        );
        expect([alice.tiles.length, alice.drawnTileId, resent.table.tilesRemaining]).toEqual([
            14, 3, 68,
        ]);
    });

    it("declares the closed kan, and the rinshan draw opens the next turn on its own wait", () => {
        const run = runClean(scenario);
        const rinshan = stateAt(scenario, run, "rinshan");
        const [, alice] = rinshan.table.players;

        expect(rinshan.decision).toMatchObject({
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

        expect(stateAt(scenario, run, "ron prompt").decision).toMatchObject({
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

        expect(stateAt(riichiTurn, run, "not the drawn tile").decision).toBe(
            stateAt(riichiTurn, run, "tsumo draw").decision,
        );
    });

    it("settles the tsumo at the round end and owes its confirm, counted down, until the player presses OK", () => {
        const run = runClean(scenario);
        const roundEnd = stateAt(scenario, run, "round end");

        expect(stateAt(scenario, run, "tsumo draw").decision?.offers).toEqual([{ kind: "tsumo" }]);
        expect(roundEnd.decision).toBeNull();
        expect(roundEnd.table.roundEndResult?.winners.map((winner) => winner.seat)).toEqual([1]);
        expect(roundEnd.table.players.map((player) => player.score)).toEqual([
            21_000, 33_000, 23_000, 23_000,
        ]);
        const waitId = receivedPayload(transcript, "round end").wi;
        expect(roundEnd.roundConfirm).toEqual({ deadline: 15_000 + 10_000, kind: "owed", waitId });
        expect(stateAt(scenario, run, "confirmed").roundConfirm).toEqual({
            deadline: 25_000,
            kind: "sent",
            waitId,
        });
        expect(stateAt(scenario, run, "next round").roundConfirm).toBeNull();
    });

    it("deals the next round to the winner as dealer, furiten cleared and the round bonus in the bank", () => {
        const run = runClean(scenario);
        const nextRound = stateAt(scenario, run, "next round");

        expect([nextRound.table.dealerSeat, nextRound.furiten]).toEqual([1, false]);
        expect(tableStateToDisplayState(nextRound.table, ALICE_VIEW)?.center.roundDisplay).toBe(
            "East 2",
        );
        expect(nextRound.table.players[1].tiles).toEqual(
            receivedPayload(transcript, "next round").mt,
        );
        expect(stateAt(scenario, run, "dealer draw").decision?.deadline).toBe(
            16_000 + (5 + 39) * 1000,
        );
    });

    it("gives a turn whose draw names no bank no deadline rather than a guessed one", () => {
        const noBank = scenario.steps.map((step): ScenarioStep => {
            const { event } = step;
            if (step.label !== "dealer draw" || event.kind !== "server_message") {
                return step;
            }
            const { bk: _bank, ...raw } = event.raw;
            return { ...step, event: { ...event, raw } };
        });
        const variant = { ...scenario, steps: noBank };

        expect(stateAt(variant, runClean(variant), "dealer draw").decision?.deadline).toBeNull();
    });
});

describe("stepGameClient - generated riichi reconnect", () => {
    const { scenario } = RIICHI_RECONNECT;

    function sticksAndScores(state: GameClientState): (number | number[])[] {
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
        expect([reconnected.table.players[1].isRiichi, reconnected.table.riichiCost]).toEqual([
            true,
            2000,
        ]);
        expect(sticksAndScores(stateAt(scenario, run, "round end"))).toEqual([
            0,
            [25_000, 29_200, 19_800, 25_000],
        ]);
    });

    it("nets the 2,000 deposit, not the 1,000 stick the ron collected, out of the riichi's round in the final ledger", () => {
        const display = standingsDisplay(
            stateAt(scenario, runClean(scenario), "game end").table,
            1,
        );
        const column = display?.seats.findIndex((seat) => seat.seat === 1) ?? -1;

        expect(display?.ledger[0].cells[column]).toMatchObject({ riichi: true, text: "+4,200" });
    });
});

describe("stepGameClient - generated round advance", () => {
    it("closes an unconfirmed result when the server's timeout deals the next round, having sent nothing", () => {
        const { scenario } = RIICHI_RECONNECT;
        const run = runClean(scenario);
        const nextRound = stateAt(scenario, run, "next round");

        expect(stateAt(scenario, run, "round end").roundConfirm).toMatchObject({
            deadline: 7000 + 10_000,
            kind: "owed",
        });
        expect([nextRound.roundConfirm, nextRound.table.phase]).toEqual([null, "in_round"]);
    });

    it("counts a double ron's confirm down for both results, and a reconnect's snapshot keeps that deadline", () => {
        const { scenario, transcript } = DOUBLE_RON;
        const run = runClean(scenario);
        const owed = {
            deadline: 5500 + 2 * 10_000,
            kind: "owed",
            waitId: receivedPayload(transcript, "round end").wi,
        };

        expect(stateAt(scenario, run, "round end").roundConfirm).toEqual(owed);
        expect(stateAt(scenario, run, "dropped").roundConfirm).toBeNull();
        expect(stateAt(scenario, run, "reconnected").roundConfirm).toEqual(owed);
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
        expect(stateAt(branch, run, "late stale").roundConfirm).toEqual(owed);
        expect(stateAt(branch, run, "late refusal").roundConfirm).toEqual(owed);
        expect(stateAt(branch, run, "refusal after confirm").roundConfirm).toEqual({
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
        const confirmSent = { notice: null, roundConfirm: { kind: "sent", waitId: 5 } };

        expect(stateAt(branch, run, "unnamed")).toMatchObject(confirmSent);
        expect(stateAt(branch, run, "earlier")).toMatchObject(confirmSent);
        expect(stateAt(branch, run, "matching")).toMatchObject({
            notice: { code: rateLimited, kind: "refused" },
            roundConfirm: { kind: "owed", waitId: 5 },
        });
    });

    it("waits for the others once the player confirmed, until the last confirm deals the next round", () => {
        const { scenario } = CHANKAN_ROBBED_ROBBER;
        const run = runClean(scenario);

        expect(stateAt(scenario, run, "confirmed").roundConfirm).toMatchObject({ kind: "sent" });
        expect(lastState(run).roundConfirm).toBeNull();
    });

    it("keeps the game's last result over the standings until the player dismisses it, sending nothing", () => {
        const { scenario } = FINAL_ROUND;
        const run = runClean(scenario);
        const roundEnd = stateAt(scenario, run, "round end");
        const gameEnd = stateAt(scenario, run, "game end");
        const dismissed = stepGameClient(lastState(run), {
            at: 6000,
            intent: { type: "confirm_result" },
            kind: "intent",
        });

        expect(roundEnd.roundConfirm).toBeNull();
        expect([gameEnd.roundConfirm, gameEnd.table.phase]).toEqual([
            { kind: "final" },
            "game_ended",
        ]);
        expect(gameEnd.table.roundEndResult).toBe(roundEnd.table.roundEndResult);
        expect(lastState(run).session?.status).toBe("ended");
        expect([dismissed.effects, dismissed.state.roundConfirm]).toEqual([[], null]);
    });

    it("keeps the last win's call through the game's end and the socket's close, until its own time ends it", () => {
        const { scenario } = FINAL_ROUND;
        const run = runClean(scenario);
        const ron = { at: 5000, calls: [{ kind: "ron", seat: 1 }], until: 6500 };
        const afterClose = lastState(run);

        expect(stateAt(scenario, run, "round end").calls).toEqual(ron);
        expect(stateAt(scenario, run, "game end").calls).toEqual(ron);
        expect([afterClose.calls, nextDeadline(afterClose)]).toEqual([ron, 6500]);
        expect(stepGameClient(afterClose, { at: 6500, kind: "tick" }).state.calls).toBeNull();
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

        expect(stateAt(scenario, run, "prompt").decision?.deadline).toBe(8000);
        expect([dropped.decision, dropped.session?.status]).toEqual([null, "reconnecting"]);
        expect([reconnected.decision, reconnected.session?.status]).toEqual([null, "playing"]);
        expect(seatsAt(reconnected)).toEqual([
            [0, 13, [HAKU]],
            [13, 0, []],
            [0, 13, []],
            [0, 13, []],
        ]);
        expect(resent.decision).toMatchObject({
            deadline: 8000,
            offers: [{ kind: "pon", tileId: HAKU }],
            status: { kind: "open" },
            waitId: receivedPayload(transcript, "prompt re-sent").wi,
        });
    });

    it("pons the re-sent prompt, keeps haku back by kuikae, and rons into the round end", () => {
        const run = runClean(scenario);
        const turn = stateAt(scenario, run, "turn");
        const roundEnd = stateAt(scenario, run, "round end");

        expect(turn.decision).toMatchObject({ kind: "turn", kuikaeTileTypes: [31] });
        expect(turn.table.players[1].melds.map((meld) => meld.tileIds)).toEqual([[124, 125, HAKU]]);
        expect(stateAt(scenario, run, "ron prompt").decision?.offers).toEqual([{ kind: "ron" }]);
        expect(roundEnd.decision).toBeNull();
        expect(roundEnd.table.roundEndResult?.winners.map((winner) => winner.seat)).toEqual([1]);
        expect(roundEnd.table.players.map((player) => player.score)).toEqual([
            25_000, 26_000, 24_000, 25_000,
        ]);
        expect(roundEnd.roundConfirm).toMatchObject({ deadline: 20_000, kind: "owed" });
    });

    it("ends on a newer tab's 4002 takeover: no confirm, retry or deadline left pending", () => {
        const last = lastState(runClean(scenario));

        expect(last.session).toMatchObject({
            reason: { code: 4002, kind: "closed", reason: "replaced_by_new_connection" },
            status: "ended",
        });
        expect([last.decision, last.roundConfirm, nextDeadline(last)]).toEqual([null, null, null]);
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
        expect(stateAt(refused, run, "stale").decision?.status).toMatchObject({
            at: 6900,
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
        const unchanged = [chosen.decision?.status, chosen.notice];

        expect(chosen.decision?.status.kind).toBe("submitted");
        expect(
            [stateAt(branch, run, "unnamed"), stateAt(branch, run, "another wait")].map((state) => [
                state.decision?.status,
                state.notice,
            ]),
        ).toEqual([unchanged, unchanged]);
        expect(stateAt(branch, run, "matching")).toMatchObject({
            decision: { status: { kind: "open" } },
            notice: { code: rateLimited, kind: "refused" },
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
    function boardAt(state: GameClientState): unknown[] {
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
        expect(turn.decision).toMatchObject({
            baseDeadline: 20_000 + 5000,
            deadline: 20_000 + (5 + 40) * 1000,
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
        expect(offer.decision).toEqual({
            callType: CALL_TYPE.MELD,
            deadline: 21_000 + 5000,
            fromSeat: 2,
            kind: "call",
            offers: [{ kind: "pon", tileId: CHARLIES_FIVE_SOU }],
            openedAt: 21_000,
            status: { kind: "open" },
            tileId: CHARLIES_FIVE_SOU,
            waitId: receivedPayload(transcript, "call offer").wi,
        });
        expect(stateAt(scenario, run, "passed").decision?.status.kind).toBe("submitted");
    });

    it("riichi offer: the eleventh draw offers riichi on 3p or 6p, and the toggle leaves only those to discard", () => {
        const riichi = stateAt(scenario, runClean(scenario), "riichi offer");
        const picking = { ...NO_PLAY_UI, riichiPickWaitId: riichi.decision?.waitId ?? null };

        expect(boardAt(riichi)).toEqual([
            "East 2",
            1,
            [10, 10, 10, 10],
            CHUN_PON,
            BOB_IN_RIICHI,
            [],
        ]);
        expect(riichi.now).toBe(22_500);
        expect(riichi.decision).toMatchObject({
            deadline: 22_500 + (5 + 40) * 1000,
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
function declarerAt(state: GameClientState): unknown[] {
    const [, declarer] = state.table.players;
    return [
        state.table.tilesRemaining,
        declarer.tiles.length + declarer.concealedCount,
        declarer.melds.map((meld) => [meld.meldType, meld.tileIds]),
    ];
}

/** The state after the step labelled `label`, stepped once more with the same event, as no transcript sends it. */
function steppedAgain(scenario: SeatScenario, run: ScenarioRun, label: string): GameClientState {
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
        expect(prompt.decision).toMatchObject({
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
        expect(kanDraw.decision?.offers).toEqual([
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
        expect(reconnected.roundConfirm).toEqual(roundEnd.roundConfirm);
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
        expect(completed.decision).toBeNull();
    });
});
