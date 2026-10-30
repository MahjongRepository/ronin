import { describe, expect, it } from "vitest";

import { clientEvent, clientScenario, forbiddingIo } from "#tests/fixtures/scenario";
import {
    WIRE_DRAW,
    WIRE_GAME_END,
    WIRE_GAME_RECONNECTED,
    WIRE_GAME_STARTED,
    WIRE_ROUND_STARTED,
    wireRoundEnd,
} from "#tests/fixtures/wire";
import { type ClientEffect, type ClientEvent, nextDeadline } from "@/entities/client";
import { CALLOUT_MS } from "@/entities/table";
import { buildConfirmRoundAction } from "@/shared/protocol";

const { closed, confirm, message, opened, tick } = clientEvent;

function collectEffects(events: readonly ClientEvent[]): {
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

function playingScenario(): ReturnType<typeof clientScenario> {
    const scenario = clientScenario();
    scenario.step(opened(0));
    scenario.step(message(0, WIRE_GAME_STARTED));
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
        expect(scenario.state.roundConfirm).toEqual({ deadline: null, kind: "sent", waitId: 5 });
        expect(scenario.step(confirm(60_200))).toEqual([]);
    });

    it("closes the round confirm when the server deals the next round, so a late press sends nothing", () => {
        const scenario = playingScenario();
        scenario.step(message(100, wireRoundEnd(5)));

        scenario.step(message(600, WIRE_ROUND_STARTED));
        expect([scenario.state.roundConfirm, scenario.state.table.phase]).toEqual([
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

    it("owes the confirm a reconnect's snapshot names, untimed when the snapshot says nothing of its timer", () => {
        const scenario = clientScenario();
        scenario.step(opened(0));
        const owed = { ...WIRE_GAME_RECONNECTED, oc: true, re: wireRoundEnd(null), wi: 9 };

        expect(scenario.step(message(100, owed))).toEqual([]);
        expect(scenario.state.table.phase).toBe("round_ended");
        expect(scenario.state.roundConfirm).toEqual({ deadline: null, kind: "owed", waitId: 9 });
        expect(scenario.step(confirm(200))).toEqual([
            { message: buildConfirmRoundAction(9), type: "send" },
        ]);
    });

    it("waits for the others when a reconnect's snapshot of a round advance owes no confirm", () => {
        const scenario = clientScenario();
        scenario.step(opened(0));
        const confirmed = { ...WIRE_GAME_RECONNECTED, oc: false, re: wireRoundEnd(null), wi: 9 };

        scenario.step(message(100, confirmed));
        expect(scenario.state.roundConfirm).toEqual({ kind: "confirmed" });
        expect(scenario.step(confirm(200))).toEqual([]);
    });
});

describe("stepGameClient", () => {
    it("keeps the furiten last reported to the seat until a new deal clears it", () => {
        const scenario = playingScenario();
        function furitenAfter(event: ClientEvent): boolean {
            scenario.step(event);
            return scenario.state.furiten;
        }

        expect([
            furitenAfter(message(100, { f: true, t: 11 })),
            furitenAfter(message(200, WIRE_DRAW)),
            furitenAfter(message(300, WIRE_ROUND_STARTED)),
        ]).toEqual([true, true, false]);
    });

    it("reports a message it cannot parse and leaves the session as it was", () => {
        const scenario = playingScenario();
        const { session } = scenario.state;

        const [report] = scenario.step(message(100, { t: 99 }));
        expect(report?.type).toBe("report_protocol_failure");
        expect(scenario.state.session).toBe(session);
    });

    it("takes no server message once its session ended, so the table stays as the game's end left it", () => {
        const scenario = playingScenario();
        scenario.step(message(100, WIRE_GAME_END));
        const ended = scenario.state;

        expect(scenario.step(message(200, WIRE_ROUND_STARTED))).toEqual([]);
        expect(scenario.step(message(300, { t: 99 }))).toEqual([]);
        expect(scenario.state.table).toBe(ended.table);
        expect([scenario.state.table.phase, scenario.state.unreadMessages]).toEqual([
            "game_ended",
            0,
        ]);
    });

    it("keeps the logical time of its last event, so a tick with nothing due changes only the time", () => {
        const scenario = playingScenario();
        const before = scenario.state;

        expect(scenario.step(tick(500))).toEqual([]);
        expect(scenario.state).toEqual({ ...before, now: 500 });
        expect(before.now).toBe(0);
    });

    it("runs no IO and reads no clock: every socket, storage and navigation effect is only described", () => {
        const { calls, result } = forbiddingIo(() =>
            collectEffects([
                opened(0),
                message(10, WIRE_GAME_STARTED),
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
