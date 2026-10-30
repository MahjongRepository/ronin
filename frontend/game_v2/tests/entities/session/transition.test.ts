import { describe, expect, it } from "vitest";

import { HANDOFF, sessionInput, sessionScenario } from "#tests/fixtures/scenario";
import {
    WIRE_DRAW,
    WIRE_GAME_END,
    WIRE_GAME_RECONNECTED,
    WIRE_GAME_STARTED,
    WIRE_SEAT_TO_AI,
    wireGameError,
    wireSessionError,
} from "#tests/fixtures/wire";
import { type SessionEffect, type SessionInput, sessionDeadline } from "@/entities/session";
import { buildJoinGameMessage, buildReconnectMessage } from "@/shared/protocol";

const { closed, leave, message, opened, recovered, tick } = sessionInput;

const JOIN = { message: buildJoinGameMessage(HANDOFF.gameTicket), type: "send" } as const;
const RECONNECT = { message: buildReconnectMessage(HANDOFF.gameTicket), type: "send" } as const;
const OPEN = { type: "open_socket", url: HANDOFF.wsUrl } as const;
const FORGET_HANDOFF = { gameId: "g1", type: "clear_handoff" } as const;
const LEAVE_FOR_LOBBY = [FORGET_HANDOFF, { type: "redirect_to_lobby" }] as const;
const FOUND = {
    gameClientUrl: "/play",
    gameId: "g1",
    handoff: HANDOFF,
    kind: "found",
} as const;

type SessionScenario = ReturnType<typeof sessionScenario>;

function joining(): SessionScenario {
    const scenario = sessionScenario();
    scenario.step(opened(0));
    return scenario;
}

function playing(): SessionScenario {
    const scenario = joining();
    scenario.step(message(0, WIRE_GAME_STARTED));
    return scenario;
}

/** A session told at join that the game already started, so it has sent RECONNECT on the open socket. */
function resumingAtJoin(): SessionScenario {
    const scenario = joining();
    scenario.step(message(0, wireSessionError("join_game_already_started")));
    return scenario;
}

/** A session waiting out a `reconnect_retry_later` due at 1000. */
function waitingOutRetryLater(): SessionScenario {
    const scenario = resumingAtJoin();
    scenario.step(message(0, wireSessionError("reconnect_retry_later")));
    return scenario;
}

/** A session that held its seat and lost it to a drop at 100, its socket due to reopen at 1100. */
function awaitingRetry(): SessionScenario {
    const scenario = playing();
    scenario.step(closed(100, 1006));
    return scenario;
}

function pendingDeadline(scenario: SessionScenario): number {
    const deadline = sessionDeadline(scenario.state);
    if (deadline === null) {
        throw new Error("no retry is pending");
    }
    return deadline;
}

function deadlineAfter(scenario: SessionScenario, inputs: readonly SessionInput[]): number {
    for (const input of inputs) {
        scenario.step(input);
    }
    return pendingDeadline(scenario);
}

/**
 * Raise `cause` at each retry's due time, `times` times, check what each due tick does, and return the delays
 * the session waited and the time of the last due tick.
 */
function backOff(
    scenario: SessionScenario,
    times: number,
    { cause, onDue }: { cause: (at: number) => SessionInput; onDue: readonly SessionEffect[] },
): { delays: number[]; now: number } {
    const delays: number[] = [];
    let now = 0;
    for (let attempt = 1; attempt <= times; attempt++) {
        expect(scenario.step(cause(now))).toEqual([]);
        const deadline = pendingDeadline(scenario);
        delays.push(deadline - now);
        now = deadline;
        expect(scenario.step(tick(now))).toEqual(onDue);
    }
    return { delays, now };
}

function retryLater(at: number): SessionInput {
    return message(at, wireSessionError("reconnect_retry_later"));
}

function dropped(at: number): SessionInput {
    return closed(at, 1006);
}

describe("stepSession", () => {
    it("joins with JOIN_GAME, plays from the first game event, and resumes with RECONNECT after a drop", () => {
        const scenario = sessionScenario();
        const effects = [
            opened(0),
            message(10, WIRE_GAME_STARTED),
            closed(100, 1006),
            tick(1099),
            tick(1100),
            opened(1200),
            message(1300, WIRE_GAME_RECONNECTED),
        ].map((input) => scenario.step(input));

        expect([scenario.startEffects, ...effects]).toEqual([
            [OPEN],
            [JOIN],
            [],
            [],
            [],
            [OPEN],
            [RECONNECT],
            [],
        ]);
    });

    it("leaves every input a state has no rule for as it is, emitting nothing", () => {
        const cases: readonly [string, () => SessionScenario, SessionInput][] = [
            ["a recovering session's socket opening", () => sessionScenario(null), opened(10)],
            ["a recovering session's socket closing", () => sessionScenario(null), dropped(10)],
            [
                "a recovering session's server message",
                () => sessionScenario(null),
                message(10, WIRE_DRAW),
            ],
            ["a second open of an open socket", joining, opened(10)],
            ["an open on a playing session", playing, opened(10)],
            ["an open with no socket asked for", awaitingRetry, opened(200)],
            ["a second close of a dropped socket", awaitingRetry, closed(200, 4002)],
            ["a message while the socket opens", sessionScenario, message(10, WIRE_GAME_END)],
            ["a message with no socket", awaitingRetry, message(200, WIRE_GAME_RECONNECTED)],
            ["the lobby's answer while identifying", joining, recovered(10, FOUND)],
            ["the lobby's answer while playing", playing, recovered(10, FOUND)],
        ];

        const moved = cases.filter(([, build, input]) => {
            const scenario = build();
            const before = scenario.state;
            return scenario.step(input).length > 0 || scenario.state !== before;
        });
        expect(moved.map(([name]) => name)).toEqual([]);
    });

    describe("connecting", () => {
        it("closes a socket that has not opened 10 s after it was asked for and retries it like a drop", () => {
            const scenario = awaitingRetry();
            expect(scenario.step(tick(1100))).toEqual([OPEN]);
            expect(sessionDeadline(scenario.state)).toBe(11_100);

            const steps = [tick(11_099), tick(11_100)].map((input) => scenario.step(input));
            expect(steps).toEqual([[], [{ type: "close_socket" }]]);
            expect(scenario.state).toMatchObject({
                identity: { kind: "reconnect", lostSeat: true },
                status: "awaiting_retry",
            });
            expect(sessionDeadline(scenario.state)).toBe(13_100);
            expect([scenario.step(tick(13_100)), scenario.step(opened(13_200))]).toEqual([
                [OPEN],
                [RECONNECT],
            ]);
            expect(sessionDeadline(scenario.state)).toBeNull();
        });
    });

    describe("identifying", () => {
        it("is admitted while joining by any message the game sends the seat, a game error included, but not by a seat's change of control", () => {
            const scenario = joining();

            expect(scenario.step(message(10, WIRE_SEAT_TO_AI))).toEqual([]);
            expect(scenario.state).toMatchObject({ status: "identifying" });
            const gameError = message(20, wireGameError("not_your_turn", 1));
            expect(scenario.step(gameError)).toEqual([]);
            expect(scenario.state).toMatchObject({ status: "playing" });
        });

        it("turns JOIN_GAME into RECONNECT on join_game_already_started only while joining", () => {
            const scenario = joining();
            const alreadyStarted = message(10, wireSessionError("join_game_already_started"));

            expect(scenario.step(alreadyStarted)).toEqual([RECONNECT]);
            expect(scenario.state).toMatchObject({
                identity: { kind: "reconnect", lostSeat: false },
                status: "identifying",
            });
            expect(scenario.step({ ...alreadyStarted, at: 20 })).toEqual([]);
            scenario.step(message(30, WIRE_GAME_RECONNECTED));
            expect(scenario.step({ ...alreadyStarted, at: 40 })).toEqual([]);
            expect(scenario.state).toMatchObject({ status: "playing" });
        });

        it("resends RECONNECT on the open socket after each reconnect_retry_later, backing off to 15 s, and gives up after 15 tries", () => {
            const scenario = resumingAtJoin();

            const { delays, now } = backOff(scenario, 15, {
                cause: retryLater,
                onDue: [RECONNECT],
            });

            expect(delays).toEqual([
                1000,
                2000,
                4000,
                8000,
                ...Array.from({ length: 11 }, () => 15_000),
            ]);
            expect(scenario.step(retryLater(now))).toEqual([
                { type: "close_socket" },
                FORGET_HANDOFF,
            ]);
            expect(scenario.state).toMatchObject({
                reason: { gameStarted: true, kind: "retries_exhausted", retry: "session" },
            });
        });

        it.each([
            { build: joining, identity: JOIN, name: "joining" },
            { build: resumingAtJoin, identity: RECONNECT, name: "reconnecting" },
        ] as const)(
            "resends its identity message on the open socket after a rate limit while $name",
            ({ build, identity }) => {
                const scenario = build();

                const rateLimited = message(10, wireSessionError("rate_limited"));
                expect(scenario.step(rateLimited)).toEqual([]);
                expect(scenario.step(tick(1009))).toEqual([]);
                expect(scenario.step(tick(1010))).toEqual([identity]);
            },
        );

        it.each(["reconnect_no_session", "internal_error"])(
            "closes the socket, forgets the handoff and stays on the page on a %s refusal",
            (code) => {
                const scenario = joining();

                const refusal = message(10, wireSessionError(code));
                expect(scenario.step(refusal)).toEqual([{ type: "close_socket" }, FORGET_HANDOFF]);
                expect(scenario.state).toMatchObject({ reason: { code, kind: "refused" } });
            },
        );
    });

    describe("playing", () => {
        it("keeps its seat and schedules nothing on a rate limit or a reconnect_retry_later", () => {
            const scenario = playing();
            const held = scenario.state;

            const rateLimited = message(10, wireSessionError("rate_limited"));
            expect(scenario.step(rateLimited)).toEqual([]);
            expect(scenario.step(retryLater(20))).toEqual([]);
            expect(scenario.state).toBe(held);
        });

        it("retries a 1000 close when no game end arrived, so the server's answer to RECONNECT decides", () => {
            const scenario = playing();

            expect(scenario.step(closed(100, 1000))).toEqual([]);
            expect(sessionDeadline(scenario.state)).toBe(1100);
        });
    });

    describe("awaiting a transport retry", () => {
        it("starts its backoff over once the seat is held again, so the next drop waits the first step's 1 s", () => {
            const scenario = awaitingRetry();

            const deadlines = [
                deadlineAfter(scenario, []),
                deadlineAfter(scenario, [tick(1100), dropped(1200)]),
                deadlineAfter(scenario, [
                    tick(3200),
                    opened(3300),
                    message(3400, WIRE_GAME_RECONNECTED),
                    dropped(3500),
                ]),
            ];
            expect(deadlines).toEqual([1100, 3200, 4500]);
        });

        it("replaces a session retry with a transport retry on a drop, whose reopened socket resends RECONNECT", () => {
            const scenario = waitingOutRetryLater();

            expect(scenario.step(closed(200, 1006))).toEqual([]);
            expect(sessionDeadline(scenario.state)).toBe(1200);
            expect(scenario.step(tick(1000))).toEqual([]);
            expect(scenario.step(tick(1200))).toEqual([OPEN]);
            expect(scenario.step(opened(1300))).toEqual([RECONNECT]);
        });

        it("reopens a socket that keeps dropping, backing off to 30 s, and gives up on the page after 10 tries", () => {
            const scenario = sessionScenario();

            const { delays, now } = backOff(scenario, 10, { cause: dropped, onDue: [OPEN] });

            expect(delays).toEqual([
                1000, 2000, 4000, 8000, 16_000, 30_000, 30_000, 30_000, 30_000, 30_000,
            ]);
            expect(scenario.step(dropped(now))).toEqual([FORGET_HANDOFF]);
            expect(scenario.state).toMatchObject({
                reason: { gameStarted: false, kind: "retries_exhausted", retry: "transport" },
            });
        });
    });

    describe("ends", () => {
        it.each([4002, 1008])(
            "on a %i close drops the pending retry, forgets the handoff, stays on the page and ignores all but a leave",
            (code) => {
                const scenario = waitingOutRetryLater();
                expect(sessionDeadline(scenario.state)).toBe(1000);

                expect(scenario.step(closed(500, code))).toEqual([FORGET_HANDOFF]);
                expect(sessionDeadline(scenario.state)).toBeNull();
                expect(scenario.step(tick(1000))).toEqual([]);
                expect(scenario.step(opened(1100))).toEqual([]);
                expect(scenario.state).toMatchObject({
                    reason: { code, kind: "closed" },
                    status: "ended",
                });
                expect(scenario.step(leave(1200))).toEqual([
                    { type: "close_socket" },
                    { type: "redirect_to_lobby" },
                ]);
            },
        );

        it("forgets the handoff and stays on the page at the game end, ignores the server's 1000 close after it, and still leaves on request", () => {
            const scenario = playing();

            expect(scenario.step(message(100, WIRE_GAME_END))).toEqual([FORGET_HANDOFF]);
            expect(scenario.state).toMatchObject({
                reason: { kind: "game_ended" },
                status: "ended",
            });
            expect(scenario.step(closed(200, 1000))).toEqual([]);
            expect(scenario.step(leave(300))).toEqual([
                { type: "close_socket" },
                { type: "redirect_to_lobby" },
            ]);
            expect(scenario.step(leave(400))).toEqual([]);
        });

        it("on leaving drops the pending retry, closes the socket and leaves for the lobby", () => {
            const scenario = waitingOutRetryLater();

            expect(scenario.step(leave(300))).toEqual([
                { type: "close_socket" },
                ...LEAVE_FOR_LOBBY,
            ]);
            expect(sessionDeadline(scenario.state)).toBeNull();
        });
    });
});

describe("handoff recovery", () => {
    const OTHER_HANDOFF = { gameTicket: "ticket-2", wsUrl: "ws://game/ws/g2" } as const;

    it("asks the lobby for the game when the tab holds no handoff, then keeps the one it finds and joins with it", () => {
        const scenario = sessionScenario(null);
        expect(scenario.startEffects).toEqual([{ type: "recover_handoff" }]);
        expect(scenario.step(tick(100))).toEqual([]);

        expect(scenario.step(recovered(200, FOUND))).toEqual([
            { gameId: "g1", handoff: HANDOFF, type: "store_handoff" },
            OPEN,
        ]);
        expect(sessionDeadline(scenario.state)).toBe(10_200);
        expect(scenario.step(opened(300))).toEqual([JOIN]);
    });

    it("keeps another game's handoff and goes to that game's page", () => {
        const scenario = sessionScenario(null);

        const found = recovered(200, {
            gameClientUrl: "/play",
            gameId: "g2",
            handoff: OTHER_HANDOFF,
            kind: "found",
        });
        expect(scenario.step(found)).toEqual([
            { gameId: "g2", handoff: OTHER_HANDOFF, type: "store_handoff" },
            { gameClientUrl: "/play", gameId: "g2", type: "redirect_to_game" },
        ]);
        expect(scenario.step(leave(300))).toEqual([]);
    });

    it("leaves for the lobby when the player plays no game", () => {
        const scenario = sessionScenario(null);

        expect(scenario.step(recovered(200, { kind: "missing" }))).toEqual(LEAVE_FOR_LOBBY);
        expect(scenario.state).toMatchObject({ reason: { kind: "no_handoff" }, status: "ended" });
    });

    it("asks the lobby again 2 s after a failed lookup, stays on the page once that fails too, and leaves on request", () => {
        const scenario = sessionScenario(null);
        const failed = recovered(200, { detail: "HTTP 503", kind: "failed" });

        expect(scenario.step(failed)).toEqual([]);
        expect(sessionDeadline(scenario.state)).toBe(2200);
        expect([scenario.step(tick(2199)), scenario.step(tick(2200))]).toEqual([
            [],
            [{ type: "recover_handoff" }],
        ]);
        expect(scenario.step({ ...failed, at: 2300 })).toEqual([]);
        expect(scenario.state).toMatchObject({ reason: { kind: "recovery_failed" } });
        expect(scenario.step(leave(2400))).toEqual([{ type: "close_socket" }, ...LEAVE_FOR_LOBBY]);
    });
});
