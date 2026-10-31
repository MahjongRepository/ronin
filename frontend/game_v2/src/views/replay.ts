import { type TemplateResult, html, nothing, render } from "lit-html";

import "@/styles/replay-page.scss";
import { type Ref, createRef, ref } from "lit-html/directives/ref.js";

import {
    REPLAY_ROUND_LIST_ID,
    ROUND_LIST_ROW_CLASS,
    ReplayControls,
    type ReplayCursor,
    type ReplayDisplay,
    type ReplayPrefsStore,
    ReplayStatus,
    RoundList,
    type StepDirection,
    lastCursor,
    replayAddressSearch,
    replayDisplay,
} from "@/entities/replay";
import {
    type BoardNotice,
    GameBoard,
    type ScoreDiffPin,
    type SeatPosition,
    type StandingsRenderer,
    type TableState,
    boardOverlay,
    showsRoundResult,
    tableStateToDisplayState,
} from "@/entities/table";
import {
    type LoadReplay,
    type ReplayFetch,
    isAbortError,
    loadReplayUntilFound,
} from "@/shared/api";
import { type Clock } from "@/shared/clock";
import {
    type DeadlineTimer,
    type LoadStatus,
    type RetryingLoad,
    type ThrottledWriter,
    assertNever,
    createDeadlineTimer,
    createThrottledWriter,
} from "@/shared/lib";
import {
    HOLD_EVENTS,
    boardWheel,
    holdInput,
    isOutsideRoundList,
    keyCommand,
    pressedStepButton,
    stepKeyDirection,
} from "@/views/replay-input";
import {
    type LoadedScreen,
    type ReplayFailure,
    type ReplayFocusTarget,
    type ReplayOpening,
    type ReplayPageEffect,
    type ReplayPageInput,
    type ReplayPageStep,
    type ReplayScreen,
    canStep,
    replayPageDeadline,
    stepReplayPage,
} from "@/views/replay-page";

/** The page's address, which the view reads once and keeps on the position it shows. */
export interface ReplayLocation {
    /** The page's query as it opened, `?` and all, or empty. */
    readonly search: string;
    /** Replace the page's history entry with this query, keeping its path and hash. */
    readonly replaceSearch: (search: string) => void;
    /** Call `listener` whenever the page is hidden or left; returns its removal. */
    readonly onPageHide: (listener: () => void) => () => void;
}

/** Where a page that cannot show its replay sends the reader. */
export interface ReplayLinks {
    readonly lobby: string;
    readonly history: string;
}

export interface ReplayViewDeps {
    readonly loadReplay: LoadReplay;
    readonly clock: Clock;
    readonly location: ReplayLocation;
    readonly links: ReplayLinks;
    /** Start loading the final standings, which the view does as it mounts and stops on dispose. */
    readonly startStandings: () => RetryingLoad<StandingsRenderer>;
    /** The reader's own settings: whether the other hands hide, and autoplay's speed. */
    readonly prefs: ReplayPrefsStore;
    /** Open on the round list, as a storybook state shows it; closed when omitted. */
    readonly roundListOpen?: boolean;
    /** Open with autoplay running, as a storybook state shows it; paused when omitted. */
    readonly autoplay?: boolean;
}

/**
 * The fewest milliseconds between two writes of the address bar: Safari refuses more than 100 history writes in 30
 * seconds, which a held key or autoplay would reach. A move within it is written once it has passed.
 */
export const REPLAY_URL_WRITE_INTERVAL_MS = 500;

/** The final standings' load as the page draws it: the renderer once loaded, and where the load stands. */
interface StandingsState {
    readonly renderer: StandingsRenderer | null;
    readonly status: LoadStatus;
}

/** What the page draws beside its screen: its ways back and the final standings' load. */
interface ReplayPage {
    readonly links: ReplayLinks;
    readonly standings: StandingsState;
}

interface ReplayHandlers {
    readonly root: Ref<HTMLElement>;
    readonly keydown: (event: KeyboardEvent) => void;
    readonly keyup: (event: KeyboardEvent) => void;
    readonly move: (cursor: ReplayCursor) => void;
    readonly showResultPage: (page: number) => void;
    readonly pinNameplate: (seat: SeatPosition | null) => void;
    readonly toggleRoundList: () => void;
    readonly closeRoundList: () => void;
    readonly selectRound: (start: ReplayCursor) => void;
    readonly showRoundResult: (round: number) => void;
    readonly retry: () => void;
    readonly wheel: { handleEvent: (event: WheelEvent) => void; passive: false };
    readonly stepPress: (direction: StepDirection, event: PointerEvent) => void;
    readonly stepClick: (direction: StepDirection) => void;
    readonly togglePlay: () => void;
    readonly cycleSpeed: () => void;
    readonly switchView: () => void;
    readonly toggleHands: () => void;
}

interface FailureText {
    readonly title: string;
    readonly detail: string;
    readonly retry: boolean;
}

function failureText(failure: ReplayFailure): FailureText {
    switch (failure.kind) {
        case "not_found": {
            return {
                detail: "No replay is stored for this game. A game that has just ended may still be saving it.",
                retry: true,
                title: "Replay not found",
            };
        }
        case "refused": {
            return {
                detail: `The server answered ${failure.status}.`,
                retry: true,
                title: "The replay could not be loaded",
            };
        }
        case "unreachable": {
            return {
                detail: "The server could not be reached.",
                retry: true,
                title: "The replay could not be loaded",
            };
        }
        case "unsupported_version": {
            return {
                detail: `It was recorded in format ${failure.version}, which this page cannot read.`,
                retry: false,
                title: "This replay cannot be shown",
            };
        }
        case "unreadable": {
            return {
                detail: `${failure.detail}.`,
                retry: false,
                title: "This replay cannot be shown",
            };
        }
        case "show_failed": {
            return {
                detail: "Something went wrong while reading it. The error is on the browser's console.",
                retry: false,
                title: "This replay cannot be shown",
            };
        }
        case "no_deal": {
            const damage =
                failure.damage === null
                    ? ""
                    : ` Line ${failure.damage.lineNumber} could not be read.`;
            return {
                detail: `The recording stops before the first deal.${damage}`,
                retry: false,
                title: "This replay holds no round",
            };
        }
        default: {
            return assertNever(failure);
        }
    }
}

/** Whether `element` is drawn: a control the board's stylesheet hides (an option under a small board's panel) is not. */
function isShown(element: HTMLElement): boolean {
    return typeof element.checkVisibility !== "function" || element.checkVisibility();
}

/**
 * Whether two screens draw the same page: a replay's wheel gesture, the click a press drops, the hold and autoplay's
 * next move are kept, never drawn, so a change to them alone draws nothing.
 */
function drawsAlike(shown: ReplayScreen, next: ReplayScreen): boolean {
    if (shown === next) {
        return true;
    }
    if (shown.kind !== "loaded" || next.kind !== "loaded") {
        return false;
    }
    return (
        shown.replay === next.replay &&
        shown.view === next.view &&
        shown.roundListOpen === next.roundListOpen &&
        shown.pinnedNameplate === next.pinnedNameplate &&
        shown.hideHands === next.hideHands &&
        shown.autoplay.playing === next.autoplay.playing &&
        shown.autoplay.speed === next.autoplay.speed
    );
}

function nextSeat(seat: number, seatCount: number): number {
    return (seat + 1) % seatCount;
}

function seatName(table: TableState, seat: number): string {
    return table.players.find((player) => player.seat === seat)?.name ?? `Seat ${seat}`;
}

/** Says the final standings failed to load, where the table shown has ended and would show them. */
function standingsNotices(table: TableState, standings: StandingsState): BoardNotice[] {
    if (table.phase !== "game_ended" || standings.status !== "failed") {
        return [];
    }
    return [
        { text: "The final standings did not load; reload the page to try again", tone: "error" },
    ];
}

/** The replay's moves and options over the board's band, and the round list over the board while it is open. */
function controlsTemplate(
    { autoplay, hideHands, replay, roundListOpen, view }: LoadedScreen,
    display: ReplayDisplay,
    handlers: ReplayHandlers,
): TemplateResult {
    const viewName = seatName(display.table, view.bottomSeat);
    const nextViewName = seatName(display.table, nextSeat(view.bottomSeat, replay.seatCount));
    const last = lastCursor(replay.navigation);
    const end =
        last === null
            ? null
            : {
                  current: display.moves.last === null,
                  cursor: last,
                  summary:
                      display.incomplete === null
                          ? "The game's end and the final standings"
                          : "Where the recording ends",
              };
    const roundList = roundListOpen
        ? RoundList({
              end,
              incomplete: display.incomplete,
              onClose: handlers.closeRoundList,
              onSelect: handlers.selectRound,
              rows: display.rounds,
          })
        : nothing;
    return html`${ReplayControls({
        moves: display.moves,
        onCycleSpeed: handlers.cycleSpeed,
        onMove: handlers.move,
        onStepClick: handlers.stepClick,
        onStepPress: handlers.stepPress,
        onSwitchView: handlers.switchView,
        onToggleHands: handlers.toggleHands,
        onTogglePlay: handlers.togglePlay,
        onToggleRoundList: handlers.toggleRoundList,
        playback: {
            hideHands,
            nextViewName,
            playing: autoplay.playing,
            speed: autoplay.speed,
            viewName,
        },
        roundListOpen,
    })}${roundList}`;
}

function loadedTemplate(
    screen: LoadedScreen,
    { links, standings }: ReplayPage,
    handlers: ReplayHandlers,
): TemplateResult {
    const { hideHands, pinnedNameplate, replay, view } = screen;
    const perspective = {
        bottomSeat: view.bottomSeat,
        reveal: hideHands ? "bottom" : "all",
    } as const;
    const display = replayDisplay(replay, view.cursor, perspective);
    const scoreDiff: ScoreDiffPin = { onPin: handlers.pinNameplate, pinned: pinnedNameplate };
    return html`
        <div class="board-page__board">
            ${GameBoard({
                callouts: display.callouts,
                debug: false,
                notices: standingsNotices(display.table, standings),
                overlay: boardOverlay(display.table, {
                    paging: { onPage: handlers.showResultPage, page: view.cursor.page },
                    standings: {
                        actions: [
                            { href: links.lobby, kind: "link", label: "Lobby" },
                            {
                                href: links.history,
                                kind: "link",
                                label: "Game history",
                                primary: true,
                            },
                        ],
                        onRound: handlers.showRoundResult,
                        renderer: standings.renderer,
                        viewerSeat: view.bottomSeat,
                    },
                }),
                overlayIsResult: showsRoundResult(display.table),
                replay: {
                    controls: controlsTemplate(screen, display, handlers),
                    status: ReplayStatus({ display }),
                },
                scoreDiff,
                state: tableStateToDisplayState(display.table, perspective),
            })}
        </div>
    `;
}

function failedTemplate(
    failure: ReplayFailure,
    links: ReplayLinks,
    handlers: ReplayHandlers,
): TemplateResult {
    const text = failureText(failure);
    return html`<div class="replay-state replay-state--failed" role="alert">
        <h1 class="replay-state__title">${text.title}</h1>
        <p class="replay-state__detail">${text.detail}</p>
        <div class="replay-state__links">
            ${text.retry ? html`<button type="button" @click=${handlers.retry}>Try again</button>` : nothing}
            <a href=${links.history} role="button" class=${text.retry ? "secondary" : ""}>Game history</a>
            <a href=${links.lobby} role="button" class="secondary">Lobby</a>
        </div>
    </div>`;
}

function loadingTemplate(waiting: boolean): TemplateResult {
    return html`<div class="replay-state" role="status" aria-busy="true">
        <p class="replay-state__detail">
            ${waiting ? "Waiting for the replay to be saved…" : "Loading the replay…"}
        </p>
    </div>`;
}

function screenTemplate(
    screen: ReplayScreen,
    page: ReplayPage,
    handlers: ReplayHandlers,
): TemplateResult {
    switch (screen.kind) {
        case "loaded": {
            return loadedTemplate(screen, page, handlers);
        }
        case "failed": {
            return failedTemplate(screen.failure, page.links, handlers);
        }
        case "loading": {
            return loadingTemplate(screen.waiting);
        }
        default: {
            return assertNever(screen);
        }
    }
}

function replayTemplate(
    screen: ReplayScreen,
    page: ReplayPage,
    handlers: ReplayHandlers,
): TemplateResult {
    return html`
        <div
            class="board-page replay-board-mode"
            tabindex="0"
            ${ref(handlers.root)}
            @keydown=${handlers.keydown}
            @keyup=${handlers.keyup}
            @wheel=${handlers.wheel}
        >
            ${screenTemplate(screen, page, handlers)}
        </div>
    `;
}

/**
 * The replay viewer for one mount: it loads the replay through the injected `loadReplay` (asking again while the
 * server has not stored it yet), steps the page's reducer (`stepReplayPage`) with every input stamped with the
 * clock's time, renders the screen it returns into its host and runs the effects it asks for: the address kept on the
 * position shown, the reader's settings saved and the focus moved. It keeps one timer armed to the screen's deadline
 * (autoplay's next move, a held button's next repeat), which comes back as a tick. Its input is its own: the keys
 * reach it only while focus is inside its focusable root, which it focuses on mount unless something else holds
 * focus, and an outside click closes only its own round list. A throw in a step or a render says the replay cannot be
 * shown, its error on the console. Disposing aborts the load and its retries, cancels every timer, drops an address
 * write still waiting, removes its listeners and clears its host; a load that settles afterwards renders nothing.
 */
class ReplayViewController {
    private readonly host: HTMLElement;
    private readonly deps: ReplayViewDeps;
    private readonly gameId: string;
    private readonly addressWriter: ThrottledWriter<string>;
    private readonly removePageHide: () => void;
    private readonly standings: RetryingLoad<StandingsRenderer>;
    private abort = new AbortController();
    private screen: ReplayScreen = { kind: "loading", waiting: false };
    private disposed = false;
    private readonly timer: DeadlineTimer;
    /** The step button a hold follows, whose pointer events the view listens to while the screen holds it. */
    private held: HTMLElement | null = null;

    private readonly handlers: ReplayHandlers = {
        closeRoundList: () => this.dispatch({ kind: "close_round_list" }),
        cycleSpeed: () => this.dispatch({ kind: "cycle_speed" }),
        keydown: (event) => this.onKeydown(event),
        keyup: (event) => this.onKeyup(event),
        move: (cursor) => this.dispatch({ cursor, kind: "move" }),
        pinNameplate: (seat) => this.dispatch({ kind: "pin", seat }),
        retry: () => this.startLoad(),
        root: createRef<HTMLElement>(),
        selectRound: (cursor) => this.dispatch({ cursor, kind: "select_round" }),
        showResultPage: (page) => this.dispatch({ kind: "result_page", page }),
        showRoundResult: (round) => this.dispatch({ kind: "round_result", round }),
        stepClick: (direction) => this.dispatch({ direction, kind: "step_click" }),
        stepPress: (direction, event) => this.onStepPress(direction, event),
        switchView: () => this.dispatch({ kind: "switch_view" }),
        toggleHands: () => this.dispatch({ kind: "toggle_hands" }),
        togglePlay: () => this.dispatch({ kind: "toggle_play" }),
        toggleRoundList: () => this.dispatch({ kind: "toggle_round_list" }),
        wheel: { handleEvent: (event) => this.onWheel(event), passive: false },
    };

    constructor(host: HTMLElement, gameId: string, deps: ReplayViewDeps) {
        this.host = host;
        this.deps = deps;
        this.gameId = gameId;
        this.timer = createDeadlineTimer(deps.clock, (at) =>
            this.guard(() => this.apply(stepReplayPage(this.screen, { at, kind: "tick" }))),
        );
        this.addressWriter = createThrottledWriter(
            deps.clock,
            REPLAY_URL_WRITE_INTERVAL_MS,
            deps.location.replaceSearch,
        );
        this.removePageHide = deps.location.onPageHide(() => this.onPageHide());
        host.ownerDocument.addEventListener("click", this.onClickOutside);
        this.standings = this.startStandings();
        this.open();
    }

    /** Show the loading screen, take the focus where nothing else holds it and start the load. */
    private open(): void {
        this.show(this.screen);
        this.focusRootUnlessFocusIsElsewhere();
        this.startLoad();
    }

    /** Start loading the final standings, drawing the page again as their load moves on. */
    private startStandings(): RetryingLoad<StandingsRenderer> {
        const standings = this.deps.startStandings();
        standings.subscribe(() => this.guard(() => this.show(this.screen)));
        return standings;
    }

    dispose(): void {
        this.disposed = true;
        this.timer.disarm();
        this.releaseHold();
        this.host.ownerDocument.removeEventListener("click", this.onClickOutside);
        this.removePageHide();
        this.standings.stop();
        this.addressWriter.cancel();
        this.abort.abort();
        render(nothing, this.host);
    }

    private readonly onClickOutside = (event: MouseEvent): void => {
        if (isOutsideRoundList(event, this.host)) {
            this.dispatch({ kind: "dismiss_round_list" });
        }
    };

    private readonly onHoldEvent = (event: Event): void => {
        const input = this.held === null ? null : holdInput(event, this.held);
        if (input !== null) {
            this.dispatch(input);
        }
    };

    private dispatch(input: ReplayPageInput): void {
        this.guard(() => this.step(input));
    }

    private step(input: ReplayPageInput): void {
        this.apply(stepReplayPage(this.screen, { ...input, at: this.deps.clock.now() }));
    }

    /**
     * Run what an input, a timer or a load asks of the page: a throw in any of it says the replay cannot be shown,
     * rather than leaving the page on a stop it could not draw; nothing runs after dispose.
     */
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

    /**
     * Take a step of the page: draw its screen where what it draws changed (a wheel's gesture or a dropped click alone
     * changes nothing drawn), run its effects, follow its hold and arm its deadline.
     */
    private apply({ effects, screen }: ReplayPageStep): void {
        if (drawsAlike(this.screen, screen)) {
            this.screen = screen;
        } else {
            this.show(screen);
        }
        for (const effect of effects) {
            this.runEffect(effect);
        }
        if (this.screen.kind !== "loaded" || this.screen.hold === null) {
            this.releaseHold();
        }
        this.armDeadline();
    }

    private fail(error: unknown): void {
        console.error("The replay could not be shown:", error);
        const at = this.deps.clock.now();
        this.apply(stepReplayPage(this.screen, { at, kind: "show_failed" }));
    }

    private runEffect(effect: ReplayPageEffect): void {
        switch (effect.kind) {
            case "write_address": {
                this.writeAddress();
                return;
            }
            case "save_prefs": {
                this.deps.prefs.save(effect.prefs);
                return;
            }
            case "focus": {
                this.focus(effect.target);
                return;
            }
            default: {
                assertNever(effect);
            }
        }
    }

    /** Keep one timer armed to the screen's deadline, unless it is the one already armed. */
    private armDeadline(): void {
        this.timer.arm(replayPageDeadline(this.screen));
    }

    private onPageHide(): void {
        this.guard(() => {
            this.addressWriter.flush();
            this.step({ kind: "page_hide" });
        });
    }

    private focusRootUnlessFocusIsElsewhere(): void {
        const { activeElement, body } = this.host.ownerDocument;
        if (activeElement === null || activeElement === body) {
            this.focus("root");
        }
    }

    private focus(target: ReplayFocusTarget): void {
        switch (target) {
            case "root": {
                this.handlers.root.value?.focus({ preventScroll: true });
                return;
            }
            case "current_round": {
                this.host
                    .querySelector<HTMLElement>(`.${ROUND_LIST_ROW_CLASS}[aria-current="true"]`)
                    ?.focus({ preventScroll: false });
                return;
            }
            case "round_list_toggle": {
                this.host
                    .querySelector<HTMLElement>(`[aria-controls="${REPLAY_ROUND_LIST_ID}"]`)
                    ?.focus({ preventScroll: true });
                return;
            }
            default: {
                assertNever(target);
            }
        }
    }

    /**
     * A key the page takes, prevented while a replay shows: Enter and Space on a step button are prevented, so the
     * button's own click never repeats the step the key took.
     */
    private onKeydown(event: KeyboardEvent): void {
        const command = keyCommand(event);
        if (command !== null && this.screen.kind === "loaded") {
            event.preventDefault();
        }
        this.dispatch({ command, kind: "key", repeat: event.repeat });
    }

    /** Space's release on a step button, which would click it where the press's prevention did not hold. */
    private onKeyup(event: KeyboardEvent): void {
        if (stepKeyDirection(event) !== null) {
            event.preventDefault();
        }
    }

    /** The wheel steps only over the board and only where a step goes; anywhere else it scrolls. */
    private onWheel(event: WheelEvent): void {
        const wheel = boardWheel(event);
        if (wheel === null || !canStep(this.screen, wheel.direction)) {
            return;
        }
        event.preventDefault();
        this.dispatch({ deltaPx: wheel.deltaPx, kind: "wheel" });
    }

    /** A pointer's press of a step button; a press that starts a hold captures the pointer and follows it. */
    private onStepPress(direction: StepDirection, event: PointerEvent): void {
        this.guard(() => this.press(direction, event));
    }

    private press(direction: StepDirection, event: PointerEvent): void {
        const button = pressedStepButton(event);
        this.step({ direction, kind: "step_press", primary: button !== null });
        if (button === null || this.screen.kind !== "loaded" || this.screen.hold === null) {
            return;
        }
        this.releaseHold();
        if (event.isTrusted) {
            button.setPointerCapture(event.pointerId);
        }
        this.held = button;
        for (const type of HOLD_EVENTS) {
            button.addEventListener(type, this.onHoldEvent);
        }
    }

    private releaseHold(): void {
        for (const type of HOLD_EVENTS) {
            this.held?.removeEventListener(type, this.onHoldEvent);
        }
        this.held = null;
    }

    private startLoad(): void {
        this.abort.abort();
        this.abort = new AbortController();
        this.dispatch({ kind: "load_started" });
        void this.load(this.abort.signal);
    }

    private async load(signal: AbortSignal): Promise<void> {
        const fetched = await this.fetchReplay(signal);
        if (fetched !== null) {
            this.guard(() => this.apply(this.readFetched(fetched)));
        }
    }

    /** The fetched replay, or null once the load was aborted or the page shows the server as unreachable. */
    private async fetchReplay(signal: AbortSignal): Promise<ReplayFetch | null> {
        try {
            return await loadReplayUntilFound(this.deps.loadReplay, this.gameId, {
                onWaiting: () => this.dispatch({ kind: "load_waiting" }),
                setTimer: this.deps.clock.setTimer,
                signal,
            });
        } catch (error: unknown) {
            if (!isAbortError(error)) {
                this.dispatch({ kind: "load_unreachable" });
            }
            return null;
        }
    }

    /** The page after a fetch's answer. */
    private readFetched(fetched: ReplayFetch): ReplayPageStep {
        const opening: ReplayOpening = {
            autoplay: this.deps.autoplay ?? false,
            prefs: this.deps.prefs.load(),
            roundListOpen: this.deps.roundListOpen ?? false,
            search: this.deps.location.search,
        };
        return stepReplayPage(this.screen, {
            at: this.deps.clock.now(),
            fetched,
            kind: "fetched",
            opening,
        });
    }

    /**
     * Render the screen. Focus that was inside the page and lost its element to the render (a result's pager, a
     * standings row, a move that can go no further, an option a panel hides) goes back to the page's root, so its keys
     * go on.
     */
    private show(screen: ReplayScreen): void {
        this.screen = screen;
        const { ownerDocument } = this.host;
        const hadFocus = this.host.contains(ownerDocument.activeElement);
        const standings = { renderer: this.standings.value(), status: this.standings.status() };
        const page = { links: this.deps.links, standings };
        render(replayTemplate(screen, page, this.handlers), this.host);
        if (hadFocus) {
            this.keepFocusInside();
        }
    }

    private keepFocusInside(): void {
        const focused = this.host.ownerDocument.activeElement;
        const lost =
            !this.host.contains(focused) ||
            (focused instanceof HTMLButtonElement && focused.disabled) ||
            (focused instanceof HTMLElement && !isShown(focused));
        if (lost) {
            this.focus("root");
        }
    }

    private writeAddress(): void {
        const { screen } = this;
        if (screen.kind !== "loaded") {
            return;
        }
        const search = replayAddressSearch(
            this.deps.location.search,
            screen.replay.navigation,
            screen.view,
        );
        this.addressWriter.write(search);
    }
}

/** Mount the replay viewer into `host` and return its dispose. */
export function mountReplayView(
    host: HTMLElement,
    gameId: string,
    deps: ReplayViewDeps,
): () => void {
    const controller = new ReplayViewController(host, gameId, deps);
    return () => controller.dispose();
}
