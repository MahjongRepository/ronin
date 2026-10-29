import { type TemplateResult, html, nothing, render } from "lit-html";
import { type Ref, createRef, ref } from "lit-html/directives/ref.js";

import {
    type ClientEffect,
    type ClientEvent,
    type GameClientState,
    NO_PLAY_UI,
    PlayBoard,
    type PlayCommand,
    type PlayDisplay,
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
import { type TileSprite } from "@/entities/tile";
import { type HandoffRecovery, type RecoverHandoff, isAbortError } from "@/shared/api";
import { type CancelTimer, type Clock } from "@/shared/clock";
import { assertNever } from "@/shared/lib";
import { CLOSE_CODE, EVENT_TYPE, LOG_TYPE_SYSTEM, LOG_TYPE_UNKNOWN } from "@/shared/protocol";
import { type GameSessionData } from "@/shared/session";
import { type ConnectSocket, type GameConnection, type SocketHandlers } from "@/shared/websocket";

/** Where the game view's effects outside the socket land: the lobby's handoff storage and the page's location. */
export interface GameViewSink {
    readonly clearHandoff: (gameId: string) => void;
    readonly storeHandoff: (gameId: string, handoff: GameSessionData) => void;
    readonly leaveToLobby: () => void;
    /** Go to another game's page, under the game client's URL the lobby named, keeping this page's query. */
    readonly openGame: (gameId: string, gameClientUrl: string) => void;
    readonly reload: () => void;
}

export interface GameViewDeps {
    readonly clock: Clock;
    readonly connect: ConnectSocket;
    /** The lobby's handoff from this tab's storage, or null, when the view asks `recoverHandoff` for it. */
    readonly handoff: GameSessionData | null;
    readonly recoverHandoff: RecoverHandoff;
    readonly sink: GameViewSink;
    /** Keep and show the debug log of every message and transport event (the page's `?debug`). */
    readonly debug: boolean;
    /** The tile sprite's load, which the board's notice reports while the faces are missing. */
    readonly tileSprite: TileSprite;
}

const MAX_LOG_ENTRIES = 500;
const LOG_TYPE_ERROR = "error";
const LOG_TYPE_SENT = "sent";

const EVENT_NAMES: ReadonlyMap<number, string> = new Map(
    Object.entries(EVENT_TYPE).map(([name, type]) => [type, name.toLowerCase()]),
);

type SocketEffect = Extract<ClientEffect, { type: "open_socket" | "close_socket" | "send" }>;
type SinkEffect = Extract<
    ClientEffect,
    { type: "clear_handoff" | "redirect_to_lobby" | "store_handoff" | "redirect_to_game" }
>;

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
    readonly panel: Ref<HTMLElement>;
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

/** What the lobby's answer for the player's game says, without the ticket it carries. */
function describeRecovery(recovery: HandoffRecovery): string {
    switch (recovery.kind) {
        case "found": {
            return `Game session found: ${recovery.gameId}`;
        }
        case "missing": {
            return "No game session";
        }
        case "failed": {
            return `Game session lookup failed: ${recovery.detail}`;
        }
        default: {
            return assertNever(recovery);
        }
    }
}

/** The system line of the debug log for the transport's events and the lobby's answer for the handoff. */
function systemLogText(
    event: Extract<
        ClientEvent,
        { kind: "transport_opened" | "transport_closed" | "transport_error" | "handoff_recovered" }
    >,
): string {
    switch (event.kind) {
        case "transport_opened": {
            return "Connection opened";
        }
        case "transport_closed": {
            return `Connection closed (${event.code} ${event.reason})`;
        }
        case "transport_error": {
            return `Transport error: ${event.detail}`;
        }
        case "handoff_recovered": {
            return describeRecovery(event.recovery);
        }
        default: {
            return assertNever(event);
        }
    }
}

/** The log line an event adds, or null for one that only moves time or carries an intent. */
function logEntryFor(event: ClientEvent): LogEntry | null {
    const { at } = event;
    switch (event.kind) {
        case "server_message": {
            const text = JSON.stringify(event.raw, null, 2);
            return { at, kind: wireTypeName(event.raw), text };
        }
        case "transport_opened":
        case "transport_closed":
        case "transport_error":
        case "handoff_recovered": {
            return { at, kind: LOG_TYPE_SYSTEM, text: systemLogText(event) };
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

/**
 * The live game: its board, played from the viewer's seat, beside its controls (the way back, the session's status
 * and, under `?debug`, the log), and the rotate panel the stylesheet shows in their place on an upright phone, all
 * rendered from the same state so the panel's status and countdown stay current while it is hidden. While the leave
 * question is open the controls are inert with the board, so the question is modal.
 */
function gameTemplate(props: GameViewProps): TemplateResult {
    const { gameId, log, onCommand, panel, state, ui } = props;
    const status = describePlayerClientStatus(state);
    const display: PlayDisplay = playDisplay(state, ui);
    return html`
        <div class="game">
            <div class="game__rotate">${RotatePanel(rotatePanelProps(state, ui, onCommand))}</div>
            <div class="game__play board-page">
                <div class="board-page__board">${PlayBoard({ display, onCommand, table: state.table })}</div>
                <aside class="board-page__aside game-aside" aria-label="Game ${gameId}" ?inert=${display.leave.confirming}>
                    <button
                        class="secondary game-aside__leave"
                        aria-haspopup=${display.leave.command.kind === "ask_leave" ? "dialog" : nothing}
                        @click=${() => onCommand(display.leave.command)}
                    >
                        Lobby
                    </button>
                    <span class="connection-status game-aside__status status-${status.tone}" role="status"
                        >${status.label}</span
                    >
                    ${log === null ? "" : logTemplate(log, panel, state)}
                </aside>
            </div>
        </div>
    `;
}

/** A lookup of the handoff that failed, as the lobby's answer; null for one that dispose cancelled. */
function failedRecovery(error: unknown, signal: AbortSignal): HandoffRecovery | null {
    if (signal.aborted || isAbortError(error)) {
        return null;
    }
    return { detail: describeError(error), kind: "failed" };
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
    private ui: PlayUi;
    private readonly stopTileSprite: () => void;
    /** The control that opened the leave question, which takes the focus back when the player stays. */
    private leaveOpener: HTMLElement | null = null;
    private readonly recovery = new AbortController();
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
        this.ui = { ...NO_PLAY_UI, tileSprite: deps.tileSprite.status() };
        this.stopTileSprite = deps.tileSprite.subscribe((tileSprite) => {
            this.ui = { ...this.ui, tileSprite };
            this.draw();
        });
        const { effects, state } = startGameClient(gameId, deps.handoff, deps.clock.now());
        this.state = state;
        this.settle(effects);
    }

    dispose(): void {
        this.disposed = true;
        this.stopTileSprite();
        this.recovery.abort();
        this.queue.length = 0;
        this.disarm();
        this.closeSocket();
        render(nothing, this.host);
    }

    /**
     * A page control: an intent goes to the dispatcher, a reload to the page; picking riichi's discard, a result page
     * or asking to leave only changes the view's `ui`. Staying returns the focus to the control that asked.
     */
    private readonly command = (command: PlayCommand): void => {
        if (command.kind === "intent") {
            this.dispatch({ at: this.deps.clock.now(), intent: command.intent, kind: "intent" });
            return;
        }
        if (command.kind === "reload") {
            this.deps.sink.reload();
            return;
        }
        this.changeUi(command);
    };

    private changeUi(command: Exclude<PlayCommand, { kind: "intent" | "reload" }>): void {
        if (command.kind === "ask_leave") {
            this.leaveOpener = this.focusedControl();
        }
        this.ui = nextPlayUi(this.state, this.ui, command);
        this.draw();
        if (command.kind === "cancel_leave") {
            this.leaveOpener?.focus();
            this.leaveOpener = null;
        }
    }

    private focusedControl(): HTMLElement | null {
        const focused = this.host.ownerDocument.activeElement;
        return focused instanceof HTMLElement && this.host.contains(focused) ? focused : null;
    }

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
        const { command, gameId, log, panel, state, ui } = this;
        const props = { gameId, log, onCommand: command, panel, state, ui };
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
            case "store_handoff":
            case "redirect_to_lobby":
            case "redirect_to_game": {
                this.runSinkEffect(effect);
                return;
            }
            case "recover_handoff": {
                void this.recover();
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
     * A server message the client could not read: always on the console, whatever the log; the state counts it for
     * the board's notice, since the table may be wrong from here on.
     */
    private reportParseError(detail: string): void {
        const text = `Parse error: ${detail}`;
        console.error(text);
        this.appendLog({ at: this.state.now, kind: LOG_TYPE_UNKNOWN, text });
    }

    private runSinkEffect(effect: SinkEffect): void {
        const { sink } = this.deps;
        if (effect.type === "clear_handoff") {
            sink.clearHandoff(effect.gameId);
        } else if (effect.type === "store_handoff") {
            sink.storeHandoff(effect.gameId, effect.handoff);
        } else if (effect.type === "redirect_to_lobby") {
            sink.leaveToLobby();
        } else {
            sink.openGame(effect.gameId, effect.gameClientUrl);
        }
    }

    /**
     * Ask the lobby for the player's game and hand its answer to the dispatcher; a request that fails is an answer
     * too, but one cancelled by dispose is dropped.
     */
    private async recover(): Promise<void> {
        const { signal } = this.recovery;
        const recovery = await this.deps
            .recoverHandoff(signal)
            .catch((error: unknown) => failedRecovery(error, signal));
        if (recovery !== null) {
            this.dispatch({ at: this.deps.clock.now(), kind: "handoff_recovered", recovery });
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
                code: CLOSE_CODE.ABNORMAL,
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
