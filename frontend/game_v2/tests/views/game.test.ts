import { describe, expect, it, onTestFinished, vi } from "vitest";

import { GAME_ID, HANDOFF } from "#tests/fixtures/scenario";
import { loadSeatScenario, receivedThrough } from "#tests/fixtures/seat-transcripts";
import { WIRE_GAME_END, WIRE_GAME_STARTED, wireSessionError } from "#tests/fixtures/wire";
import { type HandoffRecovery } from "@/shared/api";
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

    /** The timer armed last, which a test fires by hand after it was replaced or cancelled. */
    lastTimer(): ManualTimer {
        const timer = this.timers.at(-1);
        if (timer === undefined) {
            throw new Error("no timer was armed");
        }
        return timer;
    }

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
    readonly clearHandoff?: () => void;
    readonly handoff?: GameViewDeps["handoff"];
    readonly recoverHandoff?: GameViewDeps["recoverHandoff"];
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
    const sink = {
        clearHandoff: vi.fn(overrides.clearHandoff),
        leaveToLobby: vi.fn(),
        openGame: vi.fn(),
        reload: vi.fn(),
        storeHandoff: vi.fn(),
    };
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
        handoff: overrides.handoff === undefined ? HANDOFF : overrides.handoff,
        recoverHandoff:
            overrides.recoverHandoff ??
            (() => Promise.reject(new Error("the tab holds a handoff"))),
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
        const retry = clock.lastTimer();

        dispose();
        retry.callback();

        expect([retry.cancelled, connections.length, host.childElementCount]).toEqual([true, 1, 0]);
    });

    it("lets no retry callback resend RECONNECT after a terminal close", () => {
        const { clock, connections, sink } = mountWithFakes();
        const [socket] = connections;
        waitOutRetryLater(socket);
        const retry = clock.lastTimer();

        socket.handlers.onClose(4002, "replaced_by_new_connection");
        retry.callback();

        expect([retry.cancelled, socket.sent, connections.length]).toEqual([
            true,
            [JOIN, RECONNECT],
            1,
        ]);
        expect(sink.clearHandoff).toHaveBeenCalledExactlyOnceWith(GAME_ID);
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
        const { connections, host, sink } = mountWithFakes({
            clearHandoff: () => {
                throw new Error("storage blocked");
            },
        });
        connections[0].handlers.onOpen();

        connections[0].handlers.onMessage(wireSessionError("reconnect_no_session"));
        expect(host.querySelector(".game-aside__status")?.textContent).toBe("Something went wrong");

        press(host, ".failure-panel__reload");
        host.querySelector<HTMLElement>(".game__rotate .failure-panel__leave")?.click();
        expect(sink.reload).toHaveBeenCalledOnce();
        expect(sink.clearHandoff).toHaveBeenCalledTimes(2);
    });

    it("reports a server message it cannot read on the console and the board, without the debug log", () => {
        const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
        const { connections, host } = mountWithFakes();
        connections[0].handlers.onOpen();

        connections[0].handlers.onMessage({ t: 999 });

        expect(consoleError).toHaveBeenCalledOnce();
        expect(host.querySelector(".game__play .board-notice--error")?.textContent).toBe(
            "A server message could not be read; the table may be wrong",
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

        const armed = clock.timers.filter((timer) => !timer.cancelled).map((timer) => timer.at);
        expect(armed).toEqual([11_000]);
    });
});

describe("mountGameView connection", () => {
    it("gives up on a socket that never opens after 10 s and opens another on the retry", () => {
        const { clock, connections, host } = mountWithFakes();

        clock.advanceTo(9999);
        expect(connections[0].disconnected).toBe(false);
        clock.advanceTo(10_000);
        expect(connections[0].disconnected).toBe(true);
        expect(host.querySelector(".game__play .board-notice")?.textContent).toBe(
            "Cannot reach the game. Retrying…",
        );
        clock.advanceTo(11_000);

        expect(connections).toHaveLength(2);
    });

    it("shows a dropped connection on the board while it reconnects", () => {
        const { connections, host } = mountWithFakes();
        connections[0].handlers.onOpen();
        connections[0].handlers.onMessage(WIRE_GAME_STARTED);

        connections[0].handlers.onClose(1006, "");

        expect(host.querySelector(".game__play .board-notice--warning")?.textContent).toBe(
            "Connection lost. Reconnecting…",
        );
    });

    it("blocks the board with why a terminal close ended the session, and leaves only on its button", () => {
        const { connections, host, sink } = mountWithFakes();
        connections[0].handlers.onOpen();
        connections[0].handlers.onMessage(WIRE_GAME_STARTED);

        connections[0].handlers.onClose(4002, "replaced_by_new_connection");
        expect(sink.leaveToLobby).not.toHaveBeenCalled();
        const titles = [".game__play", ".game__rotate"].map(
            (place) => host.querySelector(`${place} .failure-panel__title`)?.textContent,
        );
        expect(titles).toEqual(["Opened elsewhere", "Opened elsewhere"]);

        press(host, ".failure-panel__leave");
        expect(sink.leaveToLobby).toHaveBeenCalledOnce();
    });
});

/** A lobby answer the test settles by hand, keeping the signal the view asked with. */
class PendingLookup {
    signal: AbortSignal | null = null;
    private resolve: (recovery: HandoffRecovery) => void = () => {};
    private readonly answer = new Promise<HandoffRecovery>((done) => {
        this.resolve = done;
    });

    readonly recoverHandoff = (signal: AbortSignal): Promise<HandoffRecovery> => {
        this.signal = signal;
        return this.answer;
    };

    async settle(recovery: HandoffRecovery): Promise<void> {
        this.resolve(recovery);
        await this.answer;
        await Promise.resolve();
    }
}

const OTHER_HANDOFF = { gameTicket: "ticket-2", wsUrl: "ws://game/ws/g2" } as const;

/** Let a lookup the view started settle and its answer reach the dispatcher. */
async function settleLookup(): Promise<void> {
    await Promise.resolve();
    await Promise.resolve();
}

describe("mountGameView handoff recovery", () => {
    it("asks the lobby when the tab holds no handoff, keeps the one it finds and joins with it", async () => {
        const lobby = new PendingLookup();
        const { connections, host, sink } = mountWithFakes({
            handoff: null,
            recoverHandoff: lobby.recoverHandoff,
        });
        expect(connections).toHaveLength(0);
        expect(host.querySelector(".game__play .board-notice")?.textContent).toBe(
            "Finding your game…",
        );

        await lobby.settle({
            gameClientUrl: "/play",
            gameId: GAME_ID,
            handoff: HANDOFF,
            kind: "found",
        });
        connections[0].handlers.onOpen();

        expect(sink.storeHandoff).toHaveBeenCalledExactlyOnceWith(GAME_ID, HANDOFF);
        expect(connections[0].url).toBe(HANDOFF.wsUrl);
        expect(connections[0].sent).toEqual([JOIN]);
    });

    it("goes to the lobby when the player plays no game", async () => {
        const lobby = new PendingLookup();
        const { sink } = mountWithFakes({ handoff: null, recoverHandoff: lobby.recoverHandoff });

        await lobby.settle({ kind: "missing" });

        expect(sink.leaveToLobby).toHaveBeenCalledOnce();
    });

    it("goes to the page of the game the player plays when it is another one", async () => {
        const lobby = new PendingLookup();
        const { connections, sink } = mountWithFakes({
            handoff: null,
            recoverHandoff: lobby.recoverHandoff,
        });

        await lobby.settle({
            gameClientUrl: "/play",
            gameId: "g2",
            handoff: OTHER_HANDOFF,
            kind: "found",
        });

        expect(sink.storeHandoff).toHaveBeenCalledExactlyOnceWith("g2", OTHER_HANDOFF);
        expect(sink.openGame).toHaveBeenCalledExactlyOnceWith("g2", "/play");
        expect(connections).toHaveLength(0);
        expect(sink.leaveToLobby).not.toHaveBeenCalled();
    });

    it("asks the lobby once more after a failed lookup, then stays on the page with a reload", async () => {
        const recoverHandoff = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
        const { clock, host, sink } = mountWithFakes({ handoff: null, recoverHandoff });
        await settleLookup();
        expect(host.querySelector(".game__play .board-notice")?.textContent).toBe(
            "Finding your game…",
        );

        clock.advanceTo(2000);
        await settleLookup();

        expect(recoverHandoff).toHaveBeenCalledTimes(2);
        expect(host.querySelector(".game__play .failure-panel__title")?.textContent).toBe(
            "Can't reach the lobby",
        );
        press(host, ".failure-panel__reload");
        expect(sink.reload).toHaveBeenCalledOnce();
    });

    it("cancels the lookup on dispose and drops its late answer", async () => {
        const lobby = new PendingLookup();
        const { connections, dispose, sink } = mountWithFakes({
            handoff: null,
            recoverHandoff: lobby.recoverHandoff,
        });

        dispose();
        await lobby.settle({
            gameClientUrl: "/play",
            gameId: GAME_ID,
            handoff: HANDOFF,
            kind: "found",
        });

        expect(lobby.signal?.aborted).toBe(true);
        expect(connections).toHaveLength(0);
        expect(sink.storeHandoff).not.toHaveBeenCalled();
    });
});

/** Mount into the document, where focus works, at the call prompt; the test's end disposes it and takes it out. */
function mountInDocumentAtCallPrompt(): {
    connections: FakeConnection[];
    host: HTMLElement;
    lobby: HTMLElement;
} {
    const { connections, dispose, host } = mountWithFakes();
    document.body.append(host);
    onTestFinished(() => {
        dispose();
        host.remove();
    });
    openCallPrompt(connections[0]);
    const lobby = host.querySelector<HTMLElement>(".game__play .game-aside__leave");
    if (lobby === null) {
        throw new Error("no Lobby button");
    }
    return { connections, host, lobby };
}

/** Whether the board and the aside under the leave question are inert. */
function inertAreas(host: HTMLElement): (boolean | undefined)[] {
    return [".board-layout", ".game-aside"].map((selector) =>
        host.querySelector(`.game__play ${selector}`)?.hasAttribute("inert"),
    );
}

describe("mountGameView leaving", () => {
    it("asks before handing a held seat to an AI, and Stay takes the question back, leaving nothing", () => {
        const { connections, host, sink } = mountWithFakes();
        openCallPrompt(connections[0]);

        press(host, ".game-aside__leave");
        expect(host.querySelector(".game__play .leave-confirm__detail")?.textContent).toBe(
            "An AI will play your seat.",
        );
        press(host, ".leave-confirm__stay");

        expect(host.querySelector(".game__play .leave-confirm")).toBeNull();
        expect(host.querySelector(".game__play .decision-controls__action")).not.toBeNull();
        expect(connections[0].disconnected).toBe(false);
        expect(sink.leaveToLobby).not.toHaveBeenCalled();
    });

    it("closes the socket and leaves for the lobby once the player confirms leaving", () => {
        const { connections, host, sink } = mountWithFakes();
        openCallPrompt(connections[0]);

        press(host, ".game-aside__leave");
        press(host, ".leave-confirm__leave");

        expect(connections[0].disconnected).toBe(true);
        expect(sink.leaveToLobby).toHaveBeenCalledOnce();
    });

    it("asks on the rotate panel too, in place of its way back", () => {
        const { connections, host } = mountWithFakes();
        openCallPrompt(connections[0]);

        host.querySelector<HTMLElement>(".game__rotate .rotate-panel__leave")?.click();

        expect(host.querySelector(".game__rotate .leave-confirm")).not.toBeNull();
        expect(host.querySelector<HTMLElement>(".game__rotate .rotate-panel__leave")?.hidden).toBe(
            true,
        );
    });

    it("keeps the question modal: Stay takes the focus, the page under it is inert, and Escape stays and refocuses Lobby", async () => {
        const { connections, host, lobby } = mountInDocumentAtCallPrompt();
        lobby.focus();

        lobby.click();
        await Promise.resolve();
        const opened = [inertAreas(host), document.activeElement?.className];
        document.activeElement?.dispatchEvent(
            new KeyboardEvent("keydown", { bubbles: true, key: "Escape" }),
        );
        const closed = [
            inertAreas(host),
            host.querySelector(".game__play .leave-confirm"),
            document.activeElement === lobby,
            connections[0].disconnected,
        ];

        expect(opened).toEqual([[true, true], "leave-confirm__stay"]);
        expect(closed).toEqual([[false, false], null, true, false]);
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
