import { type MockInstance, describe, expect, it, onTestFinished, vi } from "vitest";

import { ManualClock, steadyClockOn } from "#tests/fixtures/clock";
import { fakeLanguageSwitch, resetPageLanguage } from "#tests/fixtures/language";
import { GAME_ID, HANDOFF } from "#tests/fixtures/scenario";
import {
    loadSeatScenario,
    receivedPayload,
    receivedThrough,
} from "#tests/fixtures/seat-transcripts";
import {
    WIRE_GAME_END,
    WIRE_GAME_JOINED,
    WIRE_GAME_STARTED,
    WIRE_ROUND_STARTED,
    wireRoundEnd,
    wireSessionError,
} from "#tests/fixtures/wire";
import {
    AUTO_WIN_SETTING_KEY,
    DEFAULT_AUTO_WIN_SETTING,
    DEFAULT_INPUT_SETTING,
    DEFAULT_MOTION_SETTING,
    INPUT_SETTING_KEY,
    MOTION_SETTING_KEY,
    type SoundCue,
    type SoundSetting,
    readAutoWinSetting,
    readInputSetting,
    readMotionSetting,
} from "@/entities/client";
import { SHORTCUT_SETTLE_MS } from "@/entities/client/ui/play-input";
import { type TileSprite, type TileSpriteStatus } from "@/entities/tile";
import { type HandoffRecovery } from "@/shared/api";
import { localStore } from "@/shared/lib";
import {
    type ClientMessage,
    NUM_TILES,
    WIRE_KEY,
    buildChiAction,
    buildConfirmRoundAction,
    buildDiscardAction,
    buildJoinGameMessage,
    buildPassAction,
    buildReconnectMessage,
    buildResyncMessage,
} from "@/shared/protocol";
import { type GameConnection, type SocketHandlers } from "@/shared/websocket";
import { type BrowserBars, type GameViewDeps, mountGameView } from "@/views/game";

class FakeConnection implements GameConnection {
    readonly sent: ClientMessage[] = [];
    disconnected = false;
    silenceLimitMs: number | null = null;

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

    setSilenceLimit(limitMs: number): void {
        this.silenceLimitMs = limitMs;
    }
}

/** A tile sprite whose load a test moves by hand. */
class FakeTileSprite implements TileSprite {
    private current: TileSpriteStatus = "ready";
    private readonly listeners = new Set<(status: TileSpriteStatus) => void>();

    status = (): TileSpriteStatus => this.current;

    subscribe = (listener: (status: TileSpriteStatus) => void): (() => void) => {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    };

    moveTo(status: TileSpriteStatus): void {
        this.current = status;
        for (const listener of this.listeners) {
            listener(status);
        }
    }
}

class FakeBrowserBars implements BrowserBars {
    private current = false;
    private readonly listeners = new Set<(shown: boolean) => void>();
    readonly enterFullscreen = vi.fn();

    constructor(private readonly fullscreenAvailable: boolean) {}

    canEnterFullscreen = (): boolean => this.fullscreenAvailable;

    shown = (): boolean => this.current;

    subscribe = (listener: (shown: boolean) => void): (() => void) => {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    };

    moveTo(shown: boolean): void {
        this.current = shown;
        for (const listener of this.listeners) {
            listener(shown);
        }
    }
}

interface FakeOverrides {
    readonly canEnterFullscreen?: boolean;
    readonly connect?: GameViewDeps["connect"];
    readonly debug?: boolean;
    readonly clearHandoff?: () => void;
    readonly handoff?: GameViewDeps["handoff"];
    readonly recoverHandoff?: GameViewDeps["recoverHandoff"];
    readonly soundSetting?: SoundSetting;
    readonly inputSetting?: GameViewDeps["inputSetting"];
    readonly motionSetting?: GameViewDeps["motionSetting"];
    readonly autoWinSetting?: GameViewDeps["autoWinSetting"];
    readonly setLanguage?: GameViewDeps["setLanguage"];
}

/** The game's sounds as a test hears them: each cue played, and the setting as this browser would keep it. */
interface FakeSound {
    readonly played: SoundCue[];
    setting: SoundSetting;
}

/** A socket factory that keeps every connection it opens. */
function fakeConnector(): { connections: FakeConnection[]; connect: GameViewDeps["connect"] } {
    const connections: FakeConnection[] = [];
    function connect(url: string, handlers: SocketHandlers): FakeConnection {
        const connection = new FakeConnection(url, handlers);
        connections.push(connection);
        return connection;
    }
    return { connect, connections };
}

function mountWithFakes(overrides: FakeOverrides = {}): {
    browserBars: FakeBrowserBars;
    clock: ManualClock;
    connections: FakeConnection[];
    host: HTMLElement;
    sink: GameViewDeps["sink"];
    sound: FakeSound;
    tileSprite: FakeTileSprite;
    throwOnDraws: (count: number) => void;
    dispose: () => void;
} {
    const clock = new ManualClock();
    const [tileSprite, browserBars] = [
        new FakeTileSprite(),
        new FakeBrowserBars(overrides.canEnterFullscreen ?? false),
    ];
    const draws = { throwing: 0 };
    const { connect, connections } = fakeConnector();
    const sink = {
        clearHandoff: vi.fn(overrides.clearHandoff),
        leaveToLobby: vi.fn(),
        openGame: vi.fn(),
        reload: vi.fn(),
        storeHandoff: vi.fn(),
    };
    const sound: FakeSound = { played: [], setting: overrides.soundSetting ?? { sound_on: true } };
    const host = document.createElement("div");
    const dispose = mountGameView(host, GAME_ID, {
        autoWinSetting: overrides.autoWinSetting ?? {
            load: () => DEFAULT_AUTO_WIN_SETTING,
            save: () => {},
        },
        browserBars,
        clock: steadyClockOn(clock),
        connect: overrides.connect ?? connect,
        debug: overrides.debug ?? false,
        handoff: overrides.handoff === undefined ? HANDOFF : overrides.handoff,
        inputSetting: overrides.inputSetting ?? {
            load: () => DEFAULT_INPUT_SETTING,
            save: () => {},
        },
        links: {
            history: "/history",
            replay: (seat) => {
                if (draws.throwing > 0) {
                    draws.throwing -= 1;
                    throw new Error("the board broke");
                }
                return `/play/history/${GAME_ID}?seat=${String(seat)}`;
            },
        },
        motionSetting: overrides.motionSetting ?? {
            load: () => DEFAULT_MOTION_SETTING,
            save: () => {},
        },
        recoverHandoff:
            overrides.recoverHandoff ??
            (() => Promise.reject(new Error("the tab holds a handoff"))),
        setLanguage: overrides.setLanguage ?? (() => {}),
        sink,
        sound: {
            play: (cue) => sound.played.push(cue),
            setting: {
                load: () => sound.setting,
                save: (setting) => {
                    sound.setting = setting;
                },
            },
        },
        tileSprite,
    });
    /** Make the next `count` draws throw, as a bug the view meets mid-draw would: every draw asks for the replay link. */
    function throwOnDraws(count: number): void {
        draws.throwing = count;
    }
    return {
        browserBars,
        clock,
        connections,
        dispose,
        host,
        sink,
        sound,
        throwOnDraws,
        tileSprite,
    };
}

/** The server's answer to the join, then the game's start. */
function seeGameStart(socket: FakeConnection): void {
    socket.handlers.onMessage(WIRE_GAME_JOINED);
    socket.handlers.onMessage(WIRE_GAME_STARTED);
}

/** Join, see the game start, then its end. */
function endGame(socket: FakeConnection): void {
    socket.handlers.onOpen();
    seeGameStart(socket);
    socket.handlers.onMessage(WIRE_ROUND_STARTED);
    socket.handlers.onMessage(wireRoundEnd(null));
    socket.handlers.onMessage(WIRE_GAME_END);
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

/** Join, then receive the double ron scenario's messages through its round end. */
function openDoubleRonEnd(socket: FakeConnection): void {
    const { transcript } = loadSeatScenario("double_ron_seat_1");
    socket.handlers.onOpen();
    for (const payload of receivedThrough(transcript, "round end")) {
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

function pressKey(host: HTMLElement, selector: string, key: string): void {
    host.querySelector(`.game__play ${selector}`)?.dispatchEvent(
        new KeyboardEvent("keydown", { bubbles: true, key }),
    );
}

/** The decision controls' names, as a screen reader reads them, in their order on the board, after `act`. */
function labelsAfter(host: HTMLElement, act: () => void): (string | null)[] {
    act();
    return [...host.querySelectorAll(".game__play .decision-controls__action")].map((button) =>
        button.getAttribute("aria-label"),
    );
}

function spriteNotice(host: HTMLElement): string | null | undefined {
    return host.querySelector(".game__play .board-notice--warning .board-notice__body")
        ?.textContent;
}

function secondsLeft(host: HTMLElement): string | null | undefined {
    return host.querySelector(".game__rotate .rotate-panel__seconds")?.textContent;
}

const JOIN = buildJoinGameMessage(HANDOFF.gameTicket);
/** The first tile of the turn's hand that kuikae lets go, 4m, and the turn's wait id. */
const FIRST_FREE_TILE = 12;
const TURN_WAIT_ID = 3;
const PROMPT_WAIT_ID = 2;
const FIRST_STEP_CALL = '.decision-controls__action[aria-pressed="false"]';
const ROUND_END_WAIT_ID = 3;
const RECONNECT = buildReconnectMessage(HANDOFF.gameTicket);

describe("mountGameView", () => {
    it("joins on the handoff's socket and renders the session status and, under debug, the message log", () => {
        const { connections, host } = mountWithFakes({ debug: true });
        const [socket] = connections;
        expect(socket.url).toBe(HANDOFF.wsUrl);

        socket.handlers.onOpen();
        seeGameStart(socket);

        expect(socket.sent).toEqual([JOIN]);
        expect(host.querySelector(".game-menu__status-label")?.textContent).toBe("Connected");
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

        const shown = [0, 999, 1000, 5000, 24_000, 24_999].map((at) => {
            clock.advanceTo(at);
            return secondsLeft(host);
        });
        clock.advanceTo(25_000);

        expect(shown).toEqual(["25", "25", "24", "20", "1", "1"]);
        expect(host.querySelector(".game__rotate .rotate-panel__decision--expired")).not.toBeNull();
        expect(connections[0].sent).toEqual([JOIN]);
    });

    it("reopens a dropped socket when its retry comes due and resumes the seat on it", () => {
        const { clock, connections } = mountWithFakes();
        connections[0].handlers.onOpen();
        seeGameStart(connections[0]);

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

    it("clears the handoff at the game end, so a return to the page joins with no dead ticket, and leaves on Back to lobby", () => {
        const { connections, host, sink } = mountWithFakes();
        endGame(connections[0]);
        expect(sink.clearHandoff).toHaveBeenCalledExactlyOnceWith(GAME_ID);

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
        const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
        onTestFinished(() => consoleError.mockRestore());
        const { connections, host, sink } = mountWithFakes({
            clearHandoff: () => {
                throw new Error("storage blocked");
            },
        });
        connections[0].handlers.onOpen();

        connections[0].handlers.onMessage(wireSessionError("reconnect_no_session"));
        expect([
            host.querySelector(".game-menu__status-label")?.textContent,
            host.querySelector(".game-menu__toggle")?.getAttribute("aria-label"),
        ]).toEqual(["Something went wrong", "Settings, Error"]);

        press(host, ".failure-panel__reload");
        host.querySelector<HTMLElement>(".game__rotate .failure-panel__leave")?.click();
        expect(sink.reload).toHaveBeenCalledOnce();
        expect(sink.clearHandoff).toHaveBeenCalledTimes(2);
    });

    it("reports a server message it cannot read on the console and the board, without the debug log, and asks the open socket for a snapshot", () => {
        const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
        const {
            connections: [socket],
            host,
        } = mountWithFakes();
        socket.handlers.onOpen();
        seeGameStart(socket);

        socket.handlers.onMessage({ [WIRE_KEY.EVENT_TYPE]: 999 });
        socket.handlers.onUndecodableFrame("Received a non-binary frame");

        expect(consoleError).toHaveBeenCalledTimes(2);
        expect([
            host.querySelector(".game__play .board-notice--error .board-notice__body")?.textContent,
            host.querySelector(".log-entry"),
        ]).toEqual([
            "The game server sent 2 messages this page could not read, so the table may be wrong until the server sends them again; play goes on.",
            null,
        ]);
        expect([socket.sent, socket.disconnected]).toEqual([[JOIN, buildResyncMessage()], false]);
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

describe("mountGameView round trip", () => {
    it("shows the socket's round trip in the settings menu while connected, and forgets it with the socket", () => {
        const { clock, connections, host } = gameWithMenuOpen();

        connections[0].handlers.onRoundTrip(47.6);
        const connected = roundTrip(host);
        connections[0].handlers.onClose(1006, "");
        const dropped = roundTrip(host);
        clock.advanceTo(1000);
        connections[0].handlers.onRoundTrip(30);
        connections[1].handlers.onOpen();

        expect([connected, dropped, roundTrip(host)]).toEqual(["48 ms", undefined, undefined]);
    });

    it("warns on the cog from a 400 ms round trip on, and not below it", () => {
        const { connections, host } = gameWithMenuOpen();

        connections[0].handlers.onRoundTrip(399);
        const fair = cogLabel(host);
        connections[0].handlers.onRoundTrip(400);

        expect([
            fair,
            cogLabel(host),
            host.querySelectorAll(".game__play .game-menu__alert.status-slow").length,
        ]).toEqual(["Settings", "Settings, Slow connection", 1]);
    });
});

describe("mountGameView tile faces", () => {
    it("tells the player while the tile faces failed to load, with a reload, until a retry loads them", () => {
        const { host, sink, tileSprite } = mountWithFakes();

        const shown = (["retrying", "failed"] as const).map((status) => {
            tileSprite.moveTo(status);
            return spriteNotice(host);
        });
        press(host, ".board-notice__action");
        tileSprite.moveTo("ready");

        const notice = /^Tile images did not load; tiles show their names\s*Reload$/;
        expect(shown).toEqual([expect.stringMatching(notice), expect.stringMatching(notice)]);
        expect(sink.reload).toHaveBeenCalledOnce();
        expect(spriteNotice(host)).toBeUndefined();
    });

    it("shows the way to a larger table while the browser's bars are shown, and drops it as they collapse", () => {
        const { browserBars, host } = mountWithFakes();
        function barsNotice(): string | undefined {
            return host.querySelector(".game__play .board-notice--info .board-notice__body")
                ?.textContent;
        }

        browserBars.moveTo(true);
        const shown = barsNotice();
        browserBars.moveTo(false);

        expect(shown).toMatch(/^Swipe up to hide the browser bars and enlarge the table\s*$/);
        expect(barsNotice()).toBeUndefined();
    });

    it("enters full screen from the bars' notice inside the tap, where the browser can", () => {
        const { browserBars, host } = mountWithFakes({ canEnterFullscreen: true });

        browserBars.moveTo(true);
        host.querySelector<HTMLButtonElement>(".game__play .board-notice__action")?.click();

        expect(browserBars.enterFullscreen).toHaveBeenCalledOnce();
    });
});

function gameWithMenuOpen(): ReturnType<typeof mountWithFakes> {
    const mounted = mountWithFakes();
    mounted.connections[0].handlers.onOpen();
    seeGameStart(mounted.connections[0]);
    press(mounted.host, ".game-menu__toggle");
    return mounted;
}

function cogLabel(host: HTMLElement): string | null | undefined {
    return host.querySelector(".game__play .game-menu__toggle")?.getAttribute("aria-label");
}

function roundTrip(host: HTMLElement): string | null | undefined {
    return host.querySelector(".game__play .game-menu__round-trip")?.textContent;
}

function statusLabel(host: HTMLElement): string | null | undefined {
    return host.querySelector(".game-menu__status-label")?.textContent;
}

function silenceConsoleErrors(): MockInstance<typeof console.error> {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    onTestFinished(() => consoleError.mockRestore());
    return consoleError;
}

describe("mountGameView failure boundary", () => {
    it("ends as failed, with its socket closed, when drawing the state a step left throws, its error on the console", () => {
        const consoleError = silenceConsoleErrors();
        const { connections, host, throwOnDraws } = mountWithFakes();
        connections[0].handlers.onOpen();
        throwOnDraws(1);

        connections[0].handlers.onMessage(WIRE_GAME_JOINED);

        expect([statusLabel(host), connections[0].disconnected]).toEqual([
            "Something went wrong",
            true,
        ]);
        expect(consoleError.mock.calls.map(([text]) => text)).toEqual(["The game page failed:"]);
    });

    it("ends as failed, with its socket closed, when drawing a page command's view change throws", () => {
        silenceConsoleErrors();
        const { connections, host, throwOnDraws } = mountWithFakes();
        openCallPrompt(connections[0]);
        throwOnDraws(1);

        press(host, ".game-menu__toggle");

        expect([statusLabel(host), connections[0].disconnected]).toEqual([
            "Something went wrong",
            true,
        ]);
        expect(host.querySelector(".game__play .game-menu__panel")).toBeNull();
    });

    it("shows a bare notice with a reload, and nothing of the board, when even the failed state cannot be drawn", () => {
        const consoleError = silenceConsoleErrors();
        const { connections, host, sink, throwOnDraws } = mountWithFakes();
        connections[0].handlers.onOpen();
        throwOnDraws(Number.POSITIVE_INFINITY);

        connections[0].handlers.onMessage(WIRE_GAME_JOINED);
        host.querySelector<HTMLElement>(".game--broken button")?.click();

        expect([
            host.querySelector(".game--broken")?.textContent?.trim(),
            host.querySelector(".game-board"),
            connections[0].disconnected,
            vi.mocked(sink.reload).mock.calls.length,
        ]).toEqual([
            expect.stringMatching(/^The game page ran into an error\.\s*Reload$/),
            null,
            true,
            1,
        ]);
        expect(consoleError.mock.calls.map(([text]) => text)).toEqual([
            "The game page failed:",
            "The failed game page could not be drawn:",
        ]);
    });

    it("ends as failed, shown on the page with its socket closed, when a load's redraw throws", () => {
        const consoleError = silenceConsoleErrors();
        const { connections, host, throwOnDraws, tileSprite } = mountWithFakes();
        connections[0].handlers.onOpen();
        connections[0].handlers.onMessage(WIRE_GAME_JOINED);
        throwOnDraws(1);

        tileSprite.moveTo("ready");

        expect(host.querySelector(".game-menu__status-label")?.textContent).toBe(
            "Something went wrong",
        );
        expect(connections[0].disconnected).toBe(true);
        expect(consoleError.mock.calls.map(([text]) => text)).toEqual(["The game page failed:"]);
    });
});

describe("mountGameView after a sleep", () => {
    it.each([
        ["elapsed time ran through it", (clock: ManualClock) => clock.advanceTo(60_000)],
        [
            "elapsed time paused, as a forward wall step looks",
            (clock: ManualClock) => clock.stepWall(60_000),
        ],
    ])(
        "shows the open prompt expired on the first tick after the device wakes from a sleep past its time (%s)",
        (_sleep, sleep) => {
            const { clock, connections, host } = mountWithFakes();
            openCallPrompt(connections[0]);

            sleep(clock);
            clock.advanceTo(clock.elapsedNow() + 1000);

            expect(
                host.querySelector(".game__rotate .rotate-panel__decision--expired"),
            ).not.toBeNull();
            expect(connections[0].sent).toEqual([JOIN]);
        },
    );
});

describe("mountGameView connection", () => {
    it("sets the socket's silence limit past the longest wait the server names: the pending game's once joined, then the game's timer settings", () => {
        const { connections } = mountWithFakes();
        const [socket] = connections;
        socket.handlers.onOpen();
        const identifying = socket.silenceLimitMs;
        socket.handlers.onMessage({ ...WIRE_GAME_JOINED, [WIRE_KEY.POINTS]: 300 });
        const joined = socket.silenceLimitMs;
        const timer = {
            [WIRE_KEY.BANK_SECONDS]: 120,
            [WIRE_KEY.GAME_START_CONFIRM]: 3,
            [WIRE_KEY.MAX_BANK_SECONDS]: 180,
            [WIRE_KEY.ROUND_ADVANCE_TIMEOUT]: 15,
            [WIRE_KEY.BASE_TURN_SECONDS]: 10,
        };
        socket.handlers.onMessage({
            ...WIRE_GAME_STARTED,
            [WIRE_KEY.SEAT]: 0,
            [WIRE_KEY.TIMER_SETTINGS]: timer,
        });

        expect([identifying, joined, socket.silenceLimitMs]).toEqual([90_000, 325_000, 215_000]);
    });

    it("stamps a close on running time after the wall clock stepped back an hour, so its retry comes due on time", () => {
        const { clock, connections } = mountWithFakes();
        connections[0].handlers.onOpen();
        seeGameStart(connections[0]);

        clock.stepWall(-3_600_000);
        clock.advanceTo(500);
        connections[0].handlers.onClose(1006, "");
        clock.advanceTo(1499);
        expect(connections).toHaveLength(1);
        clock.advanceTo(1500);
        expect(connections).toHaveLength(2);
    });

    it("gives up on a socket that never opens after 10 s and opens another on the retry", () => {
        const { clock, connections, host } = mountWithFakes();

        clock.advanceTo(9999);
        expect(connections[0].disconnected).toBe(false);
        clock.advanceTo(10_000);
        expect(connections[0].disconnected).toBe(true);
        expect(
            host.querySelector(".game__play .board-notice .board-notice__body")?.textContent,
        ).toBe("Cannot reach the game. Retrying…");
        clock.advanceTo(11_000);

        expect(connections).toHaveLength(2);
    });

    it("shows a dropped connection on the board while it reconnects", () => {
        const { connections, host } = mountWithFakes();
        connections[0].handlers.onOpen();
        seeGameStart(connections[0]);

        connections[0].handlers.onClose(1006, "");

        expect(
            host.querySelector(".game__play .board-notice--warning .board-notice__body")
                ?.textContent,
        ).toBe("Connection lost. Reconnecting…");
    });

    it("blocks the board with why a terminal close ended the session, and leaves only on its button", () => {
        const { connections, host, sink } = mountWithFakes();
        connections[0].handlers.onOpen();
        seeGameStart(connections[0]);

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
        expect(
            host.querySelector(".game__play .board-notice .board-notice__body")?.textContent,
        ).toBe("Finding your game…");

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
        expect(
            host.querySelector(".game__play .board-notice .board-notice__body")?.textContent,
        ).toBe("Finding your game…");

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

/** Mount into the document, where focus works; the test's end disposes it and takes it out. */
function mountInDocument(overrides: FakeOverrides = {}): ReturnType<typeof mountWithFakes> {
    const mounted = mountWithFakes(overrides);
    document.body.append(mounted.host);
    onTestFinished(() => {
        mounted.dispose();
        mounted.host.remove();
    });
    return mounted;
}

/** Mount into the document at the call prompt. */
function mountInDocumentAtCallPrompt(overrides: FakeOverrides = {}): {
    clock: ManualClock;
    connections: FakeConnection[];
    host: HTMLElement;
    lobby: HTMLElement;
    sound: FakeSound;
} {
    const { clock, connections, host, sound } = mountInDocument(overrides);
    openCallPrompt(connections[0]);
    return { clock, connections, host, lobby: rotateLeave(host), sound };
}

/** The rotate panel's way back to the lobby. */
function rotateLeave(host: HTMLElement): HTMLElement {
    const lobby = host.querySelector<HTMLElement>(".game__rotate .rotate-panel__leave");
    if (lobby === null) {
        throw new Error("no Lobby button");
    }
    return lobby;
}

/** Whether the board and the page's controls in its corner are inert under the leave question. */
function inertAreas(host: HTMLElement): boolean[] {
    return [".board-layout", ".game-menu"].map(
        (selector) => host.querySelector(`.game__play ${selector}`)?.closest("[inert]") != null,
    );
}

describe("mountGameView leaving", () => {
    it("asks before handing a held seat to an AI, and Stay takes the question back, leaving nothing", () => {
        const { connections, host, sink } = mountWithFakes();
        openCallPrompt(connections[0]);

        rotateLeave(host).click();
        expect(host.querySelector(".game__play .leave-confirm__detail")?.textContent).toBe(
            "An AI will play your seat.",
        );
        expect(rotateLeave(host).hidden).toBe(true);
        press(host, ".leave-confirm__stay");

        expect(host.querySelector(".game__play .leave-confirm")).toBeNull();
        expect(host.querySelector(".game__play .decision-controls__action")).not.toBeNull();
        expect(connections[0].disconnected).toBe(false);
        expect(sink.leaveToLobby).not.toHaveBeenCalled();
    });

    it("closes the socket and leaves for the lobby once the player confirms leaving", () => {
        const { connections, host, sink } = mountWithFakes();
        openCallPrompt(connections[0]);

        rotateLeave(host).click();
        press(host, ".leave-confirm__leave");

        expect(connections[0].disconnected).toBe(true);
        expect(sink.leaveToLobby).toHaveBeenCalledOnce();
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

    it("asks from the settings menu's leave row, closing the menu, and Stay focuses the cog back", async () => {
        const { connections, host } = mountInDocumentAtCallPrompt();
        press(host, ".game-menu__toggle");
        const row = host.querySelector<HTMLElement>(".game__play .game-menu__leave");
        row?.focus();

        row?.click();
        await Promise.resolve();
        const opened = [
            row?.getAttribute("aria-haspopup"),
            host.querySelector(".game__play .game-menu__panel"),
            document.activeElement?.className,
        ];
        press(host, ".leave-confirm__stay");

        expect(opened).toEqual(["dialog", null, "leave-confirm__stay"]);
        expect([
            document.activeElement?.classList.contains("game-menu__toggle"),
            connections[0].disconnected,
        ]).toEqual([true, false]);
    });

    it("keeps Tab and Shift+Tab cycling between the question's two buttons", async () => {
        const { host, lobby } = mountInDocumentAtCallPrompt();
        lobby.click();
        await Promise.resolve();
        const [stay, leave] = [".leave-confirm__stay", ".leave-confirm__leave"].map((selector) =>
            host.querySelector<HTMLElement>(`.game__play ${selector}`),
        );
        function tab(from: HTMLElement | null, shiftKey: boolean): string | undefined {
            from?.focus();
            from?.dispatchEvent(
                new KeyboardEvent("keydown", { bubbles: true, key: "Tab", shiftKey }),
            );
            return document.activeElement?.className;
        }

        expect([tab(leave, false), tab(stay, true)]).toEqual([
            "leave-confirm__stay",
            "secondary leave-confirm__leave",
        ]);
    });
});

/**
 * Mount into the document and play the own turn scenario to its first draw, noting whether the opening screen held
 * the focus before the draw closed it.
 */
async function mountInDocumentThroughFirstDraw(): Promise<{
    host: HTMLElement;
    openingFocused: boolean;
}> {
    const { connections, host } = mountInDocument();
    const { transcript } = loadSeatScenario("own_turn_seat_1");
    const toOpening = receivedThrough(transcript, "game started").length + 1;
    const toDraw = receivedThrough(transcript, "first draw");
    connections[0].handlers.onOpen();
    toDraw.slice(0, toOpening).forEach((payload) => connections[0].handlers.onMessage(payload));
    await Promise.resolve();
    const openingFocused = document.activeElement?.closest(".seating") != null;
    toDraw.slice(toOpening).forEach((payload) => connections[0].handlers.onMessage(payload));
    return { host, openingFocused };
}

/** Press ArrowRight on the focused element, and say whether it moved the focus to a playable tile. */
function arrowReachesTile(): boolean {
    document.activeElement?.dispatchEvent(
        new KeyboardEvent("keydown", { bubbles: true, key: "ArrowRight" }),
    );
    return document.activeElement?.classList.contains("hand-tile--selectable") === true;
}

describe("mountGameView keyboard focus", () => {
    it("gives the board the focus the opening screen's OK loses on the first draw, and the arrows reach the hand from it or the cog", async () => {
        const { host, openingFocused } = await mountInDocumentThroughFirstDraw();

        const boardFocused = document.activeElement?.classList.contains("game-board");
        const fromBoard = arrowReachesTile();
        host.querySelector<HTMLElement>(".game__play .game-menu__toggle")?.focus();
        const fromCog = arrowReachesTile();

        expect([openingFocused, boardFocused, fromBoard, fromCog]).toEqual([
            true,
            true,
            true,
            true,
        ]);
    });
});

describe("mountGameView controls help", () => {
    it("opens over an inert board from the settings menu, and Escape closes it and focuses the cog back", async () => {
        const { host } = mountInDocumentAtCallPrompt();
        press(host, ".game-menu__toggle");
        const row = host.querySelector<HTMLElement>(".game__play .game-menu__controls");
        row?.focus();

        row?.click();
        await Promise.resolve();
        const opened = [
            host.querySelector(".game__play .game-menu__panel"),
            inertAreas(host),
            document.activeElement?.classList.contains("controls-help__close"),
            host.querySelectorAll(".game__play .controls-help__row").length,
        ];
        document.activeElement?.dispatchEvent(
            new KeyboardEvent("keydown", { bubbles: true, key: "Escape" }),
        );

        expect(opened).toEqual([null, [true, true], true, 6]);
        expect([
            host.querySelector(".game__play .controls-help"),
            document.activeElement?.classList.contains("game-menu__toggle"),
        ]).toEqual([null, true]);
    });
});

/** The settings menu's sound switch: whether it is on, and what it reads. */
function soundSwitch(host: HTMLElement): (string | null | undefined)[] {
    const button = host.querySelector(".game__play .game-menu__sound");
    return [button?.getAttribute("aria-checked"), button?.textContent?.trim()];
}

/** Receive the call prompt scenario's messages after its prompt, through its turn after the chi. */
function receiveThroughTurn(socket: FakeConnection): void {
    const { transcript } = loadSeatScenario("call_prompt_seat_1");
    const toPrompt = receivedThrough(transcript, "prompt").length;
    for (const payload of receivedThrough(transcript, "turn").slice(toPrompt)) {
        socket.handlers.onMessage(payload);
    }
}

function inputSettingInBrowser(): GameViewDeps["inputSetting"] {
    localStorage.setItem(INPUT_SETTING_KEY, JSON.stringify({ rightClick: "invalid" }));
    onTestFinished(() => localStorage.removeItem(INPUT_SETTING_KEY));
    return localStore(INPUT_SETTING_KEY, readInputSetting, DEFAULT_INPUT_SETTING);
}

function keepSwitch(host: HTMLElement): string | null | undefined {
    return host.querySelector(".game-menu__keep-auto-win")?.getAttribute("aria-checked");
}

function motionOf(host: HTMLElement): string | null | undefined {
    return host.querySelector(".game-board")?.getAttribute("data-motion");
}

function keycaps(host: HTMLElement): number {
    return host.querySelectorAll(".game__play .decision-controls__key").length;
}

function mountInputMenu(
    inputSetting: GameViewDeps["inputSetting"],
): ReturnType<typeof mountInDocumentAtCallPrompt> {
    const mounted = mountInDocumentAtCallPrompt({ inputSetting });
    press(mounted.host, ".game-menu__toggle");
    return mounted;
}

describe("mountGameView settings", () => {
    it("shows the decision controls' digit keys only once Key hints is on, kept across mounts beside right-click", () => {
        const inputSetting = inputSettingInBrowser();
        const first = mountInputMenu(inputSetting);
        const before = keycaps(first.host);
        press(first.host, ".game-menu__key-hints");
        const saved: unknown = JSON.parse(localStorage.getItem(INPUT_SETTING_KEY) ?? "null");
        const next = mountInputMenu(inputSetting);

        expect([before, keycaps(first.host), saved, keycaps(next.host)]).toEqual([
            0,
            4,
            { keyHints: true, rightClick: true },
            4,
        ]);
        expect(readInputSetting({ rightClick: false })).toEqual({
            keyHints: false,
            rightClick: false,
        });
    });

    it("keeps right-click disabled across mounts without disabling Escape to pass", () => {
        const inputSetting = inputSettingInBrowser();
        const first = mountInputMenu(inputSetting);
        press(first.host, ".game-menu__right-click");
        expect(JSON.parse(localStorage.getItem(INPUT_SETTING_KEY) ?? "null")).toEqual({
            keyHints: false,
            rightClick: false,
        });

        const next = mountInputMenu(inputSetting);
        const nextChecked = next.host
            .querySelector(".game-menu__right-click")
            ?.getAttribute("aria-checked");
        pressKey(next.host, ".game-menu__right-click", "Escape");
        next.clock.advanceTo(next.clock.elapsedNow() + SHORTCUT_SETTLE_MS);
        pressKey(next.host, ".board-local .hand-tile", "Escape");
        expect([nextChecked, next.connections[0].sent]).toEqual([
            "false",
            [JOIN, buildPassAction(PROMPT_WAIT_ID)],
        ]);
    });

    it("defaults keeping Auto win off over a bad stored value and remembers it across mounts", () => {
        localStorage.setItem(
            AUTO_WIN_SETTING_KEY,
            JSON.stringify({ keepBetweenRounds: "invalid" }),
        );
        onTestFinished(() => localStorage.removeItem(AUTO_WIN_SETTING_KEY));
        const autoWinSetting = localStore(
            AUTO_WIN_SETTING_KEY,
            readAutoWinSetting,
            DEFAULT_AUTO_WIN_SETTING,
        );
        const first = mountInDocumentAtCallPrompt({ autoWinSetting });
        press(first.host, ".game-menu__toggle");
        const before = keepSwitch(first.host);
        press(first.host, ".game-menu__keep-auto-win");
        const next = mountInDocumentAtCallPrompt({ autoWinSetting });
        press(next.host, ".game-menu__toggle");

        expect([
            before,
            keepSwitch(first.host),
            JSON.parse(localStorage.getItem(AUTO_WIN_SETTING_KEY) ?? "null"),
            keepSwitch(next.host),
        ]).toEqual(["false", "true", { keepBetweenRounds: true }, "true"]);
    });

    it("defaults the animations on over a bad stored value and keeps them off across mounts", () => {
        localStorage.setItem(MOTION_SETTING_KEY, JSON.stringify({ animations: "invalid" }));
        onTestFinished(() => localStorage.removeItem(MOTION_SETTING_KEY));
        const motionSetting = localStore(
            MOTION_SETTING_KEY,
            readMotionSetting,
            DEFAULT_MOTION_SETTING,
        );
        const first = mountInDocumentAtCallPrompt({ motionSetting });
        press(first.host, ".game-menu__toggle");
        const before = motionOf(first.host);
        press(first.host, ".game-menu__animations");
        const next = mountInDocumentAtCallPrompt({ motionSetting });

        expect([
            before,
            JSON.parse(localStorage.getItem(MOTION_SETTING_KEY) ?? "null"),
            motionOf(first.host),
            motionOf(next.host),
        ]).toEqual([null, { animations: false }, "off", "off"]);
    });

    it("opens the sound switch and the status from the cog, keeps the switch in this browser, and closes on Escape, focusing the cog", () => {
        const { host, sound } = mountInDocumentAtCallPrompt({ soundSetting: { sound_on: false } });

        press(host, ".game-menu__toggle");
        const stored = soundSwitch(host);
        press(host, ".game-menu__sound");
        const switched = soundSwitch(host);
        const status = host.querySelector(".game__play .game-menu__status")?.textContent;
        pressKey(host, ".game-menu__sound", "Escape");

        expect([stored, switched, sound.setting, status]).toEqual([
            ["false", "SoundOff"],
            ["true", "SoundOn"],
            { sound_on: true },
            "Connected",
        ]);
        expect(host.querySelector(".game__play .game-menu__panel")).toBeNull();
        expect(document.activeElement?.classList.contains("game-menu__toggle")).toBe(true);
    });

    it("plays the sounds of each step while the sound is on, and none once the player turns it off", () => {
        const { connections, host, sound } = mountWithFakes();
        openCallPrompt(connections[0]);
        const heard = [...new Set(sound.played)];

        press(host, ".game-menu__toggle");
        press(host, ".game-menu__sound");
        const played = sound.played.length;
        receiveThroughTurn(connections[0]);

        expect(heard).toEqual(["discard", "decision"]);
        expect(sound.played).toHaveLength(played);
    });

    it("switches the page to Russian in place while a call waits, its menu open, sending nothing and reloading nothing", () => {
        onTestFinished(resetPageLanguage);
        const languages = fakeLanguageSwitch();
        const { connections, host, sink } = mountWithFakes({ setLanguage: languages.setLanguage });
        openCallPrompt(connections[0]);

        press(host, ".game-menu__toggle");
        press(host, '.game-menu__language-option[lang="ru"]');

        expect([
            languages.chosen,
            document.documentElement.lang,
            document.title,
            host.querySelector(".game__play .decision-controls__action--pass")?.textContent?.trim(),
            host.querySelector('.game__play .game-menu__language-option[aria-current="true"]')
                ?.textContent,
            host.querySelector(".game__play .game-menu__panel") !== null,
            connections[0].sent,
        ]).toEqual([["ru"], "ru", "Ronin - Игра", "Пропустить", "Русский", true, [JOIN]]);
        expect(sink.reload).not.toHaveBeenCalled();
    });
});

describe("mountGameView choice of tiles", () => {
    it("moves the focus from a choice to its call's control when Escape goes back, never out of the board", () => {
        const { host } = mountInDocumentAtCallPrompt();
        press(host, FIRST_STEP_CALL);
        host.querySelector<HTMLElement>(".game__play .decision-controls__action--choice")?.focus();

        pressKey(host, ".decision-controls__action--choice", "Escape");

        expect([
            document.activeElement?.getAttribute("aria-label"),
            document.activeElement?.getAttribute("aria-pressed"),
        ]).toEqual(["Chii", "false"]);
    });

    it("leaves a choice of tiles open when Escape closes the leave question over it", async () => {
        const { host, lobby } = mountInDocumentAtCallPrompt();
        press(host, FIRST_STEP_CALL);
        lobby.click();
        await Promise.resolve();

        document.activeElement?.dispatchEvent(
            new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Escape" }),
        );

        expect(host.querySelector(".game__play .leave-confirm")).toBeNull();
        expect(labelsAfter(host, () => {})).toEqual([
            "Chii 2-man and 4-man",
            "Chii 1-man and 2-man",
            "Chii",
            "Back",
        ]);
    });

    it("dismisses the controls silently once Pass is pressed", () => {
        const { connections, host, sound } = mountWithFakes();
        openCallPrompt(connections[0]);
        const played = [...sound.played];

        const sent = labelsAfter(host, () => press(host, ".decision-controls__action--pass"));

        expect(sent).toEqual([]);
        expect(sound.played).toEqual(played);
    });
});

function openPlainRiichiDraw(connection: FakeConnection): ClientMessage {
    const { transcript } = loadSeatScenario("own_turn_seat_1");
    connection.handlers.onOpen();
    for (const payload of receivedThrough(transcript, "furiten")) {
        connection.handlers.onMessage(payload);
    }

    const { [WIRE_KEY.AVAILABLE_ACTIONS]: _offers, ...plain } = receivedPayload(
        transcript,
        "tsumo draw",
    );
    connection.handlers.onMessage(plain);
    return buildDiscardAction(
        Number(plain[WIRE_KEY.PACKED_MOVE]) % NUM_TILES,
        Number(plain[WIRE_KEY.WAIT_ID]),
    );
}

function openAutoDiscardDraw(connection: FakeConnection, host: HTMLElement): ClientMessage {
    const { transcript } = loadSeatScenario("anchor_seat_1");
    connection.handlers.onOpen();
    for (const payload of receivedThrough(transcript, "own turn").slice(0, -1)) {
        connection.handlers.onMessage(payload);
    }

    press(host, '.play-switch[title="Auto discard"]');
    const draw = receivedPayload(transcript, "own turn");
    connection.handlers.onMessage(draw);
    return buildDiscardAction(
        Number(draw[WIRE_KEY.PACKED_MOVE]) % NUM_TILES,
        Number(draw[WIRE_KEY.WAIT_ID]),
    );
}

describe("mountGameView board", () => {
    it("holds an Auto discard draw for one second before the driver sends it", () => {
        const { connections, clock, host } = mountWithFakes();
        const [connection] = connections;
        const discard = openAutoDiscardDraw(connection, host);
        expect(connection.sent).toEqual([JOIN]);
        expect(host.querySelectorAll(".board-local .hand-tile--selectable")).toHaveLength(14);

        clock.advanceTo(999);
        expect(connection.sent).toEqual([JOIN]);

        clock.advanceTo(1000);
        expect(connection.sent).toEqual([JOIN, discard]);
        expect(host.querySelectorAll(".board-local .hand-tile--selected")).toHaveLength(1);
    });

    it("shows a post-riichi draw for one second before the driver sends its discard", () => {
        const { connections, clock, host } = mountWithFakes();
        const [connection] = connections;
        const discard = openPlainRiichiDraw(connection);
        expect([
            connection.sent,
            host.querySelectorAll(".board-local .hand-tile--selectable").length,
        ]).toEqual([[JOIN], 1]);

        clock.advanceTo(999);
        expect(connection.sent).toEqual([JOIN]);

        clock.advanceTo(1000);
        expect(connection.sent).toEqual([JOIN, discard]);
        expect(host.querySelectorAll(".board-local .hand-tile--selected")).toHaveLength(1);
    });

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

    it("pages a double ron with Next, its button focused for Enter or Space, sends one confirm on OK, then waits for the others, counting down", async () => {
        const { connections, host } = mountInDocument();
        openDoubleRonEnd(connections[0]);
        await Promise.resolve();

        const labels = [0, 1].map(() => {
            const label = host.querySelector(
                ".game__play .round-end-result__confirm-label",
            )?.textContent;
            const focused = document.activeElement?.classList.contains("round-end-result__confirm");
            press(host, ".round-end-result__confirm");
            return [label?.trim(), focused];
        });

        expect(labels).toEqual([
            ["Next", true],
            ["OK", true],
        ]);
        expect(connections[0].sent).toEqual([JOIN, buildConfirmRoundAction(ROUND_END_WAIT_ID)]);
        expect(
            host.querySelector(
                ".game__play .round-end-result__confirm:not(.round-end-result__ghost)",
            ),
        ).toBeNull();
        expect(
            [".round-end-result__waiting", ".round-end-result__countdown"].map(
                (part) =>
                    host.querySelector(
                        `.game__play .round-end-result__wait:not(.round-end-result__ghost) ${part}`,
                    )?.textContent,
            ),
        ).toEqual(["Waiting for others", expect.stringMatching(/^\d+s left$/)]);
    });

    it("sends a pass with the prompt's wait id when the call prompt's Pass is pressed", () => {
        const { connections, host } = mountWithFakes();
        openCallPrompt(connections[0]);

        press(host, ".decision-controls__action--pass");

        expect(connections[0].sent).toEqual([JOIN, buildPassAction(PROMPT_WAIT_ID)]);
    });

    it("opens a chi's choice of tiles on Chi, sending nothing, goes back on Escape, and sends the chosen chi once", () => {
        const { connections, host, sound } = mountWithFakes();
        openCallPrompt(connections[0]);

        const choosing = labelsAfter(host, () => press(host, FIRST_STEP_CALL));
        const back = labelsAfter(host, () => pressKey(host, ".board-local .hand-tile", "Escape"));
        press(host, FIRST_STEP_CALL);
        press(host, ".decision-controls__action--choice");
        expect(host.querySelector(".decision-controls")).toBeNull();
        expect([
            host.querySelector(".board-callout--bottom .board-callout__word")?.textContent,
            sound.played.filter((cue) => cue === "chi"),
        ]).toEqual(["Chii", ["chi"]]);

        expect([choosing, back]).toEqual([
            ["Chii 2-man and 4-man", "Chii 1-man and 2-man", "Chii", "Back"],
            ["Kan 3-man", "Pon 3-man", "Chii", "Pass"],
        ]);
        expect(connections[0].sent).toEqual([JOIN, buildChiAction(8, [4, 12], PROMPT_WAIT_ID)]);
    });
});

/** The panel's button over the live board whose words are `words`. */
function panelButton(host: HTMLElement, words: string): HTMLElement | undefined {
    return [...host.querySelectorAll<HTMLElement>(".game__play .board-overlay__panel button")].find(
        (button) => button.textContent?.trim() === words,
    );
}

/** Join, receive the double ron scenario's messages through its round end, then the game's end. */
function endGameOnDoubleRon(socket: FakeConnection): void {
    socket.handlers.onOpen();
    const { transcript } = loadSeatScenario("double_ron_seat_1");
    for (const payload of receivedThrough(transcript, "round end")) {
        socket.handlers.onMessage(payload);
    }
    socket.handlers.onMessage(WIRE_GAME_END);
}

/** Let the first socket time out unopened, then open the one its retry asks for, the game not joined yet. */
function reopenAfterConnectTimeout(clock: ManualClock, connections: FakeConnection[]): void {
    clock.advanceTo(10_000);
    clock.advanceTo(11_000);
    connections[1].handlers.onOpen();
}

function resultPageLabel(host: HTMLElement): string | null | undefined {
    return host.querySelector(".game__play .round-end-result__page")?.textContent;
}

describe("mountGameView view state", () => {
    it("reopens the game's last result on its first page from Last hand, though the player left it on its second", () => {
        const { connections, host } = mountWithFakes();
        endGameOnDoubleRon(connections[0]);

        press(host, '[aria-label="Next winner"]');
        const turned = resultPageLabel(host);
        panelButton(host, "Final scores")?.click();
        panelButton(host, "Last hand")?.click();

        expect([turned, resultPageLabel(host)]).toEqual(["2 / 2", "1 / 2"]);
    });

    it("closes the notices' sheet when a message takes its last notice away, so a later notice never reopens it", () => {
        const { clock, connections, host, tileSprite } = mountWithFakes();
        reopenAfterConnectTimeout(clock, connections);
        press(host, ".board-notice__more");
        const opened = host.querySelector(".game__play .notice-sheet") !== null;

        connections[1].handlers.onMessage(WIRE_GAME_JOINED);
        const closed = host.querySelector(".game__play .notice-sheet");
        tileSprite.moveTo("failed");

        expect([opened, closed, host.querySelector(".game__play .notice-sheet")]).toEqual([
            true,
            null,
            null,
        ]);
        expect(spriteNotice(host)).toMatch(/^Tile images did not load/);
    });
});
