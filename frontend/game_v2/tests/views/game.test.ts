import { describe, expect, it, vi } from "vitest";

import { GAME_ID, HANDOFF } from "#tests/fixtures/scenario";
import { loadSeatScenario, receivedThrough } from "#tests/fixtures/seat-transcripts";
import { WIRE_GAME_END, WIRE_GAME_STARTED, wireSessionError } from "#tests/fixtures/wire";
import { type Clock } from "@/shared/clock";
import {
    type ClientMessage,
    buildConfirmRoundAction,
    buildDiscardAction,
    buildJoinGameMessage,
    buildPassAction,
    buildReconnectMessage,
} from "@/shared/protocol";
import { type GameConnection, type SocketHandlers } from "@/shared/websocket";
import { type GameViewDeps, mountGameView } from "@/views/game";

class FakeConnection implements GameConnection {
    readonly sent: ClientMessage[] = [];
    disconnected = false;

    constructor(
        readonly url: string,
        readonly handlers: SocketHandlers,
    ) {}

    send(message: ClientMessage): void {
        this.sent.push(message);
    }

    disconnect(): void {
        this.disconnected = true;
    }
}

interface ManualTimer {
    readonly at: number;
    readonly callback: () => void;
    cancelled: boolean;
}

/** A clock moved by hand; `timers` keeps every callback, cancelled ones too, so a test can fire a stale one. */
class ManualClock implements Clock {
    readonly timers: ManualTimer[] = [];
    private current = 0;

    now = (): number => this.current;

    setTimer = (delayMs: number, callback: () => void): (() => void) => {
        const timer: ManualTimer = { at: this.current + delayMs, callback, cancelled: false };
        this.timers.push(timer);
        return () => {
            timer.cancelled = true;
        };
    };

    advanceTo(at: number): void {
        this.current = at;
        for (const timer of this.timers.filter((t) => !t.cancelled && t.at <= at)) {
            timer.cancelled = true;
            timer.callback();
        }
    }
}

interface FakeOverrides {
    readonly connect?: GameViewDeps["connect"];
    readonly debug?: boolean;
    readonly leaveToLobby?: () => void;
}

function mountWithFakes(overrides: FakeOverrides = {}): {
    clock: ManualClock;
    connections: FakeConnection[];
    host: HTMLElement;
    sink: GameViewDeps["sink"];
    dispose: () => void;
} {
    const clock = new ManualClock();
    const connections: FakeConnection[] = [];
    const sink = { clearHandoff: vi.fn(), leaveToLobby: vi.fn(overrides.leaveToLobby) };
    const host = document.createElement("div");
    function fakeConnect(url: string, handlers: SocketHandlers): FakeConnection {
        const connection = new FakeConnection(url, handlers);
        connections.push(connection);
        return connection;
    }
    const dispose = mountGameView(host, GAME_ID, {
        clock,
        connect: overrides.connect ?? fakeConnect,
        debug: overrides.debug ?? false,
        handoff: HANDOFF,
        sink,
    });
    return { clock, connections, dispose, host, sink };
}

/** Join a game that already started, then get told to retry the RECONNECT later. */
function waitOutRetryLater(socket: FakeConnection): void {
    socket.handlers.onOpen();
    socket.handlers.onMessage(wireSessionError("join_game_already_started"));
    socket.handlers.onMessage(wireSessionError("reconnect_retry_later"));
}

/** Join, then receive what the generated call prompt scenario's seat did up to its prompt (a 5 s meld timer). */
function openCallPrompt(socket: FakeConnection): void {
    const { transcript } = loadSeatScenario("call_prompt_seat_1");
    socket.handlers.onOpen();
    for (const payload of receivedThrough(transcript, "prompt")) {
        socket.handlers.onMessage(payload);
    }
}

/** Join, then receive the call prompt scenario's messages through its turn after the chi (kuikae blocks 3m). */
function openKuikaeTurn(socket: FakeConnection): void {
    const { transcript } = loadSeatScenario("call_prompt_seat_1");
    socket.handlers.onOpen();
    for (const payload of receivedThrough(transcript, "turn")) {
        socket.handlers.onMessage(payload);
    }
}

function press(host: HTMLElement, selector: string): void {
    const element = host.querySelector(`.game__play ${selector}`);
    if (element === null) {
        throw new Error(`nothing matches ${selector}`);
    }
    element.dispatchEvent(new MouseEvent("click", { bubbles: true }));
}

function secondsLeft(host: HTMLElement): string | null | undefined {
    return host.querySelector(".game__rotate .rotate-panel__seconds")?.textContent;
}

const JOIN = buildJoinGameMessage(HANDOFF.gameTicket);
/** The first tile of the turn's hand that kuikae lets go, 4m, and the turn's wait id. */
const FIRST_FREE_TILE = 12;
const TURN_WAIT_ID = 2;
const PROMPT_WAIT_ID = 1;
const ROUND_END_WAIT_ID = 2;
const RECONNECT = buildReconnectMessage(HANDOFF.gameTicket);

describe("mountGameView", () => {
    it("joins on the handoff's socket and renders the session status and, under debug, the message log", () => {
        const { connections, host } = mountWithFakes({ debug: true });
        const [socket] = connections;
        expect(socket.url).toBe(HANDOFF.wsUrl);

        socket.handlers.onOpen();
        socket.handlers.onMessage(WIRE_GAME_STARTED);

        expect(socket.sent).toEqual([JOIN]);
        expect(host.querySelector(".game-aside__status")?.textContent).toBe("Connected");
        expect(host.querySelector(".log-entry:last-child .log-type")?.textContent).toBe(
            "game_started",
        );
        expect(host.querySelector(".log-entry.log-sent .log-raw")?.textContent).toBe(
            JSON.stringify(JOIN, null, 2),
        );
    });

    it("counts the open prompt down on the rotate panel as the clock reaches each second, sending nothing", () => {
        const { clock, connections, host } = mountWithFakes();
        openCallPrompt(connections[0]);

        const shown = [0, 999, 1000, 2000, 3000, 4000].map((at) => {
            clock.advanceTo(at);
            return secondsLeft(host);
        });
        clock.advanceTo(5000);

        expect(shown).toEqual(["5", "5", "4", "3", "2", "1"]);
        expect(host.querySelector(".game__rotate .rotate-panel__decision--expired")).not.toBeNull();
        expect(connections[0].sent).toEqual([JOIN]);
    });

    it("reopens a dropped socket when its retry comes due and resumes the seat on it", () => {
        const { clock, connections } = mountWithFakes();
        connections[0].handlers.onOpen();
        connections[0].handlers.onMessage(WIRE_GAME_STARTED);

        connections[0].handlers.onClose(1006, "");
        clock.advanceTo(999);
        expect(connections).toHaveLength(1);
        clock.advanceTo(1000);
        expect(connections).toHaveLength(2);

        connections[1].handlers.onOpen();
        expect(connections[1].sent).toEqual([RECONNECT]);
    });

    it("lets no retry callback reopen a socket after dispose", () => {
        const { clock, connections, dispose, host } = mountWithFakes();
        connections[0].handlers.onOpen();
        connections[0].handlers.onClose(1006, "");
        const [retry] = clock.timers;

        dispose();
        retry.callback();

        expect([retry.cancelled, connections.length, host.childElementCount]).toEqual([true, 1, 0]);
    });

    it("lets no retry callback resend RECONNECT after a terminal close", () => {
        const { clock, connections, sink } = mountWithFakes();
        const [socket] = connections;
        waitOutRetryLater(socket);
        const [retry] = clock.timers;

        socket.handlers.onClose(4002, "replaced_by_new_connection");
        retry.callback();

        expect([retry.cancelled, socket.sent, connections.length]).toEqual([
            true,
            [JOIN, RECONNECT],
            1,
        ]);
        expect(sink.clearHandoff).toHaveBeenCalledExactlyOnceWith(GAME_ID);
        expect(sink.leaveToLobby).toHaveBeenCalledOnce();
    });

    it("on Back to Lobby after the game ended closes the socket, clears the handoff and leaves", () => {
        const { connections, host, sink } = mountWithFakes();
        connections[0].handlers.onOpen();
        connections[0].handlers.onMessage(WIRE_GAME_STARTED);
        connections[0].handlers.onMessage(WIRE_GAME_END);

        host.querySelector("button")?.click();

        expect(connections[0].disconnected).toBe(true);
        expect(sink.clearHandoff).toHaveBeenCalledExactlyOnceWith(GAME_ID);
        expect(sink.leaveToLobby).toHaveBeenCalledOnce();
    });

    it("treats a socket factory that throws as a failed connection and retries it", () => {
        const { clock, connections, host } = mountWithFakes({
            connect: (url, handlers) => {
                if (clock.now() === 0) {
                    throw new Error("refused URL");
                }
                const connection = new FakeConnection(url, handlers);
                connections.push(connection);
                return connection;
            },
            debug: true,
        });
        expect(host.querySelector(".log-entry .log-raw")?.textContent).toContain("connect_failed");

        clock.advanceTo(1000);

        expect(connections).toHaveLength(1);
    });

    it("ends as failed, shown on the page, when running an effect throws, and keeps taking input", () => {
        const leaveToLobby = vi.fn(() => {
            throw new Error("navigation blocked");
        });
        const { connections, host } = mountWithFakes({ leaveToLobby });
        connections[0].handlers.onOpen();

        connections[0].handlers.onMessage(wireSessionError("reconnect_no_session"));
        expect(host.querySelector(".game-aside__status")?.textContent).toBe("Something went wrong");

        host.querySelector("button")?.click();
        expect(leaveToLobby).toHaveBeenCalledTimes(2);
    });

    it("reports a server message it cannot read on the console and the page, without the debug log", () => {
        const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
        const { connections, host } = mountWithFakes();
        connections[0].handlers.onOpen();

        connections[0].handlers.onMessage({ t: 999 });

        expect(consoleError).toHaveBeenCalledOnce();
        expect(host.querySelector(".game-aside__warning")?.textContent).toContain(
            "1 server message(s) could not be read",
        );
        expect(host.querySelector(".log-entry")).toBeNull();
        consoleError.mockRestore();
    });

    it("ignores a late callback from a socket it already replaced", () => {
        const { clock, connections } = mountWithFakes();
        const [first] = connections;
        first.handlers.onClose(1006, "");
        clock.advanceTo(1000);

        first.handlers.onClose(1006, "");

        expect(clock.timers.filter((timer) => !timer.cancelled)).toEqual([]);
    });
});

describe("mountGameView board", () => {
    it("sends one discard with the turn's wait id for a tapped tile, and nothing for a kuikae-blocked one or a second tap", () => {
        const { connections, host } = mountWithFakes();
        openKuikaeTurn(connections[0]);

        for (const tile of ["disabled", "selectable", "selected"]) {
            press(host, `.board-local .hand-tile--${tile}`);
        }

        expect(connections[0].sent).toEqual([
            JOIN,
            buildDiscardAction(FIRST_FREE_TILE, TURN_WAIT_ID),
        ]);
        expect(
            host.querySelectorAll('.game__play button.hand-tile:not([aria-disabled="true"])'),
        ).toHaveLength(0);
    });

    it("pages a double ron with Next, sends one confirm on OK, then waits for the others, counting down", () => {
        const { connections, host } = mountWithFakes();
        const { transcript } = loadSeatScenario("double_ron_seat_1");
        connections[0].handlers.onOpen();
        for (const payload of receivedThrough(transcript, "round end")) {
            connections[0].handlers.onMessage(payload);
        }

        const labels = [0, 1].map(() => {
            const label = host.querySelector(
                ".game__play .round-end-result__confirm-label",
            )?.textContent;
            press(host, ".round-end-result__confirm");
            return label?.trim();
        });

        expect(labels).toEqual(["Next", "OK"]);
        expect(connections[0].sent).toEqual([JOIN, buildConfirmRoundAction(ROUND_END_WAIT_ID)]);
        expect(host.querySelector(".game__play .round-end-result__confirm")).toBeNull();
        expect([
            host.querySelector(".game__play .round-end-result__waiting")?.textContent,
            host.querySelector(".game__play .round-end-result__countdown")?.textContent,
        ]).toEqual(["Waiting for others", expect.stringMatching(/^\d+s left$/)]);
    });

    it("sends a pass with the prompt's wait id when the call prompt's Pass is pressed", () => {
        const { connections, host } = mountWithFakes();
        openCallPrompt(connections[0]);

        press(host, ".decision-controls__action.secondary");

        expect(connections[0].sent).toEqual([JOIN, buildPassAction(PROMPT_WAIT_ID)]);
    });
});
