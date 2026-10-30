import { type TemplateResult, html, nothing, render } from "lit-html";

import "@/styles/replay-page.scss";
import { type Ref, createRef, ref } from "lit-html/directives/ref.js";

import { type LoadedReplay, type ReplayUnshowable, readReplay } from "@/entities/client";
import {
    GameBoard,
    REPLAY_ROUND_LIST_ID,
    ROUND_LIST_ROW_CLASS,
    ReplayControls,
    type ReplayCursor,
    type ReplayView,
    RoundList,
    type ScoreDiffPin,
    type SeatPosition,
    boardOverlay,
    nextCursor,
    parseReplayAddress,
    prevCursor,
    replayAddressSearch,
    replayDisplay,
    resolveReplayAddress,
    tableStateToDisplayState,
} from "@/entities/table";
import {
    type LoadReplay,
    type ReplayFetch,
    isAbortError,
    loadReplayUntilFound,
} from "@/shared/api";
import { type Clock } from "@/shared/clock";
import { type ThrottledWriter, assertNever, createThrottledWriter } from "@/shared/lib";

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
    /** Open on the round list, as a storybook state shows it; closed when omitted. */
    readonly roundListOpen?: boolean;
}

/**
 * The fewest milliseconds between two writes of the address bar: Safari refuses more than 100 history writes in 30
 * seconds, which a held key or autoplay would reach. A move within it is written once it has passed.
 */
export const REPLAY_URL_WRITE_INTERVAL_MS = 500;

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
}

type ReplayScreen =
    | { readonly kind: "loading"; readonly waiting: boolean }
    | { readonly kind: "failed"; readonly failure: ReplayFailure }
    | LoadedScreen;

interface ReplayHandlers {
    readonly root: Ref<HTMLElement>;
    readonly keydown: (event: KeyboardEvent) => void;
    readonly move: (cursor: ReplayCursor) => void;
    readonly showResultPage: (page: number) => void;
    readonly pinNameplate: (seat: SeatPosition | null) => void;
    readonly toggleRoundList: () => void;
    readonly closeRoundList: () => void;
    readonly selectRound: (start: ReplayCursor) => void;
    readonly retry: () => void;
    readonly wheel: { handleEvent: (event: WheelEvent) => void; passive: false };
}

const IGNORED_KEY_TARGETS = new Set(["INPUT", "TEXTAREA", "SELECT"]);
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

function loadedScreen(replay: LoadedReplay, search: string, roundListOpen: boolean): ReplayScreen {
    const view = resolveReplayAddress(replay.navigation, parseReplayAddress(search), {
        count: replay.seatCount,
        fallback: replay.firstDealerSeat,
    });
    if (view === null) {
        return { failure: { damage: replay.damage, kind: "no_deal" }, kind: "failed" };
    }
    return {
        kind: "loaded",
        pinnedNameplate: null,
        replay,
        roundListOpen,
        view,
    };
}

/** The screen a fetched replay file shows at the page's address, its reading timed as the `replay-load` measure. */
function readReplayScreen(text: string, search: string, roundListOpen: boolean): ReplayScreen {
    const started = performance.now();
    const read = readReplay(text);
    const screen: ReplayScreen = read.ok
        ? loadedScreen(read.replay, search, roundListOpen)
        : { failure: read.unshowable, kind: "failed" };
    performance.measure(REPLAY_LOAD_MEASURE, { detail: loadDetail(screen), start: started });
    return screen;
}

function elementOf(target: EventTarget | null): Element | null {
    return target instanceof Element ? target : null;
}

function loadedTemplate(screen: LoadedScreen, handlers: ReplayHandlers): TemplateResult {
    const { pinnedNameplate, replay, roundListOpen, view } = screen;
    const perspective = { bottomSeat: view.bottomSeat, reveal: "all" } as const;
    const display = replayDisplay(replay, view.cursor, perspective);
    const scoreDiff: ScoreDiffPin = { onPin: handlers.pinNameplate, pinned: pinnedNameplate };
    return html`
        <div class="board-page__board">
            ${GameBoard({
                debug: false,
                overlay: boardOverlay(display.table, {
                    onPage: handlers.showResultPage,
                    page: view.cursor.page,
                }),
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
                onMove: handlers.move,
                onToggleRoundList: handlers.toggleRoundList,
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
    links: ReplayLinks,
    handlers: ReplayHandlers,
): TemplateResult {
    switch (screen.kind) {
        case "loaded": {
            return loadedTemplate(screen, handlers);
        }
        case "failed": {
            return failedTemplate(screen.failure, links, handlers);
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
    links: ReplayLinks,
    handlers: ReplayHandlers,
): TemplateResult {
    return html`
        <div
            class="board-page replay-board-mode"
            tabindex="0"
            ${ref(handlers.root)}
            @keydown=${handlers.keydown}
            @wheel=${handlers.wheel}
        >
            ${screenTemplate(screen, links, handlers)}
        </div>
    `;
}

/**
 * The replay viewer for one mount: it loads the replay through the injected `loadReplay` (asking again while the
 * server has not stored it yet), reads it into the game client's timeline through the dispatcher, opens it where the
 * page's address says (else on the first deal) and moves through its stops from the controls, the round list, the
 * arrow keys and the wheel, rendering the whole view into its host and keeping the address on the position shown.
 * Its input is its own: the keys reach it only while focus is inside its focusable root, which it focuses on
 * mount unless something else holds focus, and an outside click closes only its own round list. Disposing aborts
 * the load and its retries, drops an address write still waiting, removes its listeners and clears its host; a load
 * that settles afterwards renders nothing.
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

    private readonly handlers: ReplayHandlers = {
        closeRoundList: () => this.closeRoundList(),
        keydown: (event) => this.onKeydown(event),
        move: (cursor) => this.moveTo(cursor),
        pinNameplate: (seat) => this.updateLoaded({ pinnedNameplate: seat }),
        retry: () => this.startLoad(),
        root: createRef<HTMLElement>(),
        selectRound: (start) => this.selectRound(start),
        showResultPage: (page) => this.showResultPage(page),
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
        this.removePageHide = deps.location.onPageHide(() => this.addressWriter.flush());
        host.ownerDocument.addEventListener("click", this.onClickOutside);
        this.show(this.screen);
        this.focusRootUnlessFocusIsElsewhere();
        this.startLoad();
    }

    dispose(): void {
        this.disposed = true;
        this.host.ownerDocument.removeEventListener("click", this.onClickOutside);
        this.removePageHide();
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

    private focusRootUnlessFocusIsElsewhere(): void {
        const { activeElement, body } = this.host.ownerDocument;
        if (activeElement === null || activeElement === body) {
            this.handlers.root.value?.focus({ preventScroll: true });
        }
    }

    private onKeydown(event: KeyboardEvent): void {
        const target = elementOf(event.target);
        if (target && (IGNORED_KEY_TARGETS.has(target.tagName) || target.closest(".round-list"))) {
            return;
        }
        if (event.key === "ArrowLeft") {
            event.preventDefault();
            this.stepBy("prev");
        } else if (event.key === "ArrowRight") {
            event.preventDefault();
            this.stepBy("next");
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
                readReplayScreen(text, this.deps.location.search, this.deps.roundListOpen ?? false),
            );
        } catch (error: unknown) {
            console.error("The replay could not be shown:", error);
            this.show({ failure: { kind: "show_failed" }, kind: "failed" });
        }
    }

    private showLoaded(screen: ReplayScreen): void {
        this.show(screen);
        this.writeAddress();
    }

    private show(screen: ReplayScreen): void {
        if (this.disposed) {
            return;
        }
        this.screen = screen;
        render(replayTemplate(screen, this.deps.links, this.handlers), this.host);
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

    private moveTo(cursor: ReplayCursor): void {
        if (this.screen.kind !== "loaded") {
            return;
        }
        this.updateLoaded({ view: { ...this.screen.view, cursor } });
        this.writeAddress();
    }

    /** Where one step toward `direction` goes from the cursor shown; null when nothing is loaded or it cannot go on. */
    private stepTarget(direction: "next" | "prev"): ReplayCursor | null {
        const { screen } = this;
        if (screen.kind !== "loaded") {
            return null;
        }
        const { navigation } = screen.replay;
        const { cursor } = screen.view;
        return direction === "next"
            ? nextCursor(navigation, cursor)
            : prevCursor(navigation, cursor);
    }

    private stepBy(direction: "next" | "prev"): void {
        const target = this.stepTarget(direction);
        if (target !== null) {
            this.moveTo(target);
        }
    }

    private showResultPage(page: number): void {
        if (this.screen.kind === "loaded") {
            this.moveTo({ ...this.screen.view.cursor, page });
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

    /** The wheel steps only over the board, outside the round list, and only where a step goes: else it scrolls. */
    private onWheel(event: WheelEvent): void {
        const over = elementOf(event.target);
        if (
            event.deltaY === 0 ||
            !over?.closest(".board-page__board") ||
            over.closest(".round-list")
        ) {
            return;
        }
        const target = this.stepTarget(event.deltaY > 0 ? "next" : "prev");
        if (target !== null) {
            event.preventDefault();
            this.moveTo(target);
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
