import { type TemplateResult, html, nothing, render } from "lit-html";

import "@/styles/replay-page.scss";
import { type Ref, createRef, ref } from "lit-html/directives/ref.js";

import {
    type ClientTimeline,
    readReplayTimeline,
    timelineStates,
    timelineStepEvents,
} from "@/entities/client";
import {
    type ActionStep,
    type BoardPerspective,
    GameBoard,
    GameStartDisplay,
    type NavigationIndex,
    type ResultPaging,
    RoundSelector,
    type ScoreDiffPin,
    type SeatPosition,
    type StepEvent,
    type TableState,
    TurnSelector,
    boardOverlay,
    buildActionSteps,
    buildNavigationIndex,
    roundForStep,
    tableStateToDisplayState,
    turnsForStep,
} from "@/entities/table";
import { type LoadReplay, isAbortError } from "@/shared/api";

export interface ReplayViewDeps {
    readonly loadReplay: LoadReplay;
}

type Dropdown = "round" | "turn";

interface LoadedReplay {
    readonly actionSteps: readonly ActionStep[];
    readonly perspective: BoardPerspective;
    readonly navigationIndex: NavigationIndex;
    readonly parseErrors: readonly string[];
    readonly states: readonly TableState[];
}

type ReplayScreen =
    | { readonly kind: "message"; readonly text: string }
    | {
          readonly kind: "loaded";
          readonly replay: LoadedReplay;
          readonly currentStep: number;
          readonly openDropdown: Dropdown | null;
          /** The page of a round result's panel shown at the current step: a double ron has one per winner. */
          readonly resultPage: number;
          /** The nameplate pinned for the others' score differences, kept from step to step until unpinned. */
          readonly pinnedNameplate: SeatPosition | null;
      };

interface ReplayHandlers {
    readonly root: Ref<HTMLElement>;
    readonly keydown: (event: KeyboardEvent) => void;
    readonly jumpTo: (stepIndex: number) => void;
    readonly next: () => void;
    readonly prev: () => void;
    readonly toggleDropdown: (which: Dropdown) => void;
    readonly showResultPage: (page: number) => void;
    readonly pinNameplate: (seat: SeatPosition | null) => void;
    readonly wheel: { handleEvent: (event: WheelEvent) => void; passive: false };
}

const IGNORED_KEY_TARGETS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/**
 * The User Timing measure of reading a fetched replay: parsing it, reducing it into the client timeline and building
 * its steps and navigation index, before the first render. The layout gate's load budget reads it.
 */
const REPLAY_LOAD_MEASURE = "replay-load";

/** The seat at the bottom when the replay records no game start to name its first dealer. */
const FALLBACK_BOTTOM_SEAT = 0;

function messageScreen(text: string): ReplayScreen {
    return { kind: "message", text };
}

/**
 * A replay is seen from the recorded first dealer's seat for its whole length (`docs/architecture.md`, Replays),
 * with every hand it records face up.
 */
function replayPerspective(events: readonly StepEvent[]): BoardPerspective {
    const gameStart = events.find((event) => event?.type === "game_started");
    const bottomSeat =
        gameStart?.type === "game_started" ? gameStart.dealerSeat : FALLBACK_BOTTOM_SEAT;
    return { bottomSeat, reveal: "all" };
}

function loadedScreen(timeline: ClientTimeline, parseErrors: readonly string[]): ReplayScreen {
    const events = timelineStepEvents(timeline);
    const states = timelineStates(timeline).map((state) => state.table);
    const actionSteps = buildActionSteps(events);
    return {
        currentStep: 0,
        kind: "loaded",
        openDropdown: null,
        pinnedNameplate: null,
        replay: {
            actionSteps,
            navigationIndex: buildNavigationIndex(events, actionSteps, states),
            parseErrors,
            perspective: replayPerspective(events),
            states,
        },
        resultPage: 0,
    };
}

/**
 * What a replay's reading produced, as the `replay-load` measure's detail, so whoever reads the timing can check it
 * timed the whole file: its steps, rounds, unreadable lines and final standings (seat and score), or its refusal.
 */
function loadDetail(screen: ReplayScreen): Record<string, unknown> {
    if (screen.kind === "message") {
        return { refusal: screen.text };
    }
    const { actionSteps, navigationIndex, parseErrors, states } = screen.replay;
    const standings = states.at(-1)?.gameEndResult?.standings ?? [];
    return {
        parseErrors: parseErrors.length,
        rounds: navigationIndex.rounds.length,
        standings: standings.map(({ score, seat }) => [seat, score]),
        steps: actionSteps.length,
    };
}

/** The screen a fetched replay file shows, its reading timed as the `replay-load` measure. */
function readReplayScreen(text: string): ReplayScreen {
    const started = performance.now();
    const read = readReplayTimeline(text);
    const screen = read.ok ? loadedScreen(read.timeline, read.errors) : messageScreen(read.refusal);
    performance.measure(REPLAY_LOAD_MEASURE, { detail: loadDetail(screen), start: started });
    return screen;
}

function elementOf(target: EventTarget | null): Element | null {
    return target instanceof Element ? target : null;
}

interface BoardContent {
    readonly table: TableState;
    readonly perspective: BoardPerspective;
    readonly paging: ResultPaging;
    readonly scoreDiff: ScoreDiffPin;
}

function buildBoardContent({
    paging,
    perspective,
    scoreDiff,
    table,
}: BoardContent): TemplateResult {
    if (table.phase === "pre_game" && table.players.length > 0) {
        return html`<div class="board-overlay">
            <div class="board-overlay__panel">
                ${GameStartDisplay(table.players, table.firstDealerSeat)}
            </div>
        </div>`;
    }
    return GameBoard({
        debug: false,
        overlay: boardOverlay(table, paging),
        scoreDiff,
        state: tableStateToDisplayState(table, perspective),
    });
}

function loadedTemplate(
    screen: Extract<ReplayScreen, { kind: "loaded" }>,
    handlers: ReplayHandlers,
): TemplateResult {
    const { currentStep, openDropdown, pinnedNameplate, replay, resultPage } = screen;
    const step = replay.actionSteps[currentStep];
    const displayState = step ? replay.states[step.stateIndex] : undefined;
    const totalSteps = replay.actionSteps.length;
    const inRound = displayState?.phase === "in_round" || displayState?.phase === "round_ended";
    return html`
        <div class="board-page__board">
            ${
                displayState
                    ? buildBoardContent({
                          paging: { onPage: handlers.showResultPage, page: resultPage },
                          perspective: replay.perspective,
                          scoreDiff: { onPin: handlers.pinNameplate, pinned: pinnedNameplate },
                          table: displayState,
                      })
                    : ""
            }
        </div>
        <div class="board-page__aside replay-controls">
            ${
                replay.parseErrors.length > 0
                    ? html`<div class="replay-state__warning">
                          ${replay.parseErrors.length} line(s) could not be parsed
                      </div>`
                    : ""
            }
            <div class="replay-controls__nav">
                <button
                    class="replay-state__nav-btn"
                    @click=${handlers.prev}
                    ?disabled=${currentStep === 0}
                >&lt;</button>
                ${RoundSelector({
                    currentRound: roundForStep(replay.navigationIndex, currentStep),
                    isOpen: openDropdown === "round",
                    onSelect: handlers.jumpTo,
                    onToggle: () => handlers.toggleDropdown("round"),
                    rounds: replay.navigationIndex.rounds,
                })}
                ${
                    inRound
                        ? TurnSelector({
                              currentStep,
                              isOpen: openDropdown === "turn",
                              onSelect: handlers.jumpTo,
                              onToggle: () => handlers.toggleDropdown("turn"),
                              turns: turnsForStep(replay.navigationIndex, currentStep),
                          })
                        : html`<button class="dropdown-select__trigger" disabled>Turns</button>`
                }
                <button
                    class="replay-state__nav-btn"
                    @click=${handlers.next}
                    ?disabled=${currentStep >= totalSteps - 1}
                >&gt;</button>
            </div>
        </div>
    `;
}

function replayTemplate(screen: ReplayScreen, handlers: ReplayHandlers): TemplateResult {
    return html`
        <div
            class="board-page replay-board-mode"
            tabindex="0"
            ${ref(handlers.root)}
            @keydown=${handlers.keydown}
            @wheel=${handlers.wheel}
        >
            ${
                screen.kind === "loaded"
                    ? loadedTemplate(screen, handlers)
                    : html`<div class="replay-state__message">${screen.text}</div>`
            }
        </div>
    `;
}

function describeRefusedFetch(status: number): string {
    return status === 404 ? "Replay not found" : `Failed to load replay (${status})`;
}

/**
 * The replay viewer for one mount: it loads the replay through the injected `loadReplay`, reads it into the game
 * client's timeline through the dispatcher, then steps through that timeline's states from the controls, the
 * arrow keys and the wheel, rendering the whole view into its host.
 * Its input is its own: the keys reach it only while focus is inside its focusable root, which it focuses on
 * mount unless something else holds focus, and an outside click closes only its own dropdown. Disposing aborts
 * the load, removes its listeners and clears its host; a load that settles afterwards renders nothing.
 */
class ReplayViewController {
    private readonly host: HTMLElement;
    private readonly abort = new AbortController();
    private screen = messageScreen("Loading replay...");
    private disposed = false;

    private readonly handlers: ReplayHandlers = {
        jumpTo: (stepIndex) => this.moveTo(stepIndex, null),
        keydown: (event) => this.onKeydown(event),
        next: () => this.stepBy(1),
        pinNameplate: (seat) => this.pinNameplate(seat),
        prev: () => this.stepBy(-1),
        root: createRef<HTMLElement>(),
        showResultPage: (page) => this.showResultPage(page),
        toggleDropdown: (which) => this.toggleDropdown(which),
        wheel: { handleEvent: (event) => this.onWheel(event), passive: false },
    };

    constructor(host: HTMLElement, gameId: string, deps: ReplayViewDeps) {
        this.host = host;
        host.ownerDocument.addEventListener("click", this.onClickOutside);
        this.show(this.screen);
        this.focusRootUnlessFocusIsElsewhere();
        void this.load(gameId, deps.loadReplay);
    }

    dispose(): void {
        this.disposed = true;
        this.host.ownerDocument.removeEventListener("click", this.onClickOutside);
        this.abort.abort();
        render(nothing, this.host);
    }

    private readonly onClickOutside = (event: MouseEvent): void => {
        const { screen } = this;
        if (screen.kind !== "loaded" || screen.openDropdown === null) {
            return;
        }
        const dropdown = elementOf(event.target)?.closest(".dropdown-select");
        if (dropdown && this.host.contains(dropdown)) {
            return;
        }
        this.show({ ...screen, openDropdown: null });
    };

    private focusRootUnlessFocusIsElsewhere(): void {
        const { activeElement, body } = this.host.ownerDocument;
        if (activeElement === null || activeElement === body) {
            this.handlers.root.value?.focus({ preventScroll: true });
        }
    }

    private onKeydown(event: KeyboardEvent): void {
        const target = elementOf(event.target);
        if (target && IGNORED_KEY_TARGETS.has(target.tagName)) {
            return;
        }
        if (event.key === "ArrowLeft") {
            event.preventDefault();
            this.stepBy(-1);
        } else if (event.key === "ArrowRight") {
            event.preventDefault();
            this.stepBy(1);
        }
    }

    private async load(gameId: string, loadReplay: LoadReplay): Promise<void> {
        try {
            const fetched = await loadReplay(gameId, this.abort.signal);
            if (!fetched.ok) {
                this.show(messageScreen(describeRefusedFetch(fetched.status)));
                return;
            }
            this.show(readReplayScreen(fetched.text));
        } catch (error: unknown) {
            if (!isAbortError(error)) {
                this.show(messageScreen("Failed to load replay"));
            }
        }
    }

    private show(screen: ReplayScreen): void {
        if (this.disposed) {
            return;
        }
        this.screen = screen;
        render(replayTemplate(screen, this.handlers), this.host);
    }

    private moveTo(stepIndex: number, openDropdown: Dropdown | null): void {
        const { screen } = this;
        if (screen.kind !== "loaded") {
            return;
        }
        if (stepIndex < 0 || stepIndex >= screen.replay.actionSteps.length) {
            return;
        }
        this.show({ ...screen, currentStep: stepIndex, openDropdown, resultPage: 0 });
    }

    private showResultPage(page: number): void {
        if (this.screen.kind === "loaded") {
            this.show({ ...this.screen, resultPage: page });
        }
    }

    private pinNameplate(seat: SeatPosition | null): void {
        if (this.screen.kind === "loaded") {
            this.show({ ...this.screen, pinnedNameplate: seat });
        }
    }

    private stepBy(delta: number): void {
        if (this.screen.kind === "loaded") {
            this.moveTo(this.screen.currentStep + delta, this.screen.openDropdown);
        }
    }

    private toggleDropdown(which: Dropdown): void {
        const { screen } = this;
        if (screen.kind === "loaded") {
            this.show({ ...screen, openDropdown: screen.openDropdown === which ? null : which });
        }
    }

    private onWheel(event: WheelEvent): void {
        if (elementOf(event.target)?.closest(".dropdown-select__panel")) {
            return;
        }
        if (event.deltaY > 0) {
            event.preventDefault();
            this.stepBy(1);
        } else if (event.deltaY < 0) {
            event.preventDefault();
            this.stepBy(-1);
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
