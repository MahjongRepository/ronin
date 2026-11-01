import { type TemplateResult, html, nothing, render } from "lit-html";
import { type Ref, createRef, ref } from "lit-html/directives/ref.js";

import {
    CLIENT_STEPPED,
    type ClientEffect,
    type LiveClient,
    type LiveEvent,
    NO_PLAY_UI,
    PlayBoard,
    type PlayCommand,
    type PlayDisplay,
    type PlayUi,
    RotatePanel,
    describeClientStatus,
    failGameClient,
    intentCommand,
    nextCountdownChange,
    nextDeadline,
    playDisplay,
    serverSilenceLimitMs,
    startGameClient,
    stepGameClient,
    stepPlayUi,
} from "@/entities/client";
import { type TileSprite } from "@/entities/tile";
import { type HandoffRecovery, type RecoverHandoff, isAbortError } from "@/shared/api";
import { type Clock } from "@/shared/clock";
import { type DeadlineTimer, assertNever, createDeadlineTimer } from "@/shared/lib";
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
    readonly links: GameLinks;
}

/** Where the game's end leads: the game history, and this game's replay from a seat. */
export interface GameLinks {
    readonly history: string;
    readonly replay: (seat: number | null) => string;
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

/** A line of the debug log, formatted once when it is added; it lives in the view, never in the client state. */
interface LogEntry {
    readonly at: number;
    readonly kind: string;
    readonly text: string;
}

interface GameViewProps {
    readonly links: GameLinks;
    readonly log: readonly LogEntry[] | null;
    readonly state: LiveClient;
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
        LiveEvent,
        {
            kind:
                | "transport_opened"
                | "transport_closed"
                | "transport_error"
                | "frame_undecodable"
                | "handoff_recovered";
        }
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
        case "frame_undecodable": {
            return `Undecodable frame: ${event.detail}`;
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
function logEntryFor(event: LiveEvent): LogEntry | null {
    const { at } = event;
    switch (event.kind) {
        case "server_message": {
            const text = JSON.stringify(event.raw, null, 2);
            return { at, kind: wireTypeName(event.raw), text };
        }
        case "transport_opened":
        case "transport_closed":
        case "transport_error":
        case "frame_undecodable":
        case "handoff_recovered": {
            return { at, kind: LOG_TYPE_SYSTEM, text: systemLogText(event) };
        }
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
    state: LiveClient,
): TemplateResult {
    return html`<details class="game-log">
        <summary>Log: ${describeClientStatus(state).label}</summary>
        <div class="log-panel" ${ref(panel)}>
            <div class="log-entries">${log.map(logEntryTemplate)}</div>
        </div>
    </details>`;
}

/**
 * The live game: its board, played from the viewer's seat, with the page's controls in its corner, and the rotate
 * panel the stylesheet shows in its place on an upright phone, all rendered from the same state so the panel's status
 * and countdown stay current while it is hidden.
 */
function gameTemplate(props: GameViewProps): TemplateResult {
    const { links, log, onCommand, panel, state, ui } = props;
    const display: PlayDisplay = playDisplay(state, ui);
    const board = PlayBoard({
        display,
        links: { history: links.history, replay: links.replay(state.viewerSeat) },
        menuExtra: log === null ? undefined : logTemplate(log, panel, state),
        onCommand,
    });
    return html`
        <div class="game">
            <div class="game__rotate">${RotatePanel(display, onCommand)}</div>
            <div class="game__play board-page">
                <div class="board-page__board">${board}</div>
            </div>
        </div>
    `;
}

/** The page once even its failed state could not be drawn: why, and a reload, with nothing of the board. */
function brokenTemplate(onReload: () => void): TemplateResult {
    return html`
        <div class="game game--broken" role="alert">
            <p>The game page ran into an error.</p>
            <button type="button" @click=${onReload}>Reload</button>
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
function nextWake(state: LiveClient): number | null {
    const wakes = [nextDeadline(state), nextCountdownChange(state)].filter((at) => at !== null);
    return wakes.length === 0 ? null : Math.min(...wakes);
}

/**
 * The live driver of the game client's dispatcher for one mount: it stamps every socket, timer and button event
 * with the clock's time, steps the dispatcher, executes the effects it returns in order and renders the state.
 * Events raised while effects run are queued behind the current one. After each step it arms one timer to the
 * state's next deadline or countdown change, which comes back as a tick; a timer that was replaced, a socket that
 * was closed, or anything after `dispose` is dropped, so nothing restarts a disposed session. A step, an effect or a
 * render (a redraw of the view's own included) that throws ends the client as failed, shown on the page, instead of
 * leaving it stuck: a protocol failure never throws here, since the dispatcher recovers from it itself, so what does
 * is a bug in the client. It keeps the socket's silence limit on the client's policy (`serverSilenceLimitMs`).
 */
class GameViewController {
    private readonly host: HTMLElement;
    private readonly deps: GameViewDeps;
    private readonly panel = createRef<HTMLElement>();
    private readonly queue: LiveEvent[] = [];
    private readonly log: LogEntry[] | null;
    private state: LiveClient;
    private ui: PlayUi;
    private readonly stopTileSprite: () => void;
    /** The control that opened the leave question, which takes the focus back when the player stays. */
    private leaveOpener: HTMLElement | null = null;
    private readonly recovery = new AbortController();
    private readonly timer: DeadlineTimer;
    private socket: GameConnection | null = null;
    private socketGeneration = 0;
    private disposed = false;
    /** The failed state could not be drawn either, so the page shows the bare notice and draws nothing more. */
    private broken = false;
    private draining = false;
    private logAppended = 0;
    private logAppendedAtDraw = 0;

    constructor(host: HTMLElement, gameId: string, deps: GameViewDeps) {
        this.host = host;
        this.deps = deps;
        this.log = deps.debug ? [] : null;
        this.timer = createDeadlineTimer(deps.clock, (at) => this.dispatch({ at, kind: "tick" }));
        this.ui = { ...NO_PLAY_UI, tileSprite: deps.tileSprite.status() };
        this.stopTileSprite = this.followTileSprite();
        const { effects, state } = startGameClient(gameId, deps.handoff, deps.clock.now());
        this.state = state;
        this.settle(effects);
    }

    /** Draw the page again as the tile sprite's load moves on; returns its unsubscribe. */
    private followTileSprite(): () => void {
        return this.deps.tileSprite.subscribe((tileSprite) => {
            this.guard(() => {
                this.ui = stepPlayUi(this.state, this.ui, {
                    kind: "tile_sprite",
                    status: tileSprite,
                });
                this.draw();
            });
        });
    }

    dispose(): void {
        this.disposed = true;
        this.stopTileSprite();
        this.recovery.abort();
        this.queue.length = 0;
        this.timer.disarm();
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
        this.guard(() => this.changeUi(command));
    };

    /** Run a redraw outside a step: a throw in it ends the client as failed, as a step's does. */
    private guard(action: () => void): void {
        if (this.disposed) {
            return;
        }
        try {
            action();
        } catch (error: unknown) {
            this.fail(error);
        }
    }

    private changeUi(command: Exclude<PlayCommand, { kind: "intent" | "reload" }>): void {
        if (command.kind === "ask_leave") {
            this.leaveOpener = this.focusedControl();
        }
        this.ui = stepPlayUi(this.state, this.ui, command);
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

    private dispatch(event: LiveEvent): void {
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
            this.show();
        } catch (error: unknown) {
            this.fail(error);
        } finally {
            this.draining = false;
        }
    }

    /** Arm the next deadline, keep the socket's silence limit on the client's policy and render. */
    private show(): void {
        if (!this.disposed) {
            this.armDeadline();
            this.socket?.setSilenceLimit(serverSilenceLimitMs(this.state));
            this.draw();
        }
    }

    private drainQueue(): void {
        for (let next = this.queue.shift(); next !== undefined; next = this.queue.shift()) {
            const { effects, state } = stepGameClient(this.state, next);
            this.state = state;
            this.ui = stepPlayUi(
                state,
                this.ui,
                next.kind === "intent" ? intentCommand(next.intent) : CLIENT_STEPPED,
            );
            this.runEffects(effects);
        }
    }

    /**
     * End the client as failed after a throw in a step, an effect or a render: the error on the console, whatever the
     * log, the queue and the socket dropped, and the failed state shown, or, where drawing that throws too, a bare
     * notice with a reload that draws nothing of the board.
     */
    private fail(error: unknown): void {
        console.error("The game page failed:", error);
        const detail = describeError(error);
        this.queue.length = 0;
        this.state = failGameClient(this.state, detail);
        this.appendLog({
            at: this.deps.clock.now(),
            kind: LOG_TYPE_ERROR,
            text: `Client failed: ${detail}`,
        });
        this.closeSocket();
        try {
            this.ui = stepPlayUi(this.state, this.ui, CLIENT_STEPPED);
            this.show();
        } catch (drawError: unknown) {
            this.showBroken(drawError);
        }
    }

    /** Give up drawing the board for good: the bare notice with a reload, and no timer left armed. */
    private showBroken(drawError: unknown): void {
        console.error("The failed game page could not be drawn:", drawError);
        this.broken = true;
        this.timer.disarm();
        render(brokenTemplate(this.deps.sink.reload), this.host);
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
        if (this.disposed || this.broken) {
            return;
        }
        const { command, log, panel, state, ui } = this;
        const props = {
            links: this.deps.links,
            log,
            onCommand: command,
            panel,
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
            case "report_protocol_failure": {
                this.reportProtocolFailure(effect.detail);
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
     * A server message the client could not read or take: always on the console, whatever the log; the state counts it
     * for the board's notice and recovers from it itself, since the table may be wrong until a snapshot.
     */
    private reportProtocolFailure(detail: string): void {
        const text = `Protocol failure: ${detail}`;
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
        const fromCurrent = (event: LiveEvent): void => {
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
            onUndecodableFrame: (detail) =>
                fromCurrent({ at: clock.now(), detail, kind: "frame_undecodable" }),
        };
    }

    /** Keep one timer armed to the state's next wake; a replaced timer's late callback is dropped. */
    private armDeadline(): void {
        this.timer.arm(nextWake(this.state));
    }
}

/** Mount the live game into `host` and return its dispose, which cancels the timer and the socket. */
export function mountGameView(host: HTMLElement, gameId: string, deps: GameViewDeps): () => void {
    const controller = new GameViewController(host, gameId, deps);
    return () => controller.dispose();
}
