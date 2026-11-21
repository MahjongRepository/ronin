import { type TemplateResult, html, nothing, render } from "lit-html";

import "@/styles/replay-page.scss";
import { type Ref, createRef, ref } from "lit-html/directives/ref.js";

import { type GameSound, type MotionSetting, ReplayRotatePanel } from "@/entities/client";
import {
    CURRENT_ROUND_FOCUS_KEY,
    type LoadedReplayScreen,
    type ObserveCountdown,
    type ObserveOpening,
    ROUND_LIST_TOGGLE_FOCUS_KEY,
    ReplayBoard,
    type ReplayBoardHandlers,
    type ReplayFailure,
    type ReplayFocusTarget,
    type ReplayLinks,
    type ReplayOpening,
    type ReplayPageEffect,
    type ReplayPageInput,
    type ReplayPageStep,
    type ReplayPrefsStore,
    type ReplayScreen,
    SEATING_START_FOCUS_KEY,
    type StepDirection,
    TOOLS_FIRST_FOCUS_KEY,
    TOOLS_TOGGLE_FOCUS_KEY,
    canStep,
    replayAddressSearch,
    replayDisplay,
    replayPageDeadline,
    showsHand,
    stepReplayPage,
} from "@/entities/replay";
import { windName } from "@/entities/table";
import {
    type LoadReplay,
    type ObserveFetch,
    type ReplayFetch,
    isAbortError,
    isTimeoutError,
    loadReplayUntilFound,
} from "@/shared/api";
import { type Clock } from "@/shared/clock";
import { type Locale, type MessageKey, type WindScript, t } from "@/shared/i18n";
import {
    type DeadlineTimer,
    type LocalStore,
    type ShortcutKeys,
    type ThrottledWriter,
    assertNever,
    createDeadlineTimer,
    createThrottledWriter,
    focusByKey,
} from "@/shared/lib";
import { LandingClacks } from "@/views/landing-clacks";
import {
    HOLD_EVENTS,
    boardWheel,
    holdInput,
    isCopyKey,
    isOutsideRoundList,
    isOutsideTools,
    keyCommand,
    pressedStepButton,
    stepKeyDirection,
} from "@/views/replay-input";

/** The page's address, which the view reads once and keeps on the position it shows. */
export interface ReplayLocation {
    /** The page's query as it opened, `?` and all, or empty. */
    readonly search: string;
    /** Replace the page's history entry with this query, keeping its path and hash. */
    readonly replaceSearch: (search: string) => void;
    /** Call `listener` whenever the page is hidden or left; returns its removal. */
    readonly onPageHide: (listener: () => void) => () => void;
}

export type { ReplayLinks } from "@/entities/replay";

/** Fetch a game's observe stream from cursor `from`, as `fetchObserve` does. */
export type FetchObserve = (
    gameId: string,
    from: number,
    signal: AbortSignal,
) => Promise<ObserveFetch>;

/** Where the page's replay comes from: a saved game's file, or a game being played, watched behind the table. */
export type ReplayViewSource =
    | { readonly kind: "archive"; readonly loadReplay: LoadReplay }
    | { readonly kind: "observe"; readonly fetchObserve: FetchObserve };

export interface ReplayViewDeps {
    readonly source: ReplayViewSource;
    readonly clock: Clock;
    readonly location: ReplayLocation;
    readonly links: ReplayLinks;
    /** Whose shortcut names the page shows: Apple's ⌘ or the others' Ctrl. */
    readonly shortcuts: ShortcutKeys;
    /** The reader's own settings: whether the other hands hide. */
    readonly prefs: ReplayPrefsStore;
    /** The game's sounds, which a step on plays while the setting the live game shares keeps them on. */
    readonly sound: GameSound;
    /** Whether the board animates, a setting the live game shares. */
    readonly motionSetting: LocalStore<MotionSetting>;
    readonly prefersReducedMotion: () => boolean;
    readonly setLanguage: (locale: Locale) => void;
    readonly setWinds: (script: WindScript) => void;
    readonly setTileLabels: (on: boolean) => void;
    /** Put `text` on the clipboard; rejects where the browser refuses it. */
    readonly copyText: (text: string) => Promise<void>;
    /** Open `url` in a new tab. */
    readonly openUrl: (url: string) => void;
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

/** The focus key of each target but the root; the current round scrolls into view, the others stay where they are. */
const FOCUS_KEYS: Readonly<Record<Exclude<ReplayFocusTarget, "root">, string>> = {
    current_round: CURRENT_ROUND_FOCUS_KEY,
    round_list_toggle: ROUND_LIST_TOGGLE_FOCUS_KEY,
    start: SEATING_START_FOCUS_KEY,
    tools: TOOLS_FIRST_FOCUS_KEY,
    tools_toggle: TOOLS_TOGGLE_FOCUS_KEY,
};

interface ReplayHandlers extends ReplayBoardHandlers {
    readonly root: Ref<HTMLElement>;
    readonly keydown: (event: KeyboardEvent) => void;
    readonly keyup: (event: KeyboardEvent) => void;
    readonly retry: () => void;
    readonly wheel: { handleEvent: (event: WheelEvent) => void; passive: false };
}

interface FailureText {
    readonly title: string;
    readonly detail: string;
    readonly retry: boolean;
}

type UnshowableFailure = Exclude<ReplayFailure, { kind: "not_found" | "refused" | "unreachable" }>;

const PLAIN_FAILURE_DETAILS: Readonly<
    Record<"empty" | "no_version_record" | "show_failed" | "too_large", MessageKey>
> = {
    empty: "replay.failure.empty",
    no_version_record: "replay.failure.no_version_record",
    show_failed: "replay.failure.show_failed",
    too_large: "replay.failure.too_large",
};

function unshowableDetail(failure: UnshowableFailure): string {
    switch (failure.kind) {
        case "unsupported_version": {
            return t("replay.failure.unsupported_version", { version: failure.version });
        }
        case "incomplete_record": {
            return t("replay.failure.incomplete_record", { record: failure.record });
        }
        case "invalid_record": {
            return t("replay.failure.unreadable_record", { record: failure.record });
        }
        case "no_deal": {
            return failure.damage === null
                ? t("replay.failure.no_deal")
                : t("replay.failure.no_deal_damaged", { record: failure.damage.lineNumber });
        }
        case "empty":
        case "no_version_record":
        case "too_large":
        case "show_failed": {
            return t(PLAIN_FAILURE_DETAILS[failure.kind]);
        }
        default: {
            return assertNever(failure);
        }
    }
}

function failureText(failure: ReplayFailure): FailureText {
    switch (failure.kind) {
        case "not_found": {
            return {
                detail: t("replay.failure.not_found"),
                retry: true,
                title: t("replay.error.not_found"),
            };
        }
        case "refused": {
            return {
                detail: t("replay.failure.server_status", { status: String(failure.status) }),
                retry: true,
                title: t("replay.error.failed"),
            };
        }
        case "unreachable": {
            return {
                detail: t("replay.failure.unreachable"),
                retry: true,
                title: t("replay.error.failed"),
            };
        }
        default: {
            return {
                detail: unshowableDetail(failure),
                retry: false,
                title: t(
                    failure.kind === "no_deal"
                        ? "replay.failure.no_round"
                        : "replay.error.cannot_show",
                ),
            };
        }
    }
}

function logReadFailure(screen: ReplayScreen): void {
    if (screen.kind === "failed" && screen.failure.kind === "invalid_record") {
        console.error("The replay could not be read:", screen.failure.cause);
    }
}

/** Whether `element` is drawn: a control the board's stylesheet hides (an option under a small board's panel) is not. */
function isShown(element: HTMLElement): boolean {
    return typeof element.checkVisibility !== "function" || element.checkVisibility();
}

/** What a loaded screen keeps but never draws: the hold, the click a press drops and the wheel's gesture. */
const UNDRAWN = { hold: null, pressedStep: null, wheel: null } as const;

/** Whether two objects hold the same fields, each the same value. */
function sameFields(first: object, second: object): boolean {
    const other = new Map(Object.entries(second));
    const fields = Object.entries(first);
    return (
        fields.length === other.size &&
        fields.every(([name, value]) => other.has(name) && Object.is(value, other.get(name)))
    );
}

/**
 * Whether two screens draw the same page: they differ in nothing but what a screen keeps and never draws (the hold,
 * the click a press drops, the wheel's gesture, autoplay's next move and the observe stream's cursor and next
 * request), so a change to those alone draws nothing.
 */
function drawsAlike(shown: ReplayScreen, next: ReplayScreen): boolean {
    if (shown === next) {
        return true;
    }
    if (shown.kind !== "loaded" || next.kind !== "loaded") {
        return false;
    }
    return (
        sameFields(
            { ...shown, ...UNDRAWN, autoplay: null, observe: null },
            { ...next, ...UNDRAWN, autoplay: null, observe: null },
        ) &&
        sameFields({ ...shown.autoplay, dueAt: null }, { ...next.autoplay, dueAt: null }) &&
        sameFields(
            { ...shown.observe, next: null, pollAt: null },
            { ...next.observe, next: null, pollAt: null },
        )
    );
}

/** What the page draws beside its screen: the ways out and whose shortcut names it shows. */
type ReplayChrome = Pick<ReplayViewDeps, "links" | "shortcuts">;

function loadedTemplate(
    screen: LoadedReplayScreen,
    { links, shortcuts }: ReplayChrome,
    handlers: ReplayHandlers,
): TemplateResult {
    const { hideHands, observe, replay, seating, shownCall, view } = screen;
    const perspective = {
        bottomSeat: view.bottomSeat,
        reveal: hideHands ? "bottom" : "all",
    } as const;
    const display = replayDisplay(replay, {
        cursor: view.cursor,
        observe,
        perspective,
        seating,
        shownCall,
    });
    return html`
        <div class="board-page__board">
            ${ReplayBoard({ display, handlers, links, screen, shortcuts })}
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
            ${text.retry ? html`<button type="button" @click=${handlers.retry}>${t("common.try_again")}</button>` : nothing}
            <a href=${links.history} role="button" class=${text.retry ? "secondary" : ""}>${t("common.game_history")}</a>
            <a href=${links.lobby} role="button" class="secondary">${t("common.lobby")}</a>
        </div>
    </div>`;
}

/** The page once even its failed screen could not be drawn: why, and the ways back, with nothing of the replay. */
function brokenTemplate(links: ReplayLinks): TemplateResult {
    return html`<div class="replay-state replay-state--failed replay-state--broken" role="alert">
        <p class="replay-state__detail">${t("replay.failure.page_broken")}</p>
        <div class="replay-state__links">
            <a href=${links.history} role="button">${t("common.game_history")}</a>
            <a href=${links.lobby} role="button" class="secondary">${t("common.lobby")}</a>
        </div>
    </div>`;
}

function loadingTemplate(waiting: boolean): TemplateResult {
    return html`<div class="replay-state" role="status" aria-busy="true">
        <p class="replay-state__detail">
            ${waiting ? t("replay.loading.waiting") : t("replay.loading.loading")}
        </p>
    </div>`;
}

/** The time left as minutes and seconds, a part second counted whole. */
function countdownTime(remainingMs: number): string {
    const seconds = Math.ceil(remainingMs / 1000);
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** An observed game before it can be played: its players East to North and the time left, or loading before any. */
function observeWaitingTemplate(countdown: ObserveCountdown | null): TemplateResult {
    if (countdown === null) {
        return html`<div class="replay-state" role="status" aria-busy="true">
            <p class="replay-state__detail">${t("replay.observe.loading")}</p>
        </div>`;
    }
    return html`<div class="replay-state replay-state--observe">
        <h1 class="replay-state__title">${t("replay.observe.title")}</h1>
        <ol class="replay-state__players" aria-label=${t("replay.observe.players")}>
            ${countdown.players.map(
                (name, wind) => html`<li>
                    <span class="replay-state__wind">${windName(wind)}</span>
                    <span>${name}</span>
                </li>`,
            )}
        </ol>
        <p class="replay-state__detail">${t("replay.observe.delay_note")}</p>
        <p class="replay-state__countdown">
            ${
                countdown.remainingMs > 0
                    ? t("replay.observe.countdown", { time: countdownTime(countdown.remainingMs) })
                    : t("replay.observe.starting")
            }
        </p>
    </div>`;
}

/** An observed game the server no longer holds, before any of it could be played: its saved replay and the lobby. */
function observeGoneTemplate(links: ReplayLinks): TemplateResult {
    return html`<div class="replay-state replay-state--failed" role="alert">
        <h1 class="replay-state__title">${t("replay.observe.gone")}</h1>
        <p class="replay-state__detail">${t("replay.observe.gone_detail")}</p>
        <div class="replay-state__links">
            <a href=${links.replay} role="button">${t("replay.observe.replay_link")}</a>
            <a href=${links.lobby} role="button" class="secondary">${t("common.lobby")}</a>
        </div>
    </div>`;
}

function screenTemplate(
    screen: ReplayScreen,
    chrome: ReplayChrome,
    handlers: ReplayHandlers,
): TemplateResult {
    switch (screen.kind) {
        case "loaded": {
            return loadedTemplate(screen, chrome, handlers);
        }
        case "failed": {
            return failedTemplate(screen.failure, chrome.links, handlers);
        }
        case "loading": {
            return loadingTemplate(screen.waiting);
        }
        case "observe_waiting": {
            return observeWaitingTemplate(screen.countdown);
        }
        case "observe_gone": {
            return observeGoneTemplate(chrome.links);
        }
        default: {
            return assertNever(screen);
        }
    }
}

function replayTemplate(
    screen: ReplayScreen,
    chrome: ReplayChrome,
    handlers: ReplayHandlers,
): TemplateResult {
    return html`
        ${screen.kind === "loaded" ? ReplayRotatePanel(chrome.links.history) : nothing}
        <div
            class="board-page replay-board-mode"
            tabindex="0"
            ${ref(handlers.root)}
            @keydown=${handlers.keydown}
            @keyup=${handlers.keyup}
            @wheel=${handlers.wheel}
        >
            ${screenTemplate(screen, chrome, handlers)}
        </div>
    `;
}

/**
 * The replay viewer for one mount: it loads the replay through its source, a saved game's `loadReplay` (asking again
 * while the server has not stored it yet) or an observed game's `fetchObserve` (asked again whenever the page's
 * screen says so, one request at a time), steps the page's reducer (`stepReplayPage`) with every input stamped with the
 * clock's time, renders the screen it returns into its host and runs the effects it asks for: the address kept on the
 * position shown, a step's sounds played, the reader's settings saved and the focus moved. It keeps one timer armed to the screen's deadline
 * (autoplay's next move, a held button's next repeat), which comes back as a tick. Its input is its own: the keys
 * reach it only while focus is inside its focusable root, which it focuses on mount unless something else holds
 * focus, and an outside click closes only its own round list. A throw in a step or a render says the replay cannot be
 * shown, its error on the console. Disposing aborts the load and its retries or the observe request in flight, cancels
 * every timer, drops an address write still waiting, removes its listeners and clears its host; a load that settles afterwards renders nothing.
 */
class ReplayViewController {
    private readonly host: HTMLElement;
    private readonly deps: ReplayViewDeps;
    private readonly gameId: string;
    private readonly addressWriter: ThrottledWriter<string>;
    private readonly removePageHide: () => void;
    private abort = new AbortController();
    private screen: ReplayScreen = { kind: "loading", waiting: false };
    private disposed = false;
    /** The failed screen could not be drawn either, so the page shows the bare notice and draws nothing more. */
    private broken = false;
    private readonly timer: DeadlineTimer;
    private readonly clacks: LandingClacks;
    /** The step button a hold follows, whose pointer events the view listens to while the screen holds it. */
    private held: HTMLElement | null = null;

    private readonly handlers: ReplayHandlers = {
        analyzeHand: () => this.dispatch({ kind: "analyze_hand" }),
        closeRoundList: () => this.dispatch({ kind: "close_round_list" }),
        closeSettings: () => this.dispatch({ kind: "close_settings" }),
        closeTools: () => this.dispatch({ kind: "close_tools" }),
        copyHand: () => this.dispatch({ kind: "copy_hand" }),
        keydown: (event) => this.onKeydown(event),
        keyup: (event) => this.onKeyup(event),
        move: (cursor) => this.dispatch({ cursor, kind: "move" }),
        nextView: () => this.dispatch({ command: "view", kind: "key", repeat: false }),
        retry: () => this.startLoad(),
        root: createRef<HTMLElement>(),
        selectRound: (cursor) => this.dispatch({ cursor, kind: "select_round" }),
        setLanguage: (locale) => this.changeLanguage(locale),
        setTileLabels: (on) => this.changeTileLabels(on),
        setWinds: (script) => this.changeWinds(script),
        showResultPage: (page) => this.dispatch({ kind: "result_page", page }),
        start: () => this.dispatch({ kind: "start" }),
        stepClick: (direction) => this.dispatch({ direction, kind: "step_click" }),
        stepPress: (direction, event) => this.onStepPress(direction, event),
        toggleAnimations: () => this.dispatch({ kind: "toggle_animations" }),
        toggleHands: () => this.dispatch({ kind: "toggle_hands" }),
        togglePlay: () => this.dispatch({ kind: "toggle_play" }),
        toggleRoundList: () => this.dispatch({ kind: "toggle_round_list" }),
        toggleSettings: () => this.dispatch({ kind: "toggle_settings" }),
        toggleSound: () => this.dispatch({ kind: "toggle_sound" }),
        toggleTools: () => this.dispatch({ kind: "toggle_tools" }),
        toggleTsumogiri: () => this.dispatch({ kind: "toggle_tsumogiri" }),
        viewSeat: (seat) => this.dispatch({ kind: "view_seat", seat }),
        wheel: { handleEvent: (event) => this.onWheel(event), passive: false },
    };

    constructor(host: HTMLElement, gameId: string, deps: ReplayViewDeps) {
        this.host = host;
        this.deps = deps;
        this.gameId = gameId;
        this.timer = createDeadlineTimer(deps.clock, (at) =>
            this.guard(() => this.apply(stepReplayPage(this.screen, { at, kind: "tick" }))),
        );
        this.clacks = new LandingClacks(deps.clock, deps.sound);
        this.addressWriter = createThrottledWriter(
            deps.clock,
            REPLAY_URL_WRITE_INTERVAL_MS,
            deps.location.replaceSearch,
        );
        this.removePageHide = deps.location.onPageHide(() => this.onPageHide());
        host.ownerDocument.addEventListener("click", this.onClickOutside);
        this.open();
    }

    /** Show the loading screen, take the focus where nothing else holds it and start the load. */
    private open(): void {
        this.show(this.screen);
        this.focusRootUnlessFocusIsElsewhere();
        this.startLoad();
    }

    dispose(): void {
        this.disposed = true;
        this.timer.disarm();
        this.clacks.cancel();
        this.releaseHold();
        this.host.ownerDocument.removeEventListener("click", this.onClickOutside);
        this.removePageHide();
        this.addressWriter.cancel();
        this.abort.abort();
        render(nothing, this.host);
    }

    private changeLanguage(locale: Locale): void {
        this.deps.setLanguage(locale);
        this.guard(() => this.show(this.screen));
    }

    private changeWinds(script: WindScript): void {
        this.deps.setWinds(script);
        this.guard(() => this.show(this.screen));
    }

    private changeTileLabels(on: boolean): void {
        this.deps.setTileLabels(on);
        this.guard(() => this.show(this.screen));
    }

    private readonly onClickOutside = (event: MouseEvent): void => {
        if (isOutsideRoundList(event, this.host)) {
            this.dispatch({ kind: "dismiss_round_list" });
        }
        if (isOutsideTools(event, this.host)) {
            this.dispatch({ kind: "dismiss_tools" });
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
        if (this.disposed || this.broken) {
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
        this.followClacks(screen);
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

    private followClacks(next: ReplayScreen): void {
        const shown = this.screen;
        if (next.kind !== "loaded" || !next.soundOn || shown.kind !== "loaded") {
            this.clacks.cancel();
            return;
        }
        const [from, to] = [shown.view.cursor.stop, next.view.cursor.stop];
        if (to === from + 1) {
            this.clacks.landNow();
        } else if (to !== from) {
            this.clacks.cancel();
        }
    }

    /**
     * Say the replay cannot be shown after a throw, the error on the console; where drawing that throws too, show a
     * bare notice with the ways back that draws nothing of the replay.
     */
    private fail(error: unknown): void {
        console.error("The replay could not be shown:", error);
        try {
            const at = this.deps.clock.now();
            this.apply(stepReplayPage(this.screen, { at, kind: "show_failed" }));
        } catch (drawError: unknown) {
            this.showBroken(drawError);
        }
    }

    /** Give up drawing the replay for good: the bare notice with the ways back, no timer armed and no hold followed. */
    private showBroken(drawError: unknown): void {
        console.error("The failed replay page could not be drawn:", drawError);
        this.broken = true;
        this.timer.disarm();
        this.releaseHold();
        this.abort.abort();
        this.addressWriter.cancel();
        render(brokenTemplate(this.deps.links), this.host);
    }

    private runEffect(effect: ReplayPageEffect): void {
        switch (effect.kind) {
            case "write_address": {
                return this.writeAddress();
            }
            case "play_sounds": {
                return this.clacks.play(effect.cues, this.motionEffective());
            }
            case "save_prefs":
            case "save_sound":
            case "save_animations": {
                this.saveSetting(effect);
                return;
            }
            case "focus": {
                return this.focus(effect.target);
            }
            case "copy_text": {
                return void this.copyText(effect.text);
            }
            case "open_url": {
                return this.deps.openUrl(effect.url);
            }
            case "fetch_observe": {
                return void this.pollObserve(effect.from);
            }
            default: {
                assertNever(effect);
            }
        }
    }

    /** Put the text on the clipboard, then say whether it went through; a refusal's cause goes to the console. */
    private async copyText(text: string): Promise<void> {
        try {
            await this.deps.copyText(text);
        } catch (error: unknown) {
            console.error("The hand could not be copied:", error);
            this.dispatch({ kind: "hand_copy", outcome: "failed" });
            return;
        }
        this.dispatch({ kind: "hand_copy", outcome: "copied" });
    }

    /** Keep the reader's settings, or the sound's or the animations', which the live game shares. */
    private saveSetting(
        effect: Extract<
            ReplayPageEffect,
            { kind: "save_prefs" | "save_sound" | "save_animations" }
        >,
    ): void {
        if (effect.kind === "save_prefs") {
            this.deps.prefs.save(effect.prefs);
            return;
        }
        if (effect.kind === "save_sound") {
            this.deps.sound.setting.save({ sound_on: effect.soundOn });
            return;
        }
        this.deps.motionSetting.save({ animations: effect.animationsOn });
    }

    private motionEffective(): boolean {
        return (
            this.screen.kind === "loaded" &&
            this.screen.animationsOn &&
            !this.deps.prefersReducedMotion()
        );
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
        if (target === "root") {
            this.handlers.root.value?.focus({ preventScroll: true });
            return;
        }
        focusByKey(this.host, FOCUS_KEYS[target], { preventScroll: target !== "current_round" });
    }

    /**
     * A key the page takes, prevented while a replay shows: Enter and Space on a step button are prevented, so the
     * button's own click never repeats the step the key took.
     */
    private onKeydown(event: KeyboardEvent): void {
        if (isCopyKey(event)) {
            this.onCopyKey(event);
            return;
        }
        const command = keyCommand(event);
        if (command !== null && this.screen.kind === "loaded") {
            event.preventDefault();
        }
        this.dispatch({ command, kind: "key", repeat: event.repeat });
    }

    /** Ctrl+C or Cmd+C copies the hand shown, unless text is selected, which the browser copies as ever. */
    private onCopyKey(event: KeyboardEvent): void {
        const selection = this.host.ownerDocument.getSelection();
        if ((selection !== null && !selection.isCollapsed) || !showsHand(this.screen)) {
            return;
        }
        event.preventDefault();
        this.dispatch({ kind: "copy_hand" });
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
        const { source } = this.deps;
        if (source.kind === "observe") {
            this.dispatch({ kind: "observe_started" });
            return;
        }
        this.dispatch({ kind: "load_started" });
        void this.load(source.loadReplay, this.abort.signal);
    }

    private async load(loadReplay: LoadReplay, signal: AbortSignal): Promise<void> {
        const fetched = await this.fetchReplay(loadReplay, signal);
        if (fetched !== null) {
            this.guard(() => this.apply(this.readFetched(fetched)));
        }
    }

    /**
     * Ask the observe stream for its records from `from` and step the page with the answer; an answer after the page
     * aborted the request (dispose, a retry) is dropped.
     */
    private async pollObserve(from: number): Promise<void> {
        const { source } = this.deps;
        if (source.kind !== "observe") {
            return;
        }
        const { signal } = this.abort;
        const fetched = await this.askObserve(source.fetchObserve, from, signal);
        if (fetched !== null && !signal.aborted) {
            this.dispatch({ fetched, kind: "observe_fetched", opening: this.observeOpening() });
        }
    }

    /**
     * The stream's answer, or null once the request was aborted or failed. A failure, which the page asks again after,
     * is the network's or a body that is no observe answer, whose cause goes to the console.
     */
    private async askObserve(
        fetchObserve: FetchObserve,
        from: number,
        signal: AbortSignal,
    ): Promise<ObserveFetch | null> {
        try {
            return await fetchObserve(this.gameId, from, signal);
        } catch (error: unknown) {
            if (!isAbortError(error) && !signal.aborted) {
                this.onObserveFailed(error);
            }
            return null;
        }
    }

    private onObserveFailed(error: unknown): void {
        if (!(error instanceof TypeError) && !isTimeoutError(error)) {
            console.error("The observe answer could not be read:", error);
        }
        this.dispatch({ kind: "observe_unreachable" });
    }

    private observeOpening(): ObserveOpening {
        return {
            animationsOn: this.deps.motionSetting.load().animations,
            prefs: this.deps.prefs.load(),
            roundListOpen: this.deps.roundListOpen ?? false,
            soundOn: this.deps.sound.setting.load().sound_on,
        };
    }

    /** The fetched replay, or null once the load was aborted or the page shows the server as unreachable. */
    private async fetchReplay(
        loadReplay: LoadReplay,
        signal: AbortSignal,
    ): Promise<ReplayFetch | null> {
        try {
            return await loadReplayUntilFound(loadReplay, this.gameId, {
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
            animationsOn: this.deps.motionSetting.load().animations,
            autoplay: this.deps.autoplay ?? false,
            prefs: this.deps.prefs.load(),
            roundListOpen: this.deps.roundListOpen ?? false,
            search: this.deps.location.search,
            soundOn: this.deps.sound.setting.load().sound_on,
        };
        const step = stepReplayPage(this.screen, {
            at: this.deps.clock.now(),
            fetched,
            kind: "fetched",
            opening,
        });
        logReadFailure(step.screen);
        return step;
    }

    /**
     * Render the screen. Focus that was inside the page and lost its element to the render (a result's pager, the
     * seating's start, a move that can go no further, an option a panel hides) goes back to the page's root, so its keys
     * go on.
     */
    private show(screen: ReplayScreen): void {
        this.screen = screen;
        const { ownerDocument } = this.host;
        const hadFocus = this.host.contains(ownerDocument.activeElement);
        render(replayTemplate(screen, this.deps, this.handlers), this.host);
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
