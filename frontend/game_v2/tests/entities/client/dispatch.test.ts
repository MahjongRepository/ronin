import { describe, expect, it } from "vitest";

import { clientEvent, clientScenario, forbiddingIo } from "#tests/fixtures/scenario";
import {
    WIRE_DRAW,
    WIRE_GAME_END,
    WIRE_GAME_JOINED,
    WIRE_GAME_RECONNECTED,
    WIRE_GAME_STARTED,
    WIRE_ROUND_STARTED,
    wireRoundAdvanceSnapshot,
    wireRoundEnd,
} from "#tests/fixtures/wire";
import {
    type ClientEffect,
    type LiveClient,
    type LiveEvent,
    RESYNC_ANSWER_MS,
    desyncOf,
    nextDeadline,
    roundConfirmOf,
    stepGameClient,
    takesIntent,
} from "@/entities/client";
import { CALLOUT_MS } from "@/entities/table";
import { buildConfirmRoundAction, buildResyncMessage } from "@/shared/protocol";

const { closed, confirm, message, opened, tick } = clientEvent;

function collectEffects(events: readonly LiveEvent[]): {
    effects: ClientEffect[];
    deadline: number | null;
} {
    const scenario = clientScenario();
    const effects: ClientEffect[] = [...scenario.startEffects];
    for (const event of events) {
        effects.push(...scenario.step(event));
    }
    return { deadline: nextDeadline(scenario.state), effects };
}

function socketError(at: number): LiveEvent {
    return { at, detail: "", kind: "transport_error" };
}

/** What `event` asks for at the connect deadline of a socket that never opened. */
function connectTimeoutEffects(event: (at: number) => LiveEvent): readonly ClientEffect[] {
    const { state } = clientScenario();
    return stepGameClient(state, event(nextDeadline(state) ?? 0)).effects;
}

/** What a socket error asks for once the resync request of a client that lost step at 5000 comes due. */
function resyncDueEffects(state: LiveClient): readonly ClientEffect[] {
    const desynced = stepGameClient(state, message(5000, { t: 999 })).state;
    return stepGameClient(desynced, socketError(5000 + RESYNC_ANSWER_MS)).effects;
}

function playingScenario(): ReturnType<typeof clientScenario> {
    const scenario = clientScenario();
    scenario.step(opened(0));
    scenario.step(message(0, WIRE_GAME_JOINED));
    scenario.step(message(0, WIRE_GAME_STARTED));
    scenario.step(message(0, WIRE_ROUND_STARTED));
    return scenario;
}

describe("stepGameClient - round confirm", () => {
    it("confirms a round end by its wait id once, on the player's intent, never on its own", () => {
        const scenario = playingScenario();
        const roundEnd = message(100, wireRoundEnd(5));
        const sent = { message: buildConfirmRoundAction(5), type: "send" } as const;

        expect([scenario.step(roundEnd), nextDeadline(scenario.state)]).toEqual([
            [],
            100 + CALLOUT_MS,
        ]);
        expect(scenario.step(tick(60_000))).toEqual([]);
        expect(scenario.step(confirm(60_100))).toEqual([sent]);
        expect(roundConfirmOf(scenario.state)).toEqual({ deadline: null, kind: "sent", waitId: 5 });
        expect(scenario.step(confirm(60_200))).toEqual([]);
    });

    it("closes the round confirm when the server deals the next round, so a late press sends nothing", () => {
        const scenario = playingScenario();
        scenario.step(message(100, wireRoundEnd(5)));

        scenario.step(message(600, WIRE_ROUND_STARTED));
        expect([roundConfirmOf(scenario.state), scenario.state.table.phase]).toEqual([
            null,
            "in_round",
        ]);
        expect(scenario.step(confirm(700))).toEqual([]);
    });

    it("drops an owed confirm with the socket, so a press sends nothing and only the retry is due", () => {
        const scenario = playingScenario();
        scenario.step(message(100, wireRoundEnd(5)));

        expect(scenario.step(closed(500, 1006))).toEqual([]);
        expect(scenario.step(confirm(600))).toEqual([]);
        expect(nextDeadline(scenario.state)).toBe(1500);
    });

    it("owes the confirm a reconnect's snapshot names, untimed when the snapshot says nothing of its timer, and keeps it sent when a second snapshot repeats its wait", () => {
        const scenario = clientScenario();
        scenario.step(opened(0));
        const owed = wireRoundAdvanceSnapshot(true, 9);

        expect(scenario.step(message(100, owed))).toEqual([]);
        expect(scenario.state.table.phase).toBe("round_ended");
        expect(roundConfirmOf(scenario.state)).toEqual({ deadline: null, kind: "owed", waitId: 9 });
        expect(scenario.step(confirm(200))).toEqual([
            { message: buildConfirmRoundAction(9), type: "send" },
        ]);
        expect(scenario.step(message(300, owed))).toEqual([]);
        expect(roundConfirmOf(scenario.state)).toEqual({ deadline: null, kind: "sent", waitId: 9 });
        expect(scenario.step(confirm(400))).toEqual([]);
    });

    it("waits for the others when a reconnect's snapshot of a round advance owes no confirm", () => {
        const scenario = clientScenario();
        scenario.step(opened(0));
        const confirmed = wireRoundAdvanceSnapshot(false, 9);

        scenario.step(message(100, confirmed));
        expect(roundConfirmOf(scenario.state)).toEqual({ kind: "confirmed" });
        expect(scenario.step(confirm(200))).toEqual([]);
    });
});

describe("stepGameClient", () => {
    it("keeps the furiten last reported to the seat until a new deal clears it", () => {
        const scenario = playingScenario();
        function furitenAfter(event: LiveEvent): boolean {
            scenario.step(event);
            return scenario.state.furiten;
        }
        const roundEnd = message(250, wireRoundEnd(5));

        expect([
            furitenAfter(message(100, { f: true, t: 11 })),
            furitenAfter(message(200, WIRE_DRAW)),
            furitenAfter(roundEnd),
            furitenAfter(message(300, WIRE_ROUND_STARTED)),
        ]).toEqual([true, true, true, false]);
    });

    it("reports a message it cannot parse and leaves the session as it was", () => {
        const scenario = playingScenario();
        const { session } = scenario.state;

        const [report] = scenario.step(message(100, { t: 99 }));
        expect(report?.type).toBe("report_protocol_failure");
        expect(scenario.state.session).toBe(session);
    });

    it("ends a game no round result preceded on its standings alone, and takes no server message after it, so the table stays as the game's end left it", () => {
        const scenario = playingScenario();
        scenario.step(message(100, WIRE_GAME_END));
        const ended = scenario.state;
        expect(roundConfirmOf(ended)).toBeNull();
        expect(takesIntent(ended, { type: "show_last_result" })).toBe(false);

        expect(scenario.step(message(200, WIRE_ROUND_STARTED))).toEqual([]);
        expect(scenario.step(message(300, { t: 99 }))).toEqual([]);
        expect(scenario.state.table).toBe(ended.table);
        expect([scenario.state.table.phase, desyncOf(scenario.state)?.unreadMessages ?? 0]).toEqual(
            ["game_ended", desyncOf(ended)?.unreadMessages ?? 0],
        );
    });

    it("takes a valid event it otherwise ignores as advancing the time and settling expiry and resync, while only a tick drives the session's deadlines", () => {
        const scenario = playingScenario();
        const before = scenario.state;
        const ignored: LiveEvent[] = [
            tick(500),
            socketError(600),
            { at: 700, intent: { type: "pass" }, kind: "intent" },
            confirm(800),
        ];

        expect(ignored.map((event) => scenario.step(event))).toEqual([[], [], [], []]);
        expect([scenario.state, before.now]).toEqual([{ ...before, now: 800 }, 0]);
        scenario.step(message(1000, wireRoundEnd(5)));
        const called = scenario.state;
        scenario.step(socketError(1000 + CALLOUT_MS));
        expect([called.calls === null, scenario.state]).toEqual([
            false,
            { ...called, calls: null, now: 1000 + CALLOUT_MS },
        ]);
        expect([
            connectTimeoutEffects(tick),
            connectTimeoutEffects(socketError),
            resyncDueEffects(scenario.state),
        ]).toEqual([
            [{ type: "close_socket" }],
            [],
            [{ message: buildResyncMessage(), type: "send" }],
        ]);
    });

    it("runs no IO and reads no clock: every socket, storage and navigation effect is only described", () => {
        const { calls, result } = forbiddingIo(() =>
            collectEffects([
                opened(0),
                message(5, WIRE_GAME_JOINED),
                message(10, WIRE_GAME_STARTED),
                message(15, WIRE_ROUND_STARTED),
                message(20, wireRoundEnd(5)),
                closed(30, 1006),
                tick(1030),
                opened(1100),
                message(1200, WIRE_GAME_RECONNECTED),
                message(1300, WIRE_DRAW),
                closed(1500, 4002),
            ]),
        );

        expect(calls).toEqual([0, 0, 0, 0]);
        expect(result.effects.map((effect) => effect.type)).toEqual([
            "open_socket",
            "send",
            "open_socket",
            "send",
            "clear_handoff",
        ]);
        expect(result.deadline).toBeNull();
    });
});
