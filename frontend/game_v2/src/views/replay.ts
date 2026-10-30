import { type TemplateResult, html, nothing, render } from "lit-html";

import "@/styles/replay-page.scss";
import { type Ref, createRef, ref } from "lit-html/directives/ref.js";

import { type LoadedReplay, type ReplayUnshowable, readReplay } from "@/entities/client";
import {
    type AutoplayState,
    type BoardNotice,
    GameBoard,
    REPLAY_ROUND_LIST_ID,
    ROUND_LIST_ROW_CLASS,
    ReplayControls,
    type ReplayCursor,
    type ReplayMoves,
    type ReplayPrefs,
    type ReplayPrefsStore,
    type ReplayView,
    RoundList,
    STEP_BUTTON_ATTRIBUTE,
    type ScoreDiffPin,
    type SeatPosition,
    type StandingsRenderer,
    type StepDirection,
    type TableState,
    autoplayDelayMs,
    autoplayStep,
    boardOverlay,
    isPauseStop,
    nextAutoplaySpeed,
    parseReplayAddress,
    replayAddressSearch,
    replayDisplay,
    replayMoves,
    resolveReplayAddress,
    roundResultCursor,
    tableStateToDisplayState,
} from "@/entities/table";
import {
    type LoadReplay,
    type ReplayFetch,
    isAbortError,
    loadReplayUntilFound,
} from "@/shared/api";
import { type CancelTimer, type Clock } from "@/shared/clock";
import {
    type LoadStatus,
    type RetryingLoad,
    type ThrottledWriter,
    type WheelGesture,
    assertNever,
    createThrottledWriter,
    wheelPixels,
    wheelStep,
} from "@/shared/lib";

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

/** A held step button steps from its press, again after this delay, then every `HOLD_REPEAT_MS`. */
export const HOLD_DELAY_MS = 350;
export const HOLD_REPEAT_MS = 120;

/** Why the page shows no replay. */
type ReplayFailure =
    | ReplayUnshowable
    | { readonly kind: "not_found" }
    | { readonly kind: "refused"; readonly status: number }
    | { readonly kind: "unreachable" }
    | { readonly kind: "show_failed" };

interface LoadedScreen {
    readonly kind: "loaded";
    readonly replay: LoadedReplay;
    readonly view: ReplayView;
    readonly roundListOpen: boolean;
    /** The nameplate pinned for the others' score differences, kept from step to step until unpinned. */
    readonly pinnedNameplate: SeatPosition | null;
    readonly autoplay: AutoplayState;
    /** Whether the other seats' hands hide, as a seat would see the table, their draws in the narration too. */
    readonly hideHands: boolean;
}

type ReplayScreen =
    | { readonly kind: "loading"; readonly waiting: boolean }
    | { readonly kind: "failed"; readonly failure: ReplayFailure }
    | LoadedScreen;

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
    readonly stepClick: (direction: StepDirection, event: MouseEvent) => void;
    readonly togglePlay: () => void;
    readonly cycleSpeed: () => void;
    readonly switchView: () => void;
    readonly toggleHands: () => void;
}

/** What a key does on the page: a move, autoplay's switch, the next seat's view, or the other hands' switch. */
type ReplayKeyCommand = keyof ReplayMoves | "play" | "view" | "hands";

/** The switches among the key commands, which act once per press however long the key is held. */
const TOGGLE_COMMANDS: ReadonlySet<ReplayKeyCommand> = new Set(["hands", "play", "view"]);

/** The moves a scrolling round result keeps for itself: they would scroll it. */
const SCROLL_COMMANDS: ReadonlySet<ReplayKeyCommand> = new Set([
    "first",
    "last",
    "nextRound",
    "prevRound",
]);

/** By `key`, or by `code` for the letters, so a layout that types other letters keeps them. */
const KEY_COMMANDS: ReadonlyMap<string, ReplayKeyCommand> = new Map([
    ["ArrowDown", "nextRound"],
    ["ArrowLeft", "prev"],
    ["ArrowRight", "next"],
    ["ArrowUp", "prevRound"],
    ["End", "last"],
    ["Home", "first"],
    ["KeyH", "hands"],
    ["KeyV", "view"],
    ["PageDown", "nextRound"],
    ["PageUp", "prevRound"],
    ["Space", "play"],
]);

/** Where a key belongs to something else: a field typed into, the round list's and standings' own keys. */
const OWN_KEYS_SELECTOR = "input, textarea, select, [contenteditable], .round-list, .standings";
/** The panel over the board a round's result shows in, which scrolls when the result is taller than the board. */
const OVERLAY_PANEL_SELECTOR = ".board-overlay__panel";
/** Where Space and Enter activate the focused control itself, which the page must not repeat. */
const ACTIVATED_SELECTOR = "button, a[href], summary, [role='button']";
const HTTP_NOT_FOUND = 404;

/**
 * The User Timing measure of reading a fetched replay: parsing it, reducing it into the client timeline and building
 * its stops and navigation, before the first render. The layout gate's load budget reads it.
 */
const REPLAY_LOAD_MEASURE = "replay-load";

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

/**
 * What a replay's reading produced, as the `replay-load` measure's detail, so whoever reads the timing can check it
 * timed the whole file: its stops, rounds, completeness and final standings (seat and score), or why it failed.
 */
function loadDetail(screen: ReplayScreen): Record<string, unknown> {
    if (screen.kind !== "loaded") {
        return { failure: screen.kind === "failed" ? screen.failure.kind : screen.kind };
    }
    const { damage, navigation, tables } = screen.replay;
    const standings = tables.at(-1)?.gameEndResult?.standings ?? [];
    return {
        complete: navigation.complete,
        damagedLine: damage?.lineNumber ?? null,
        rounds: navigation.rounds.length,
        standings: standings.map(({ score, seat }) => [seat, score]),
        stops: navigation.stops.length,
    };
}

interface ScreenOptions {
    readonly search: string;
    readonly roundListOpen: boolean;
    readonly prefs: ReplayPrefs;
}

function loadedScreen(
    replay: LoadedReplay,
    { prefs, roundListOpen, search }: ScreenOptions,
): ReplayScreen {
    const view = resolveReplayAddress(replay.navigation, parseReplayAddress(search), {
        count: replay.seatCount,
        fallback: replay.firstDealerSeat,
    });
    if (view === null) {
        return { failure: { damage: replay.damage, kind: "no_deal" }, kind: "failed" };
    }
    return {
        autoplay: { playing: false, speed: prefs.speed },
        hideHands: prefs.hideHands,
        kind: "loaded",
        pinnedNameplate: null,
        replay,
        roundListOpen,
        view,
    };
}

/** The screen a fetched replay file shows at the page's address, its reading timed as the `replay-load` measure. */
function readReplayScreen(text: string, options: ScreenOptions): ReplayScreen {
    const started = performance.now();
    const read = readReplay(text);
    const screen: ReplayScreen = read.ok
        ? loadedScreen(read.replay, options)
        : { failure: read.unshowable, kind: "failed" };
    performance.measure(REPLAY_LOAD_MEASURE, { detail: loadDetail(screen), start: started });
    return screen;
}

function elementOf(target: EventTarget | null): Element | null {
    return target instanceof Element ? target : null;
}

function isModified(event: KeyboardEvent): boolean {
    return (
        event.isComposing ||
        event.key === "Process" ||
        event.ctrlKey ||
        event.altKey ||
        event.metaKey
    );
}

/**
 * The step a key activating a step button takes (Enter or Space on it), or null. The page takes it as that step, so a
 * held key pauses where a result shows, as an arrow key does, rather than repeating the button's clicks past it.
 */
function stepKeyDirection(event: KeyboardEvent): StepDirection | null {
    if (isModified(event) || (event.key !== "Enter" && event.key !== " ")) {
        return null;
    }
    const step = elementOf(event.target)
        ?.closest(`[${STEP_BUTTON_ATTRIBUTE}]`)
        ?.getAttribute(STEP_BUTTON_ATTRIBUTE);
    return step === "next" || step === "prev" ? step : null;
}

/** Whether `element` is inside the panel over the board while that panel scrolls. */
function inScrollingPanel(element: Element): boolean {
    const panel = element.closest(OVERLAY_PANEL_SELECTOR);
    return panel !== null && panel.scrollHeight > panel.clientHeight;
}

/**
 * The page's command for a key, or null where the key is not the page's: typed into a field or composed by an input
 * method, held with a modifier, inside the round list or the standings, Space and Enter on a control they activate
 * (a step button's are its step), or a key that would scroll a round's result scrolling inside its panel.
 */
function keyCommand(event: KeyboardEvent): ReplayKeyCommand | null {
    const step = stepKeyDirection(event);
    if (step !== null) {
        return step;
    }
    const target = elementOf(event.target);
    if (isModified(event) || target?.closest(OWN_KEYS_SELECTOR)) {
        return null;
    }
    const command = KEY_COMMANDS.get(event.key) ?? KEY_COMMANDS.get(event.code) ?? null;
    if (command === "play" && target?.closest(ACTIVATED_SELECTOR)) {
        return null;
    }
    return command !== null &&
        SCROLL_COMMANDS.has(command) &&
        target !== null &&
        inScrollingPanel(target)
        ? null
        : command;
}

/**
 * A wheel turned up or down over the board, outside the round list, the standings' rounds and a round's result
 * scrolling in its panel, and not a pinch.
 */
function isBoardWheel(event: WheelEvent): boolean {
    const over = elementOf(event.target);
    return (
        event.deltaY !== 0 &&
        !event.ctrlKey &&
        over !== null &&
        over.closest(".board-page__board") !== null &&
        over.closest(".round-list, .standings__sheet") === null &&
        !inScrollingPanel(over)
    );
}

/** Whether a pointer event stands over `element`'s box. */
function isOver(element: Element, event: MouseEvent): boolean {
    const { bottom, left, right, top } = element.getBoundingClientRect();
    return (
        event.clientX >= left &&
        event.clientX <= right &&
        event.clientY >= top &&
        event.clientY <= bottom
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

function loadedTemplate(
    screen: LoadedScreen,
    { links, standings }: ReplayPage,
    handlers: ReplayHandlers,
): TemplateResult {
    const { autoplay, hideHands, pinnedNameplate, replay, roundListOpen, view } = screen;
    const perspective = {
        bottomSeat: view.bottomSeat,
        reveal: hideHands ? "bottom" : "all",
    } as const;
    const display = replayDisplay(replay, view.cursor, perspective);
    const scoreDiff: ScoreDiffPin = { onPin: handlers.pinNameplate, pinned: pinnedNameplate };
    return html`
        <div class="board-page__board">
            ${GameBoard({
                debug: false,
                notices: standingsNotices(display.table, standings),
                overlay: boardOverlay(
                    display.table,
                    { onPage: handlers.showResultPage, page: view.cursor.page },
                    {
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
                ),
                scoreDiff,
                state: tableStateToDisplayState(display.table, perspective),
            })}
            ${
                roundListOpen
                    ? RoundList({
                          incomplete: display.incomplete,
                          onClose: handlers.closeRoundList,
                          onSelect: handlers.selectRound,
                          rows: display.rounds,
                      })
                    : nothing
            }
        </div>
        <div class="board-page__aside replay-controls">
            ${ReplayControls({
                display,
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
                    nextViewName: seatName(
                        display.table,
                        nextSeat(view.bottomSeat, replay.seatCount),
                    ),
                    playing: autoplay.playing,
                    speed: autoplay.speed,
                    viewName: seatName(display.table, view.bottomSeat),
                },
                roundListOpen,
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

/** A primary button's bit in a pointer event's `buttons`. */
const PRIMARY_BUTTON = 1;

/** The events a held step button follows its pointer by. */
const HOLD_EVENTS = [
    "pointerup",
    "lostpointercapture",
    "pointercancel",
    "pointerleave",
    "pointermove",
] as const;

/** What a held step button asks of its view. */
interface HeldStepDeps {
    readonly clock: Clock;
    /** Where the next repeat goes, or null where the hold must stop: a pause stop or the end. */
    readonly nextStep: () => ReplayCursor | null;
    readonly step: (cursor: ReplayCursor) => void;
    /** The hold is over: its press ended, or was cancelled, after which no click follows it. */
    readonly end: (cancelled: boolean) => void;
}

/** The step button a primary pointer pressed with its main button, else null. */
function pressedStepButton(event: PointerEvent): HTMLElement | null {
    const button = event.currentTarget;
    return event.button === 0 && event.isPrimary && button instanceof HTMLElement ? button : null;
}

/**
 * A held step button: it repeats its step after a delay, then on a beat, until its view ends it. The repeat waits
 * while the pointer is off the button and goes on when it comes back still pressed; a pointer back with its button
 * released ends the hold, as a release off the button may never reach it.
 */
class HeldStep {
    private readonly button: HTMLElement;
    private readonly deps: HeldStepDeps;
    private cancelRepeat: CancelTimer | null = null;
    private over = true;

    constructor(button: HTMLElement, deps: HeldStepDeps) {
        this.button = button;
        this.deps = deps;
        this.arm(HOLD_DELAY_MS);
        for (const type of HOLD_EVENTS) {
            button.addEventListener(type, this);
        }
    }

    handleEvent(event: Event): void {
        if (event.type === "pointerup" || event.type === "lostpointercapture") {
            this.deps.end(false);
        } else if (event.type === "pointercancel") {
            this.deps.end(true);
        } else if (event.type === "pointerleave") {
            this.follow(false);
        } else if (event instanceof MouseEvent) {
            this.track(event);
        }
    }

    stop(): void {
        this.cancelRepeat?.();
        this.cancelRepeat = null;
        for (const type of HOLD_EVENTS) {
            this.button.removeEventListener(type, this);
        }
    }

    private arm(delay: number): void {
        this.cancelRepeat = this.deps.clock.setTimer(delay, () => this.repeat());
    }

    private repeat(): void {
        const target = this.deps.nextStep();
        if (target === null) {
            this.deps.end(false);
            return;
        }
        this.deps.step(target);
        this.arm(HOLD_REPEAT_MS);
    }

    private track(event: MouseEvent): void {
        if ((event.buttons & PRIMARY_BUTTON) === 0) {
            this.deps.end(false);
        } else {
            this.follow(isOver(this.button, event));
        }
    }

    private follow(over: boolean): void {
        if (over === this.over) {
            return;
        }
        this.over = over;
        this.cancelRepeat?.();
        this.cancelRepeat = null;
        if (over) {
            this.arm(HOLD_REPEAT_MS);
        }
    }
}

/**
 * The replay viewer for one mount: it loads the replay through the injected `loadReplay` (asking again while the
 * server has not stored it yet), reads it into the game client's timeline through the dispatcher, opens it where the
 * page's address says (else on the first deal) and moves through its stops from the controls, the round list, the
 * keys, the wheel and autoplay, rendering the whole view into its host and keeping the address on the position shown.
 * Its input is its own: the keys reach it only while focus is inside its focusable root, which it focuses on
 * mount unless something else holds focus, and an outside click closes only its own round list. Autoplay, a held
 * step button and a turning wheel pause where a result shows; any other move, the page hiding and dispose stop
 * autoplay. Disposing aborts the load and its retries, cancels every timer, drops an address write still waiting,
 * removes its listeners and clears its host; a load that settles afterwards renders nothing.
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
    private autoplayTimer: CancelTimer | null = null;
    private hold: HeldStep | null = null;
    /** The step button whose press stepped already, so the click that press ends in is dropped, once. */
    private pressedStep: EventTarget | null = null;
    private wheelGesture: WheelGesture | null = null;

    private readonly handlers: ReplayHandlers = {
        closeRoundList: () => this.closeRoundList(),
        cycleSpeed: () => this.cycleSpeed(),
        keydown: (event) => this.onKeydown(event),
        keyup: (event) => this.onKeyup(event),
        move: (cursor) => this.moveTo(cursor),
        pinNameplate: (seat) => this.updateLoaded({ pinnedNameplate: seat }),
        retry: () => this.startLoad(),
        root: createRef<HTMLElement>(),
        selectRound: (start) => this.selectRound(start),
        showResultPage: (page) => this.showResultPage(page),
        showRoundResult: (round) => this.showRoundResult(round),
        stepClick: (direction, event) => this.onStepClick(direction, event),
        stepPress: (direction, event) => this.startHold(direction, event),
        switchView: () => this.switchView(),
        toggleHands: () => this.toggleHands(),
        togglePlay: () => this.togglePlay(),
        toggleRoundList: () => this.toggleRoundList(),
        wheel: { handleEvent: (event) => this.onWheel(event), passive: false },
    };

    constructor(host: HTMLElement, gameId: string, deps: ReplayViewDeps) {
        this.host = host;
        this.deps = deps;
        this.gameId = gameId;
        this.addressWriter = createThrottledWriter(
            deps.clock,
            REPLAY_URL_WRITE_INTERVAL_MS,
            deps.location.replaceSearch,
        );
        this.removePageHide = deps.location.onPageHide(() => this.onPageHide());
        host.ownerDocument.addEventListener("click", this.onClickOutside);
        this.standings = this.startStandings();
        this.show(this.screen);
        this.focusRootUnlessFocusIsElsewhere();
        this.startLoad();
    }

    /** Start loading the final standings, drawing the page again as their load moves on. */
    private startStandings(): RetryingLoad<StandingsRenderer> {
        const standings = this.deps.startStandings();
        standings.subscribe(() => this.show(this.screen));
        return standings;
    }

    dispose(): void {
        this.disposed = true;
        this.stopAutoplayTimer();
        this.stopHold();
        this.host.ownerDocument.removeEventListener("click", this.onClickOutside);
        this.removePageHide();
        this.standings.stop();
        this.addressWriter.cancel();
        this.abort.abort();
        render(nothing, this.host);
    }

    private readonly onClickOutside = (event: MouseEvent): void => {
        const { screen } = this;
        if (screen.kind !== "loaded" || !screen.roundListOpen) {
            return;
        }
        const inside = elementOf(event.target)?.closest(".round-list, .replay-controls__round");
        if (inside && this.host.contains(inside)) {
            return;
        }
        this.show({ ...screen, roundListOpen: false });
    };

    private onPageHide(): void {
        this.addressWriter.flush();
        this.stopHold();
        this.setPlaying(false);
    }

    private focusRootUnlessFocusIsElsewhere(): void {
        const { activeElement, body } = this.host.ownerDocument;
        if (activeElement === null || activeElement === body) {
            this.focusRoot();
        }
    }

    private focusRoot(): void {
        this.handlers.root.value?.focus({ preventScroll: true });
    }

    /**
     * A key the page takes. A switch acts once per press; a move repeats while held. Enter and Space on a step button
     * are prevented, so the button's own click never repeats the step the key took.
     */
    private onKeydown(event: KeyboardEvent): void {
        this.pressedStep = null;
        const command = keyCommand(event);
        if (command === null || this.screen.kind !== "loaded") {
            return;
        }
        event.preventDefault();
        if (!event.repeat || !TOGGLE_COMMANDS.has(command)) {
            this.runKeyCommand(command, event.repeat);
        }
    }

    private runKeyCommand(command: ReplayKeyCommand, repeat: boolean): void {
        if (command === "play") {
            this.togglePlay();
        } else if (command === "view") {
            this.switchView();
        } else if (command === "hands") {
            this.toggleHands();
        } else {
            this.keyMove(command, repeat);
        }
    }

    /** Space's release on a step button, which would click it where the press's prevention did not hold. */
    private onKeyup(event: KeyboardEvent): void {
        if (stepKeyDirection(event) !== null) {
            event.preventDefault();
        }
    }

    /** A move by key; a held key's repeats pause where a result shows, as a held button does. */
    private keyMove(move: keyof ReplayMoves, repeat: boolean): void {
        if (this.screen.kind !== "loaded") {
            return;
        }
        const { cursor } = this.screen.view;
        if (repeat && isPauseStop(this.screen.replay.navigation, cursor)) {
            return;
        }
        const target = replayMoves(this.screen.replay.navigation, cursor)[move];
        if (target !== null) {
            this.moveTo(target);
        }
    }

    private startLoad(): void {
        this.abort.abort();
        this.abort = new AbortController();
        this.show({ kind: "loading", waiting: false });
        void this.load(this.abort.signal);
    }

    private async load(signal: AbortSignal): Promise<void> {
        const fetched = await this.fetchReplay(signal);
        if (fetched === null) {
            return;
        }
        if (!fetched.ok) {
            const failure: ReplayFailure =
                fetched.status === HTTP_NOT_FOUND
                    ? { kind: "not_found" }
                    : { kind: "refused", status: fetched.status };
            this.show({ failure, kind: "failed" });
            return;
        }
        this.showReplay(fetched.text);
    }

    /** The fetched replay, or null once the load was aborted or the page shows the server as unreachable. */
    private async fetchReplay(signal: AbortSignal): Promise<ReplayFetch | null> {
        try {
            return await loadReplayUntilFound(this.deps.loadReplay, this.gameId, {
                onWaiting: () => this.show({ kind: "loading", waiting: true }),
                setTimer: this.deps.clock.setTimer,
                signal,
            });
        } catch (error: unknown) {
            if (!isAbortError(error)) {
                this.show({ failure: { kind: "unreachable" }, kind: "failed" });
            }
            return null;
        }
    }

    /** Read and show a fetched replay; a throw in either says the replay cannot be shown, with the error on the console. */
    private showReplay(text: string): void {
        try {
            this.showLoaded(
                readReplayScreen(text, {
                    prefs: this.deps.prefs.load(),
                    roundListOpen: this.deps.roundListOpen ?? false,
                    search: this.deps.location.search,
                }),
            );
        } catch (error: unknown) {
            console.error("The replay could not be shown:", error);
            this.show({ failure: { kind: "show_failed" }, kind: "failed" });
        }
    }

    private showLoaded(screen: ReplayScreen): void {
        this.show(screen);
        this.writeAddress();
        if (this.deps.autoplay === true) {
            this.setPlaying(true);
        }
    }

    /**
     * Render the screen. Focus that was inside the page and lost its element to the render (a result's pager, a
     * standings row, a move that can go no further) goes back to the page's root, so its keys go on.
     */
    private show(screen: ReplayScreen): void {
        if (this.disposed) {
            return;
        }
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
            (focused instanceof HTMLButtonElement && focused.disabled);
        if (lost) {
            this.focusRoot();
        }
    }

    private writeAddress(): void {
        const { screen } = this;
        if (screen.kind !== "loaded" || this.disposed) {
            return;
        }
        const search = replayAddressSearch(
            this.deps.location.search,
            screen.replay.navigation,
            screen.view,
        );
        this.addressWriter.write(search);
    }

    private updateLoaded(change: Partial<Omit<LoadedScreen, "kind" | "replay">>): void {
        if (this.screen.kind === "loaded") {
            this.show({ ...this.screen, ...change });
        }
    }

    /** A move the reader asked for, which stops autoplay and a held step button. */
    private moveTo(cursor: ReplayCursor): void {
        this.stopHold();
        this.setPlaying(false);
        this.navigate(cursor);
    }

    private navigate(cursor: ReplayCursor): void {
        if (this.screen.kind !== "loaded") {
            return;
        }
        this.updateLoaded({ view: { ...this.screen.view, cursor } });
        this.writeAddress();
    }

    /** Where one step toward `direction` goes from the cursor shown; null when nothing is loaded or it cannot go on. */
    private stepTarget(direction: StepDirection): ReplayCursor | null {
        const { screen } = this;
        if (screen.kind !== "loaded") {
            return null;
        }
        return replayMoves(screen.replay.navigation, screen.view.cursor)[direction];
    }

    /** Whether the cursor shown is where a continuous move pauses: a result's page or the last stop. */
    private atPauseStop(): boolean {
        const { screen } = this;
        return (
            screen.kind === "loaded" && isPauseStop(screen.replay.navigation, screen.view.cursor)
        );
    }

    private togglePlay(): void {
        if (this.screen.kind !== "loaded") {
            return;
        }
        const { playing } = this.screen.autoplay;
        this.setPlaying(!playing && this.stepTarget("next") !== null);
    }

    private setPlaying(playing: boolean): void {
        this.stopAutoplayTimer();
        if (playing) {
            this.stopHold();
        }
        if (this.screen.kind !== "loaded") {
            return;
        }
        const { autoplay } = this.screen;
        if (autoplay.playing !== playing) {
            this.updateLoaded({ autoplay: { ...autoplay, playing } });
        }
        if (playing) {
            this.armAutoplay();
        }
    }

    private armAutoplay(): void {
        const { screen } = this;
        if (screen.kind !== "loaded" || this.disposed) {
            return;
        }
        const delay = autoplayDelayMs(screen.replay, screen.view.cursor, screen.autoplay.speed);
        this.autoplayTimer = this.deps.clock.setTimer(delay, () => this.autoplayTick());
    }

    private stopAutoplayTimer(): void {
        this.autoplayTimer?.();
        this.autoplayTimer = null;
    }

    private autoplayTick(): void {
        this.autoplayTimer = null;
        const { screen } = this;
        if (screen.kind !== "loaded" || !screen.autoplay.playing) {
            return;
        }
        const step = autoplayStep(screen.replay.navigation, screen.view.cursor);
        if (step !== null) {
            this.navigate(step.cursor);
        }
        if (step === null || step.pause) {
            this.setPlaying(false);
        } else {
            this.armAutoplay();
        }
    }

    private cycleSpeed(): void {
        if (this.screen.kind !== "loaded") {
            return;
        }
        const { autoplay } = this.screen;
        this.updateLoaded({ autoplay: { ...autoplay, speed: nextAutoplaySpeed(autoplay.speed) } });
        this.savePrefs();
        if (autoplay.playing) {
            this.stopAutoplayTimer();
            this.armAutoplay();
        }
    }

    /** The next seat at the bottom, where the cursor and the result's page stay; a pin by position would move seats. */
    private switchView(): void {
        if (this.screen.kind !== "loaded") {
            return;
        }
        const { replay, view } = this.screen;
        const bottomSeat = nextSeat(view.bottomSeat, replay.seatCount);
        this.updateLoaded({ pinnedNameplate: null, view: { ...view, bottomSeat } });
        this.writeAddress();
    }

    private toggleHands(): void {
        if (this.screen.kind !== "loaded") {
            return;
        }
        this.updateLoaded({ hideHands: !this.screen.hideHands });
        this.savePrefs();
    }

    private savePrefs(): void {
        if (this.screen.kind === "loaded") {
            const { autoplay, hideHands } = this.screen;
            this.deps.prefs.save({ hideHands, speed: autoplay.speed });
        }
    }

    /**
     * A pointer pressed a step button: it steps at once, and while the press holds, after a delay and then on a beat,
     * until it reaches a result or the end, or the press ends or is cancelled. The click the press ends in is dropped.
     */
    private startHold(direction: StepDirection, event: PointerEvent): void {
        this.pressedStep = null;
        const button = pressedStepButton(event);
        const first = button === null ? null : this.stepTarget(direction);
        if (button === null || first === null) {
            return;
        }
        this.moveTo(first);
        this.pressedStep = button;
        if (event.isTrusted) {
            button.setPointerCapture(event.pointerId);
        }
        this.hold = new HeldStep(button, {
            clock: this.deps.clock,
            end: (cancelled) => this.endHold(cancelled),
            nextStep: () => (this.atPauseStop() ? null : this.stepTarget(direction)),
            step: (cursor) => this.navigate(cursor),
        });
    }

    /** A step button's click: a keyboard's or an assistive technology's steps, the one ending a press is dropped. */
    private onStepClick(direction: StepDirection, event: MouseEvent): void {
        const pressed = this.pressedStep === event.currentTarget;
        this.pressedStep = null;
        const target = pressed ? null : this.stepTarget(direction);
        if (target !== null) {
            this.moveTo(target);
        }
    }

    private endHold(cancelled: boolean): void {
        if (cancelled) {
            this.pressedStep = null;
        }
        this.stopHold();
    }

    private stopHold(): void {
        this.hold?.stop();
        this.hold = null;
    }

    private showResultPage(page: number): void {
        if (this.screen.kind === "loaded") {
            this.moveTo({ ...this.screen.view.cursor, page });
        }
    }

    /**
     * A standings row: its round's result, where the replay holds one. The result replaces the row that held the
     * focus, so the focus goes back to the page's root, where the arrow keys step on from the result.
     */
    private showRoundResult(round: number): void {
        if (this.screen.kind !== "loaded") {
            return;
        }
        const target = roundResultCursor(this.screen.replay.navigation, round);
        if (target !== null) {
            this.moveTo(target);
            this.focusRoot();
        }
    }

    private toggleRoundList(): void {
        if (this.screen.kind !== "loaded") {
            return;
        }
        if (this.screen.roundListOpen) {
            this.closeRoundList();
            return;
        }
        this.updateLoaded({ roundListOpen: true });
        this.host
            .querySelector<HTMLElement>(`.${ROUND_LIST_ROW_CLASS}[aria-current="true"]`)
            ?.focus({ preventScroll: false });
    }

    private closeRoundList(): void {
        this.updateLoaded({ roundListOpen: false });
        this.host
            .querySelector<HTMLElement>(`[aria-controls="${REPLAY_ROUND_LIST_ID}"]`)
            ?.focus({ preventScroll: true });
    }

    private selectRound(start: ReplayCursor): void {
        this.moveTo(start);
        this.closeRoundList();
    }

    /**
     * The wheel steps only over the board, outside the round list and the standings' rounds, and only where a step
     * goes: else it scrolls, and a pinch's zoom is the browser's. A gesture steps once it has run far enough, then on
     * a beat, and once it reaches a result or the end it steps no more until it rests or turns back.
     */
    private onWheel(event: WheelEvent): void {
        const target = isBoardWheel(event)
            ? this.stepTarget(event.deltaY > 0 ? "next" : "prev")
            : null;
        if (target !== null) {
            event.preventDefault();
            this.turnWheel(wheelPixels(event), target);
        }
    }

    private turnWheel(deltaPx: number, target: ReplayCursor): void {
        const { gesture, step } = wheelStep(this.wheelGesture, deltaPx, this.deps.clock.now());
        this.wheelGesture = gesture;
        if (step !== 0) {
            this.moveTo(target);
            this.wheelGesture = { ...gesture, halted: this.atPauseStop() };
        }
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
