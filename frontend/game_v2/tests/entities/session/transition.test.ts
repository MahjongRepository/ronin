import { describe, expect, it } from "vitest";

import { HANDOFF, sessionInput, sessionScenario } from "#tests/fixtures/scenario";
import {
    WIRE_GAME_END,
    WIRE_GAME_RECONNECTED,
    WIRE_GAME_STARTED,
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

type SessionScenario = ReturnType<typeof sessionScenario>;

function playing(): SessionScenario {
    const scenario = sessionScenario();
    scenario.step(opened(0));
    scenario.step(message(0, WIRE_GAME_STARTED));
    return scenario;
}

/** A session told at join that the game already started, so it has sent RECONNECT on the open socket. */
function resumingAtJoin(): SessionScenario {
    const scenario = sessionScenario();
    scenario.step(opened(0));
    scenario.step(message(0, wireSessionError("join_game_already_started")));
    return scenario;
}

/** A session waiting out a `reconnect_retry_later` due at 1000. */
function waitingOutRetryLater(): SessionScenario {
    const scenario = resumingAtJoin();
    scenario.step(message(0, wireSessionError("reconnect_retry_later")));
    return scenario;
}

function pendingDeadline(scenario: SessionScenario): number {
    const deadline = sessionDeadline(scenario.state);
    if (deadline === null) {
        throw new Error("no retry is pending");
    }
    return deadline;
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
        expect(scenario.state).toMatchObject({
            attempts: { session: 0, transport: 0 },
            link: "open",
            status: "playing",
        });
    });

    describe("retries", () => {
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

        it("closes a socket that has not opened 10 s after it was asked for and retries it like a drop", () => {
            const scenario = playing();
            scenario.step(dropped(100));
            expect(scenario.step(tick(1100))).toEqual([OPEN]);
            expect(sessionDeadline(scenario.state)).toBe(11_100);

            const steps = [tick(11_099), tick(11_100)].map((input) => scenario.step(input));
            expect(steps).toEqual([[], [{ type: "close_socket" }]]);
            expect(scenario.state).toMatchObject({ link: "down", status: "reconnecting" });
            expect(sessionDeadline(scenario.state)).toBe(13_100);
            expect([scenario.step(tick(13_100)), scenario.step(opened(13_200))]).toEqual([
                [OPEN],
                [RECONNECT],
            ]);
            expect(sessionDeadline(scenario.state)).toBeNull();
        });

        it("retries a 1000 close when no game end arrived, so the server's answer to RECONNECT decides", () => {
            const scenario = playing();

            expect(scenario.step(closed(100, 1000))).toEqual([]);
            expect(sessionDeadline(scenario.state)).toBe(1100);
        });

        it("resends JOIN_GAME on the open socket after a rate limit while joining", () => {
            const scenario = sessionScenario();
            scenario.step(opened(0));

            const rateLimited = message(10, wireSessionError("rate_limited"));
            expect(scenario.step(rateLimited)).toEqual([]);
            expect(scenario.step(tick(1010))).toEqual([JOIN]);
        });

        it("keeps its seat and schedules nothing on a rate limit or a reconnect_retry_later while playing", () => {
            const scenario = playing();

            const rateLimited = message(10, wireSessionError("rate_limited"));
            expect(scenario.step(rateLimited)).toEqual([]);
            expect(scenario.step(retryLater(20))).toEqual([]);
            expect(scenario.state).toMatchObject({ link: "open", retry: null, status: "playing" });
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

        it.each(["reconnect_no_session", "internal_error"])(
            "closes the socket, forgets the handoff and stays on the page on a %s refusal",
            (code) => {
                const scenario = sessionScenario();
                scenario.step(opened(0));

                const refusal = message(10, wireSessionError(code));
                expect(scenario.step(refusal)).toEqual([{ type: "close_socket" }, FORGET_HANDOFF]);
                expect(scenario.state).toMatchObject({ reason: { code, kind: "refused" } });
            },
        );

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

        const found = recovered(200, {
            gameClientUrl: "/play",
            gameId: "g1",
            handoff: HANDOFF,
            kind: "found",
        });
        expect(scenario.step(found)).toEqual([
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
