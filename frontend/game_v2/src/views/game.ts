import { type TemplateResult, html, nothing, render } from "lit-html";
import { type Ref, createRef, ref } from "lit-html/directives/ref.js";

import {
    type ClientEffect,
    type ClientEvent,
    type GameClientState,
    NO_PLAY_UI,
    PlayBoard,
    type PlayCommand,
    type PlayUi,
    RotatePanel,
    describeClientStatus,
    describePlayerClientStatus,
    failGameClient,
    nextCountdownChange,
    nextDeadline,
    nextPlayUi,
    playDisplay,
    rotatePanelProps,
    startGameClient,
    stepGameClient,
} from "@/entities/client";
import { boardOverlay } from "@/entities/table";
import { type CancelTimer, type Clock } from "@/shared/clock";
import { assertNever } from "@/shared/lib";
import { EVENT_TYPE, LOG_TYPE_SYSTEM, LOG_TYPE_UNKNOWN } from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";
import { type ConnectSocket, type GameConnection, type SocketHandlers } from "@/shared/websocket";

/** Where the game view's effects outside the socket land: the lobby's handoff storage and the page's location. */
export interface GameViewSink {
    readonly clearHandoff: (gameId: string) => void;
    readonly leaveToLobby: () => void;
}

export interface GameViewDeps {
    readonly clock: Clock;
    readonly connect: ConnectSocket;
    readonly handoff: GameSessionData | null;
    readonly sink: GameViewSink;
    /** Keep and show the debug log of every message and transport event (the page's `?debug`). */
    readonly debug: boolean;
}

/** The close the driver reports when the socket factory throws: what a browser reports for a failed connection. */
const CONNECT_FAILED_CLOSE_CODE = 1006;
const MAX_LOG_ENTRIES = 500;
const LOG_TYPE_ERROR = "error";
const LOG_TYPE_SENT = "sent";

const EVENT_NAMES: ReadonlyMap<number, string> = new Map(
    Object.entries(EVENT_TYPE).map(([name, type]) => [type, name.toLowerCase()]),
);

type SocketEffect = Extract<ClientEffect, { type: "open_socket" | "close_socket" | "send" }>;
type SinkEffect = Extract<ClientEffect, { type: "clear_handoff" | "redirect_to_lobby" }>;

interface ArmedTimer {
    readonly cancel: CancelTimer;
    readonly deadline: number;
    readonly token: object;
}

/** A line of the debug log, formatted once when it is added; it lives in the view, never in the client state. */
interface LogEntry {
    readonly at: number;
    readonly kind: string;
    readonly text: string;
}

interface GameViewProps {
    readonly gameId: string;
    readonly log: readonly LogEntry[] | null;
    readonly state: GameClientState;
    readonly ui: PlayUi;
    readonly parseErrors: number;
    readonly panel: Ref<HTMLElement>;
    readonly onLeave: () => void;
    readonly onCommand: (command: PlayCommand) => void;
}

function describeError(error: unknown): string {
    return error instanceof Error ? error.message : String(error);
}

function wireTypeName(raw: Readonly<Record<string, unknown>>): string {
    if (typeof raw.type === "string") {
        return raw.type;
    }
    return typeof raw.t === "number" ? (EVENT_NAMES.get(raw.t) ?? `t=${raw.t}`) : LOG_TYPE_UNKNOWN;
}

/** The log line an event adds, or null for one that only moves time or carries an intent. */
function logEntryFor(event: ClientEvent): LogEntry | null {
    const { at } = event;
    switch (event.kind) {
        case "server_message": {
            const text = JSON.stringify(event.raw, null, 2);
            return { at, kind: wireTypeName(event.raw), text };
        }
        case "transport_opened": {
            return { at, kind: LOG_TYPE_SYSTEM, text: "Connection opened" };
        }
        case "transport_closed": {
            const text = `Connection closed (${event.code} ${event.reason})`;
            return { at, kind: LOG_TYPE_SYSTEM, text };
        }
        case "transport_error": {
            return { at, kind: LOG_TYPE_SYSTEM, text: `Transport error: ${event.detail}` };
        }
        case "replay_line":
        case "tick":
        case "intent": {
            return null;
        }
        default: {
            return assertNever(event);
        }
    }
}

function logEntryTemplate(entry: LogEntry): TemplateResult {
    return html`
        <div class="log-entry log-${entry.kind}">
            <span class="log-time">[${new Date(entry.at).toLocaleTimeString()}]</span>
            <span class="log-type">${entry.kind}</span>
            <pre class="log-raw">${entry.text}</pre>
        </div>
    `;
}

function logTemplate(
    log: readonly LogEntry[],
    panel: Ref<HTMLElement>,
    state: GameClientState,
): TemplateResult {
    return html`<details class="game-log">
        <summary>Log: ${describeClientStatus(state).label}</summary>
        <div class="log-panel" ${ref(panel)}>
            <div class="log-entries">${log.map(logEntryTemplate)}</div>
        </div>
    </details>`;
}

/** The page's notice of server messages the client could not read: the game may be off from here on. */
function parseErrorNotice(count: number): TemplateResult | string {
    if (count === 0) {
        return "";
    }
    return html`<p class="game-aside__warning" role="alert">
        ${count} server message(s) could not be read; the table may be wrong.
    </p>`;
}

/**
 * The live game: its board, played from the viewer's seat, beside its controls (the way back, the session's status
 * and, under `?debug`, the log), and the rotate panel the stylesheet shows in their place on an upright phone, all
 * rendered from the same state so the panel's status and countdown stay current while it is hidden.
 */
function gameTemplate(props: GameViewProps): TemplateResult {
    const { gameId, log, onCommand, onLeave, panel, parseErrors, state, ui } = props;
    const status = describePlayerClientStatus(state);
    return html`
        <div class="game">
            <div class="game__rotate">${RotatePanel(rotatePanelProps(state, onLeave))}</div>
            <div class="game__play board-page">
                <div class="board-page__board">
                    ${PlayBoard({ display: playDisplay(state, ui), onCommand, overlay: boardOverlay(state.table) })}
                </div>
                <aside class="board-page__aside game-aside" aria-label="Game ${gameId}">
                    <button class="secondary game-aside__leave" @click=${onLeave}>Lobby</button>
                    <span class="connection-status game-aside__status status-${status.tone}" role="status"
                        >${status.label}</span
                    >
                    ${parseErrorNotice(parseErrors)}
                    ${log === null ? "" : logTemplate(log, panel, state)}
                </aside>
            </div>
        </div>
    `;
}

/** The next logical time the driver must tick at: a deadline the state holds, or a change of its countdown. */
function nextWake(state: GameClientState): number | null {
    const wakes = [nextDeadline(state), nextCountdownChange(state)].filter((at) => at !== null);
    return wakes.length === 0 ? null : Math.min(...wakes);
}

/**
 * The live driver of the game client's dispatcher for one mount: it stamps every socket, timer and button event
 * with the clock's time, steps the dispatcher, executes the effects it returns in order and renders the state.
 * Events raised while effects run are queued behind the current one. After each step it arms one timer to the
 * state's next deadline or countdown change, which comes back as a tick; a timer that was replaced, a socket that
 * was closed, or anything after `dispose` is dropped, so nothing restarts a disposed session. A step that throws
 * ends the client as failed, shown on the page, instead of leaving it stuck.
 */
class GameViewController {
    private readonly host: HTMLElement;
    private readonly gameId: string;
    private readonly deps: GameViewDeps;
    private readonly panel = createRef<HTMLElement>();
    private readonly queue: ClientEvent[] = [];
    private readonly log: LogEntry[] | null;
    private state: GameClientState;
    private ui: PlayUi = NO_PLAY_UI;
    private parseErrors = 0;
    private timer: ArmedTimer | null = null;
    private socket: GameConnection | null = null;
    private socketGeneration = 0;
    private disposed = false;
    private draining = false;
    private logAppended = 0;
    private logAppendedAtDraw = 0;

    constructor(host: HTMLElement, gameId: string, deps: GameViewDeps) {
        this.host = host;
        this.gameId = gameId;
        this.deps = deps;
        this.log = deps.debug ? [] : null;
        const { effects, state } = startGameClient(gameId, deps.handoff, deps.clock.now());
        this.state = state;
        this.settle(effects);
    }

    dispose(): void {
        this.disposed = true;
        this.queue.length = 0;
        this.disarm();
        this.closeSocket();
        render(nothing, this.host);
    }

    private readonly leave = (): void => {
        this.dispatch({ at: this.deps.clock.now(), intent: { type: "leave" }, kind: "intent" });
    };

    /** A board control: an intent goes to the dispatcher; picking riichi's discard only changes the view's `ui`. */
    private readonly command = (command: PlayCommand): void => {
        if (command.kind === "intent") {
            this.dispatch({ at: this.deps.clock.now(), intent: command.intent, kind: "intent" });
            return;
        }
        this.ui = nextPlayUi(this.state, this.ui, command);
        this.draw();
    };

    private dispatch(event: ClientEvent): void {
        if (this.disposed) {
            return;
        }
        if (this.log !== null) {
            this.appendLog(logEntryFor(event));
        }
        this.queue.push(event);
        if (!this.draining) {
            this.settle([]);
        }
    }

    /** Run `effects`, then step every queued event; then arm the next deadline and render. */
    private settle(effects: readonly ClientEffect[]): void {
        this.draining = true;
        try {
            this.runEffects(effects);
            this.drainQueue();
        } catch (error: unknown) {
            this.fail(error);
        } finally {
            this.draining = false;
        }
        if (!this.disposed) {
            this.armDeadline();
            this.draw();
        }
    }

    private drainQueue(): void {
        for (let next = this.queue.shift(); next !== undefined; next = this.queue.shift()) {
            const { effects, state } = stepGameClient(this.state, next);
            this.state = state;
            this.runEffects(effects);
        }
    }

    private fail(error: unknown): void {
        const detail = describeError(error);
        this.queue.length = 0;
        this.state = failGameClient(this.state, detail);
        this.appendLog({
            at: this.deps.clock.now(),
            kind: LOG_TYPE_ERROR,
            text: `Client failed: ${detail}`,
        });
        this.closeSocket();
    }

    private appendLog(entry: LogEntry | null): void {
        const { log } = this;
        if (entry === null || log === null) {
            return;
        }
        log.push(entry);
        this.logAppended += 1;
        if (log.length > MAX_LOG_ENTRIES) {
            log.splice(0, log.length - MAX_LOG_ENTRIES);
        }
    }

    private draw(): void {
        if (this.disposed) {
            return;
        }
        const { command, gameId, leave, log, panel, parseErrors, state, ui } = this;
        const props = {
            gameId,
            log,
            onCommand: command,
            onLeave: leave,
            panel,
            parseErrors,
            state,
            ui,
        };
        render(gameTemplate(props), this.host);
        if (panel.value && this.logAppended !== this.logAppendedAtDraw) {
            panel.value.scrollTop = panel.value.scrollHeight;
        }
        this.logAppendedAtDraw = this.logAppended;
    }

    private runEffects(effects: readonly ClientEffect[]): void {
        for (const effect of effects) {
            if (this.disposed) {
                return;
            }
            this.runEffect(effect);
        }
    }

    private runEffect(effect: ClientEffect): void {
        switch (effect.type) {
            case "open_socket":
            case "close_socket":
            case "send": {
                this.runSocketEffect(effect);
                return;
            }
            case "clear_handoff":
            case "redirect_to_lobby": {
                this.runSinkEffect(effect);
                return;
            }
            case "report_parse_error": {
                this.reportParseError(effect.detail);
                return;
            }
            default: {
                assertNever(effect);
            }
        }
    }

    private runSocketEffect(effect: SocketEffect): void {
        switch (effect.type) {
            case "open_socket": {
                this.openSocket(effect.url);
                return;
            }
            case "close_socket": {
                this.closeSocket();
                return;
            }
            case "send": {
                this.socket?.send(effect.message);
                this.appendLog({
                    at: this.state.now,
                    kind: LOG_TYPE_SENT,
                    text: JSON.stringify(effect.message, null, 2),
                });
                return;
            }
            default: {
                assertNever(effect);
            }
        }
    }

    /**
     * A server message the client could not read: always on the console and counted on the page, whatever the log,
     * since the table may be wrong from here on.
     */
    private reportParseError(detail: string): void {
        const text = `Parse error: ${detail}`;
        console.error(text);
        this.parseErrors += 1;
        this.appendLog({ at: this.state.now, kind: LOG_TYPE_UNKNOWN, text });
    }

    private runSinkEffect(effect: SinkEffect): void {
        if (effect.type === "clear_handoff") {
            this.deps.sink.clearHandoff(effect.gameId);
        } else {
            this.deps.sink.leaveToLobby();
        }
    }

    /** Open a socket; a factory that throws (a refused URL, say) is reported as a failed connection's close. */
    private openSocket(url: string): void {
        this.closeSocket();
        try {
            this.socket = this.deps.connect(url, this.handlersFor(this.socketGeneration));
        } catch (error: unknown) {
            const reason = `connect_failed: ${describeError(error)}`;
            const at = this.deps.clock.now();
            this.dispatch({
                at,
                code: CONNECT_FAILED_CLOSE_CODE,
                kind: "transport_closed",
                reason,
            });
        }
    }

    private closeSocket(): void {
        this.socketGeneration += 1;
        this.socket?.disconnect();
        this.socket = null;
    }

    /** Socket callbacks that reach the dispatcher only while their socket is the current one. */
    private handlersFor(generation: number): SocketHandlers {
        const { clock } = this.deps;
        const fromCurrent = (event: ClientEvent): void => {
            if (generation === this.socketGeneration && this.socket !== null) {
                this.dispatch(event);
            }
        };
        return {
            onClose: (code, reason) => {
                fromCurrent({ at: clock.now(), code, kind: "transport_closed", reason });
                if (generation === this.socketGeneration) {
                    this.socket = null;
                }
            },
            onError: (detail) => fromCurrent({ at: clock.now(), detail, kind: "transport_error" }),
            onMessage: (raw) => fromCurrent({ at: clock.now(), kind: "server_message", raw }),
            onOpen: () => fromCurrent({ at: clock.now(), kind: "transport_opened" }),
        };
    }

    /** Keep one timer armed to the state's next wake; a replaced timer's late callback is dropped. */
    private armDeadline(): void {
        const deadline = nextWake(this.state);
        if (deadline === (this.timer?.deadline ?? null)) {
            return;
        }
        this.disarm();
        if (deadline === null) {
            return;
        }
        const { clock } = this.deps;
        const token = {};
        const cancel = clock.setTimer(Math.max(0, deadline - clock.now()), () => {
            if (this.timer?.token !== token) {
                return;
            }
            this.timer = null;
            this.dispatch({ at: Math.max(clock.now(), deadline), kind: "tick" });
        });
        this.timer = { cancel, deadline, token };
    }

    private disarm(): void {
        this.timer?.cancel();
        this.timer = null;
    }
}

/** Mount the live game into `host` and return its dispose, which cancels the timer and the socket. */
export function mountGameView(host: HTMLElement, gameId: string, deps: GameViewDeps): () => void {
    const controller = new GameViewController(host, gameId, deps);
    return () => controller.dispose();
}
