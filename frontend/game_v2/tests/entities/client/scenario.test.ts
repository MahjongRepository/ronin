import { describe, expect, it } from "vitest";

import { forbiddingIo } from "#tests/fixtures/scenario";
import { CALL_PROMPT_SCENARIO } from "#tests/fixtures/scenarios/call-prompt";
import { OWN_TURN_SCENARIO } from "#tests/fixtures/scenarios/own-turn";
import {
    type GameClientState,
    type ScenarioRun,
    type ScenarioStep,
    type SeatScenario,
    nextDeadline,
    runSeatScenario,
    scenarioStateIndex,
    timelineStates,
} from "@/entities/client";
import {
    GAME_ERROR_CODE,
    KAN_TYPE,
    SESSION_ERROR_CODE,
    buildPassAction,
    buildPonAction,
    buildRonAction,
} from "@/shared/protocol";

const NINE_MAN = 33;
const PROMPT_OFFERS = [
    { kind: "pon", tileId: NINE_MAN },
    { kanType: "open", kind: "kan", tileId: NINE_MAN },
    { kind: "chi", sequence: [24, 28], tileId: NINE_MAN },
];
const PON = { offer: { kind: "pon", tileId: NINE_MAN }, type: "choose" } as const;
const PON_SENT = { message: buildPonAction(NINE_MAN, 4), type: "send" } as const;

function runClean(scenario: SeatScenario): ScenarioRun {
    const run = runSeatScenario(scenario);
    expect(run.mismatches).toEqual([]);
    return run;
}

function stateAt(scenario: SeatScenario, run: ScenarioRun, label: string): GameClientState {
    return timelineStates(run.timeline)[scenarioStateIndex(scenario, label)];
}

function refusal(code: string): Record<string, unknown> {
    return { cd: code, msg: code, t: 7 };
}

function branchAfter(
    scenario: SeatScenario,
    label: string,
    steps: readonly ScenarioStep[],
): SeatScenario {
    const kept = scenario.steps.slice(0, scenarioStateIndex(scenario, label));
    return { ...scenario, steps: [...kept, ...steps] };
}

describe("runSeatScenario", () => {
    it("reports a step whose effects part from the ones the scenario names", () => {
        const silentPon = CALL_PROMPT_SCENARIO.steps.map((step): ScenarioStep =>
            step.label === "pon chosen" ? { ...step, effects: [] } : step,
        );
        const run = runSeatScenario({ ...CALL_PROMPT_SCENARIO, steps: silentPon });

        expect(run.mismatches).toEqual([
            {
                actual: [PON_SENT],
                expected: [],
                kind: "effects",
                label: "pon chosen",
                step: scenarioStateIndex(CALL_PROMPT_SCENARIO, "pon chosen") - 1,
            },
        ]);
    });
});

describe("stepGameClient - call prompt scenario", () => {
    it("shows the prompt with its offers at its step and none at the step before, running no IO", () => {
        const { calls, result } = forbiddingIo(() => {
            const states = timelineStates(runClean(CALL_PROMPT_SCENARIO).timeline);
            const at = scenarioStateIndex(CALL_PROMPT_SCENARIO, "prompt");
            return { before: states[at - 1], prompt: states[at] };
        });
        const { before, prompt } = result;

        expect(calls).toEqual([0, 0, 0, 0]);
        expect(before.decision).toBeNull();
        expect(prompt.decision).toEqual({
            callType: 1,
            deadline: 8510,
            fromSeat: 0,
            kind: "call",
            offers: PROMPT_OFFERS,
            openedAt: 3510,
            status: { kind: "open" },
            tileId: NINE_MAN,
            waitId: 4,
        });
        expect(prompt.table.players.map((p) => [p.tiles.length, p.concealedCount])).toEqual([
            [0, 13],
            [13, 0],
            [0, 13],
            [0, 13],
        ]);
        expect(prompt.table.tilesRemaining).toBe(69);
        expect(nextDeadline(prompt)).toBe(8510);
    });

    it("sends one pon with the prompt's wait id, submitted until the meld closes the prompt", () => {
        const run = runClean(CALL_PROMPT_SCENARIO);
        const chosen = stateAt(CALL_PROMPT_SCENARIO, run, "pon chosen");
        const states = timelineStates(run.timeline);
        const afterMeld = states[scenarioStateIndex(CALL_PROMPT_SCENARIO, "pon chosen") + 1];

        expect(chosen.decision?.status).toEqual({
            at: 6000,
            kind: "submitted",
            message: PON_SENT.message,
        });
        expect(nextDeadline(chosen)).toBeNull();
        expect(afterMeld.decision).toBeNull();
        expect(afterMeld.table.players[1].melds.map((meld) => meld.tileIds)).toEqual([
            [32, 33, 34],
        ]);
    });

    it("drops the prompt with the socket, and the prompt re-sent after the snapshot keeps its deadline", () => {
        const run = runClean(CALL_PROMPT_SCENARIO);
        const dropped = stateAt(CALL_PROMPT_SCENARIO, run, "dropped");
        const reconnected = stateAt(CALL_PROMPT_SCENARIO, run, "reconnected");
        const resent = stateAt(CALL_PROMPT_SCENARIO, run, "prompt re-sent");

        expect(dropped.decision).toBeNull();
        expect(reconnected.decision).toBeNull();
        expect(reconnected.session?.status).toBe("playing");
        expect(reconnected.table.players[0].discards.map((d) => d.tileId)).toEqual([NINE_MAN]);
        expect(resent.decision).toMatchObject({
            deadline: 8510,
            offers: PROMPT_OFFERS,
            status: { kind: "open" },
            waitId: 4,
        });
    });

    it("opens the turn after the pon with the turn event's wait id, its kuikae type sending nothing", () => {
        const run = runClean(CALL_PROMPT_SCENARIO);
        const turn = stateAt(CALL_PROMPT_SCENARIO, run, "turn");

        expect(turn.decision).toMatchObject({
            deadline: 6110 + 25_000,
            kind: "turn",
            kuikaeTileTypes: [8],
            offers: [],
            waitId: 5,
        });
        expect(stateAt(CALL_PROMPT_SCENARIO, run, "kuikae discard").decision).toBe(turn.decision);
    });

    it("passes a pon prompt with its wait id, and the next discard closes it", () => {
        const run = runClean(CALL_PROMPT_SCENARIO);

        expect(stateAt(CALL_PROMPT_SCENARIO, run, "pon prompt").decision?.offers).toEqual([
            { kind: "pon", tileId: 64 },
        ]);
        expect(stateAt(CALL_PROMPT_SCENARIO, run, "passed").decision?.status).toMatchObject({
            kind: "submitted",
            message: buildPassAction(6),
        });
        expect(stateAt(CALL_PROMPT_SCENARIO, run, "moved on").decision).toBeNull();
    });

    it("offers only ron on a ron prompt, sends it with its wait id, and the round end closes it", () => {
        const ron = branchAfter(CALL_PROMPT_SCENARIO, "passed", [
            { event: { at: 7400, kind: "server_message", raw: { d: 508, t: 2 } } },
            {
                event: {
                    at: 7410,
                    kind: "server_message",
                    raw: { clt: 0, cs: 1, frs: 3, t: 3, ti: 100, wi: 7 },
                },
                label: "ron prompt",
            },
            {
                effects: [{ message: buildRonAction(7), type: "send" }],
                event: {
                    at: 7500,
                    intent: { offer: { kind: "ron" }, type: "choose" },
                    kind: "intent",
                },
            },
            {
                event: {
                    at: 7600,
                    kind: "server_message",
                    raw: {
                        ct: [8, 24, 28, 35, 44, 48, 65, 66, 72, 76],
                        hr: { fu: 30, han: 1, pt: 10, yk: [{ han: 1, yi: 13 }] },
                        ls: 3,
                        ml: [17_409],
                        rc: 0,
                        rt: 1,
                        sch: { "1": 10, "3": -10 },
                        scs: { "0": 250, "1": 250, "2": 250, "3": 250 },
                        t: 4,
                        ws: 1,
                        wt: 100,
                    },
                },
                label: "won",
            },
        ]);
        const run = runClean(ron);
        const won = stateAt(ron, run, "won");

        expect(stateAt(ron, run, "ron prompt").decision?.offers).toEqual([{ kind: "ron" }]);
        expect(won.decision).toBeNull();
        expect(won.table.roundEndResult?.winners.map((winner) => winner.seat)).toEqual([1]);
    });

    it("keeps an expired prompt for display: a late choice still sends once, with or without a tick first", () => {
        const late = { at: 8600, intent: PON, kind: "intent" } as const;
        const again = { at: 8700, intent: PON, kind: "intent" } as const;
        const ticked = branchAfter(CALL_PROMPT_SCENARIO, "prompt", [
            { event: { at: 8509, kind: "tick" }, label: "just before" },
            { event: { at: 8510, kind: "tick" }, label: "deadline" },
            { effects: [PON_SENT], event: late, label: "late" },
            { event: again },
        ]);
        const unticked = branchAfter(CALL_PROMPT_SCENARIO, "prompt", [
            { effects: [PON_SENT], event: late, label: "late" },
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

    it("reopens an answer the game refused or the rate limit dropped, not one refused as stale", () => {
        const refused = branchAfter(CALL_PROMPT_SCENARIO, "pon chosen", [
            { event: { at: 6050, kind: "server_message", raw: refusal("invalid_pon") } },
            { effects: [PON_SENT], event: { at: 6060, intent: PON, kind: "intent" } },
            {
                event: {
                    at: 6065,
                    kind: "server_message",
                    raw: {
                        code: SESSION_ERROR_CODE.RATE_LIMITED,
                        message: "",
                        type: "session_error",
                    },
                },
            },
            { effects: [PON_SENT], event: { at: 6070, intent: PON, kind: "intent" } },
            {
                event: {
                    at: 6080,
                    kind: "server_message",
                    raw: refusal(GAME_ERROR_CODE.STALE_ACTION),
                },
                label: "stale",
            },
            { event: { at: 6090, intent: PON, kind: "intent" } },
        ]);
        const run = runClean(refused);

        expect(stateAt(refused, run, "stale").decision?.status).toMatchObject({
            at: 6070,
            kind: "submitted",
        });
    });
});

describe("stepGameClient - own turn scenario", () => {
    it("opens the draw's riichi and closed-kan offers, its deadline the bank less the elapsed time", () => {
        const run = runClean(OWN_TURN_SCENARIO);

        expect(stateAt(OWN_TURN_SCENARIO, run, "turn").decision).toEqual({
            deadline: 3100 + (5 + 20 - 2) * 1000,
            kind: "turn",
            kuikaeTileTypes: [],
            offers: [
                { kind: "riichi", tileId: 84 },
                { kind: "riichi", tileId: 0 },
                { kanType: KAN_TYPE.CLOSED, kind: "kan", tileId: 108 },
            ],
            openedAt: 3100,
            status: { kind: "open" },
            waitId: 1,
        });
    });

    it("declares the closed kan, and the rinshan draw opens the next turn on its own wait", () => {
        const run = runClean(OWN_TURN_SCENARIO);
        const rinshan = stateAt(OWN_TURN_SCENARIO, run, "rinshan");
        const [alice] = rinshan.table.players;

        expect(stateAt(OWN_TURN_SCENARIO, run, "kan chosen").decision?.status.kind).toBe(
            "submitted",
        );
        expect(rinshan.decision).toMatchObject({
            offers: [{ kind: "riichi", tileId: 88 }],
            waitId: 2,
        });
        expect(alice.melds.map((meld) => meld.meldType)).toEqual(["closed_kan"]);
        expect([alice.tiles.length, alice.drawnTileId, rinshan.table.tilesRemaining]).toEqual([
            11, 88, 68,
        ]);
    });

    it("in riichi takes only the drawn tile as the turn's discard", () => {
        const run = runClean(OWN_TURN_SCENARIO);
        const turn = stateAt(OWN_TURN_SCENARIO, run, "riichi turn");

        expect(turn.table.players[0].isRiichi).toBe(true);
        expect(turn.table.tilesRemaining).toBe(64);
        expect(stateAt(OWN_TURN_SCENARIO, run, "not the drawn tile").decision).toBe(turn.decision);
        expect(stateAt(OWN_TURN_SCENARIO, run, "tsumogiri").decision?.status.kind).toBe(
            "submitted",
        );
    });

    it("gives a turn whose draw names no bank no deadline rather than a guessed one", () => {
        const noBank = OWN_TURN_SCENARIO.steps.map((step): ScenarioStep => {
            const { event } = step;
            if (step.label !== "turn" || event.kind !== "server_message") {
                return step;
            }
            const { bk: _bank, ...raw } = event.raw;
            return { ...step, event: { ...event, raw } };
        });
        const scenario = { ...OWN_TURN_SCENARIO, steps: noBank };

        expect(stateAt(scenario, runClean(scenario), "turn").decision?.deadline).toBeNull();
    });
});
