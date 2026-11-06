import { describe, expect, it } from "vitest";

import { clientEvent, clientScenario, forbiddingIo } from "#tests/fixtures/scenario";
import { checkpointState } from "#tests/fixtures/seat-transcripts";
import {
    WIRE_DRAW,
    WIRE_GAME_END,
    WIRE_GAME_JOINED,
    WIRE_GAME_RECONNECTED,
    WIRE_GAME_STARTED,
    WIRE_ROUND_STARTED,
    type WirePayload,
    wirePayloadList,
    wireRoundAdvanceSnapshot,
    wireRoundEnd,
    wireSessionError,
    wireStartConfirmDeal,
    wireStartConfirmSnapshot,
} from "#tests/fixtures/wire";
import {
    type ClientEffect,
    type LiveClient,
    type LiveEvent,
    NO_PLAY_UI,
    RESYNC_ANSWER_MS,
    decisionOf,
    desyncOf,
    nextDeadline,
    playDisplay,
    roundConfirmOf,
    stepGameClient,
    takesIntent,
} from "@/entities/client";
import { WIN_CALLOUT_CONTEXT_MS } from "@/entities/client/model/calls";
import {
    SESSION_ERROR_CODE,
    WIRE_KEY,
    buildConfirmRoundAction,
    buildResyncMessage,
} from "@/shared/protocol";

const { closed, confirm, confirmOpening, message, opened, tick } = clientEvent;

/** The seating the live board shows over its table: its heading's round, and each seat's name, wind and score. */
function shownSeating(state: LiveClient): readonly unknown[] | null {
    const panel = playDisplay(state, NO_PLAY_UI).overlay?.panel;
    if (panel?.kind !== "seating") {
        return null;
    }
    const seats = panel.display.seats.map(({ name, score, wind }) => [wind, name, score]);
    return [panel.display.gameType, panel.display.round, seats];
}

/** A snapshot of East 2 with one honba, dealt by seat 1 though seat 0 dealt first, the scores moved from the start. */
const WIRE_SECOND_DEALER_SNAPSHOT: WirePayload = {
    ...WIRE_GAME_RECONNECTED,
    [WIRE_KEY.DEALER]: 1,
    [WIRE_KEY.HONBA]: 1,
    [WIRE_KEY.PLAYER_STATES]: wirePayloadList(WIRE_GAME_RECONNECTED, WIRE_KEY.PLAYER_STATES).map(
        (seat, index) => ({ ...seat, [WIRE_KEY.SCORE]: 280 - index * 10 }),
    ),
};

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
    const desynced = stepGameClient(state, message(5000, { [WIRE_KEY.EVENT_TYPE]: 999 })).state;
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
            100 + WIN_CALLOUT_CONTEXT_MS,
        ]);
        expect(scenario.step(tick(60_000))).toEqual([]);
        expect(scenario.step(confirm(60_100))).toEqual([sent]);
        expect(roundConfirmOf(scenario.state)).toEqual({
            deadline: 100 + 15_000,
            kind: "sent",
            waitId: 5,
        });
        expect(scenario.step(confirm(60_200))).toEqual([]);
    });

    it("times the confirm by the timeout the round end names, never by the timer settings and the result's pages", () => {
        const scenario = playingScenario();
        scenario.step(message(100, wireRoundEnd(5, 7)));

        expect(roundConfirmOf(scenario.state)).toEqual({
            deadline: 100 + 7000,
            kind: "owed",
            waitId: 5,
        });
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

/** The seat's own first draw, the dealer's, opening its turn after the start confirm on wait id 1. */
const WIRE_FIRST_DRAW: WirePayload = { ...WIRE_DRAW, [WIRE_KEY.WAIT_ID]: 2 };

/** A seat the server awaits at the game's start: the game start, then the first deal owing the start confirm on wait 1. */
function startConfirmScenario(): ReturnType<typeof clientScenario> {
    const scenario = clientScenario();
    scenario.step(opened(0));
    scenario.step(message(0, WIRE_GAME_JOINED));
    scenario.step(message(0, WIRE_GAME_STARTED));
    scenario.step(message(0, wireStartConfirmDeal(1)));
    return scenario;
}

function openingControlsOf(state: LiveClient): unknown {
    const { opening } = playDisplay(state, NO_PLAY_UI);
    return opening === null ? null : { ...opening, action: opening.action?.label ?? null };
}

describe("stepGameClient - opening screen", () => {
    it("shows the start screen from the game start over the first deal, owing the start confirm it names, and closes both on the first draw, never at the confirm's deadline", () => {
        const scenario = startConfirmScenario();
        const seating = shownSeating(scenario.state);

        expect([
            scenario.state.opening,
            roundConfirmOf(scenario.state),
            nextDeadline(scenario.state),
        ]).toEqual([
            { cause: "start", kind: "showing" },
            { deadline: 10_000, kind: "owed", waitId: 1 },
            null,
        ]);
        expect(seating).toEqual([
            "Hanchan",
            "East 1",
            [
                ["E", "P0", "25,000"],
                ["S", "P1", "25,000"],
                ["W", "P2", "25,000"],
                ["N", "P3", "25,000"],
            ],
        ]);
        expect([scenario.step(tick(12_000)), shownSeating(scenario.state)]).toEqual([[], seating]);
        expect(openingControlsOf(scenario.state)).toEqual({
            action: "OK",
            secondsLeft: 0,
            waiting: false,
        });
        scenario.step(message(12_100, WIRE_FIRST_DRAW));
        expect([
            scenario.state.opening,
            shownSeating(scenario.state),
            decisionOf(scenario.state)?.waitId,
        ]).toEqual([{ kind: "closed" }, null, 2]);
    });

    it("sends the start confirm on the OK once by its wait id, then waits for the others with its time still counting, and a refusal naming it reopens the OK", () => {
        const scenario = startConfirmScenario();

        expect(scenario.step(confirmOpening(1000))).toEqual([
            { message: buildConfirmRoundAction(1), type: "send" },
        ]);
        expect([openingControlsOf(scenario.state), scenario.step(confirmOpening(1100))]).toEqual([
            { action: null, secondsLeft: 9, waiting: true },
            [],
        ]);
        expect(scenario.step(confirm(1200))).toEqual([]);
        scenario.step(message(1300, wireSessionError(SESSION_ERROR_CODE.RATE_LIMITED, 1)));
        expect([roundConfirmOf(scenario.state), openingControlsOf(scenario.state)]).toEqual([
            { deadline: 10_000, kind: "owed", waitId: 1 },
            { action: "OK", secondsLeft: 9, waiting: false },
        ]);
    });

    it("closes the start screen on the OK of a seat the first deal awaits no confirm of, sending nothing, and opens none on a reconnect after it", () => {
        const scenario = playingScenario();

        expect(scenario.step(confirmOpening(1000))).toEqual([]);
        expect([
            scenario.state.opening,
            takesIntent(scenario.state, { type: "confirm_opening" }),
        ]).toEqual([{ kind: "closed" }, false]);
        scenario.step(closed(4000, 1006));
        scenario.step(tick(5000));
        scenario.step(opened(5000));
        scenario.step(message(5100, WIRE_GAME_RECONNECTED));
        expect([scenario.state.notice?.kind, shownSeating(scenario.state)]).toEqual([
            "reconnected",
            null,
        ]);
    });

    it("shows the start screen on a fresh page's snapshot of the start confirm, the OK owed on the time the server's elapsed time leaves, or waiting once the seat confirmed", () => {
        const owed = clientScenario();
        owed.step(opened(0));
        owed.step(message(100, wireStartConfirmSnapshot(true, 4, 3)));
        const confirmed = clientScenario();
        confirmed.step(opened(0));
        confirmed.step(message(100, wireStartConfirmSnapshot(false, 4, 0)));

        expect([owed.state.opening, roundConfirmOf(owed.state)]).toEqual([
            { cause: "start", kind: "showing" },
            { deadline: 7100, kind: "owed", waitId: 4 },
        ]);
        expect(owed.step(confirmOpening(200))).toEqual([
            { message: buildConfirmRoundAction(4), type: "send" },
        ]);
        expect([confirmed.state.opening, openingControlsOf(confirmed.state)]).toEqual([
            { cause: "start", kind: "showing" },
            { action: null, secondsLeft: null, waiting: true },
        ]);
    });

    it("opens the resume screen on a fresh page's first snapshot with the game type, round, dealer and scores now, for its own time, and not on a second reconnect", () => {
        const scenario = clientScenario();
        scenario.step(opened(0));
        scenario.step(message(100, WIRE_SECOND_DEALER_SNAPSHOT));

        expect([shownSeating(scenario.state), nextDeadline(scenario.state)]).toEqual([
            [
                "Hanchan",
                "East 2, 1 honba",
                [
                    ["E", "P2", "27,000"],
                    ["S", "B1", "26,000"],
                    ["W", "B2", "25,000"],
                    ["N", "P1", "28,000"],
                ],
            ],
            5100,
        ]);
        scenario.step(tick(5100));
        scenario.step(closed(6000, 1006));
        scenario.step(tick(7000));
        scenario.step(opened(7000));
        scenario.step(message(7100, WIRE_SECOND_DEALER_SNAPSHOT));
        expect([scenario.state.notice?.kind, shownSeating(scenario.state)]).toEqual([
            "reconnected",
            null,
        ]);
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
            furitenAfter(message(100, { [WIRE_KEY.FURITEN]: true, [WIRE_KEY.EVENT_TYPE]: 11 })),
            furitenAfter(message(200, WIRE_DRAW)),
            furitenAfter(roundEnd),
            furitenAfter(message(300, WIRE_ROUND_STARTED)),
        ]).toEqual([true, true, true, false]);
    });

    it("reports a message it cannot parse and leaves the session as it was", () => {
        const scenario = playingScenario();
        const { session } = scenario.state;

        const [report] = scenario.step(message(100, { [WIRE_KEY.EVENT_TYPE]: 99 }));
        expect(report?.type).toBe("report_protocol_failure");
        expect(scenario.state.session).toBe(session);
    });

    it("ends a game no round result preceded on its final scores alone, and takes no server message after it, so the table stays as the game's end left it", () => {
        const scenario = playingScenario();
        scenario.step(message(100, WIRE_GAME_END));
        const ended = scenario.state;
        expect(roundConfirmOf(ended)).toBeNull();
        expect(takesIntent(ended, { type: "show_last_result" })).toBe(false);

        expect(scenario.step(message(200, WIRE_ROUND_STARTED))).toEqual([]);
        expect(scenario.step(message(300, { [WIRE_KEY.EVENT_TYPE]: 99 }))).toEqual([]);
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
        scenario.step(socketError(1000 + WIN_CALLOUT_CONTEXT_MS));
        expect([called.calls === null, scenario.state]).toEqual([
            false,
            { ...called, calls: null, now: 1000 + WIN_CALLOUT_CONTEXT_MS },
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

    it("never runs its logical time back for an event stamped before it, as after a wall clock stepped back an hour", () => {
        const onTurn = checkpointState("own_turn_seat_1", "first draw");
        const decision = decisionOf(onTurn);
        const stepped = stepGameClient(onTurn, socketError(onTurn.now - 3_600_000)).state;

        expect(stepped.now).toBe(onTurn.now);
        expect(decisionOf(stepped)).toEqual(decision);
        expect(nextDeadline(stepped)).toBe(nextDeadline(onTurn));
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
