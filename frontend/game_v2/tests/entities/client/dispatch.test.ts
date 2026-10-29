import { describe, expect, it } from "vitest";

import { clientEvent, clientScenario, forbiddingIo } from "#tests/fixtures/scenario";
import {
    WIRE_DRAW,
    WIRE_GAME_RECONNECTED,
    WIRE_GAME_STARTED,
    WIRE_ROUND_STARTED,
    wireRoundEnd,
} from "#tests/fixtures/wire";
import { type ClientEffect, type ClientEvent, nextDeadline } from "@/entities/client";
import { buildConfirmRoundAction } from "@/shared/protocol";

const { closed, message, opened, tick } = clientEvent;

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

describe("stepGameClient", () => {
    it("confirms a round end by its wait id once a second has passed", () => {
        const scenario = playingScenario();

        const roundEnd = message(100, wireRoundEnd(5));
        expect(scenario.step(roundEnd)).toEqual([]);
        expect(nextDeadline(scenario.state)).toBe(1100);
        expect(scenario.step(tick(1099))).toEqual([]);
        expect(scenario.step(tick(1100))).toEqual([
            { message: buildConfirmRoundAction(5), type: "send" },
        ]);
        expect(nextDeadline(scenario.state)).toBeNull();
    });

    it("confirms nothing for the game's last round end, which carries no wait id", () => {
        const scenario = playingScenario();

        const lastRoundEnd = message(100, wireRoundEnd(null));
        expect(scenario.step(lastRoundEnd)).toEqual([]);
        expect(nextDeadline(scenario.state)).toBeNull();
    });

    it("drops a pending confirm once the next round starts, so its due tick sends nothing", () => {
        const scenario = playingScenario();
        scenario.step(message(100, wireRoundEnd(5)));

        expect(scenario.step(message(600, WIRE_ROUND_STARTED))).toEqual([]);
        expect(nextDeadline(scenario.state)).toBeNull();
        expect(scenario.step(tick(1100))).toEqual([]);
    });

    it("drops a pending confirm when the socket drops, so only the retry is due", () => {
        const scenario = playingScenario();
        scenario.step(message(100, wireRoundEnd(5)));

        expect(scenario.step(closed(500, 1006))).toEqual([]);
        expect(nextDeadline(scenario.state)).toBe(1500);
        expect(scenario.step(tick(1100))).toEqual([]);
    });

    it("confirms by the snapshot's wait id a round advance a reconnect says the seat still owes", () => {
        const scenario = clientScenario();
        scenario.step(opened(0));
        const owed = { ...WIRE_GAME_RECONNECTED, oc: true, re: wireRoundEnd(null), wi: 9 };

        expect(scenario.step(message(100, owed))).toEqual([]);
        expect(scenario.state.table.phase).toBe("round_ended");
        expect(scenario.step(tick(1100))).toEqual([
            { message: buildConfirmRoundAction(9), type: "send" },
        ]);
    });

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
        expect(report?.type).toBe("report_parse_error");
        expect(scenario.state.session).toBe(session);
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
            "redirect_to_lobby",
        ]);
        expect(result.deadline).toBeNull();
    });
});
