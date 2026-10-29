import { type TemplateResult, html, nothing, render } from "lit-html";
import { type Ref, createRef, ref } from "lit-html/directives/ref.js";

import {
    type ActionStep,
    GameBoard,
    GameEndDisplay,
    GameStartDisplay,
    type NavigationIndex,
    type ParsedReplay,
    RoundEndDisplay,
    RoundSelector,
    type TableState,
    TurnSelector,
    buildActionSteps,
    buildNavigationIndex,
    buildTimeline,
    parseReplayLines,
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
      };

interface ReplayHandlers {
    readonly root: Ref<HTMLElement>;
    readonly keydown: (event: KeyboardEvent) => void;
    readonly jumpTo: (stepIndex: number) => void;
    readonly next: () => void;
    readonly prev: () => void;
    readonly toggleDropdown: (which: Dropdown) => void;
    readonly wheel: { handleEvent: (event: WheelEvent) => void; passive: false };
}

const IGNORED_KEY_TARGETS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

function messageScreen(text: string): ReplayScreen {
    return { kind: "message", text };
}

function loadedScreen(parsed: ParsedReplay): ReplayScreen {
    const { events } = parsed;
    const states = buildTimeline(events);
    const actionSteps = buildActionSteps(events);
    return {
        currentStep: 0,
        kind: "loaded",
        openDropdown: null,
        replay: {
            actionSteps,
            navigationIndex: buildNavigationIndex(events, actionSteps, states),
            parseErrors: parsed.errors,
            states,
        },
    };
}

function elementOf(target: EventTarget | null): Element | null {
    return target instanceof Element ? target : null;
}

function buildOverlay(tableState: TableState): TemplateResult | undefined {
    if (tableState.phase === "round_ended" && tableState.roundEndResult) {
        return RoundEndDisplay(
            tableState.roundEndResult,
            tableState.players,
            tableState.dealerSeat,
        );
    }
    if (tableState.phase === "game_ended" && tableState.gameEndResult) {
        return GameEndDisplay(tableState.gameEndResult, tableState.players);
    }
    return undefined;
}

function buildBoardContent(tableState: TableState): TemplateResult {
    if (tableState.phase === "pre_game" && tableState.players.length > 0) {
        return html`<div class="board-overlay">
            <div class="board-overlay__panel">
                ${GameStartDisplay(tableState.players, tableState.dealerSeat)}
            </div>
        </div>`;
    }
    return GameBoard({
        debug: false,
        overlay: buildOverlay(tableState),
        state: tableStateToDisplayState(tableState, { allOpen: true }),
    });
}

function loadedTemplate(
    screen: Extract<ReplayScreen, { kind: "loaded" }>,
    handlers: ReplayHandlers,
): TemplateResult {
    const { currentStep, openDropdown, replay } = screen;
    const step = replay.actionSteps[currentStep];
    const displayState = step ? replay.states[step.stateIndex] : undefined;
    const totalSteps = replay.actionSteps.length;
    const inRound = displayState?.phase === "in_round" || displayState?.phase === "round_ended";
    return html`
        <div class="replay-board-layout__board">
            ${displayState ? buildBoardContent(displayState) : ""}
        </div>
        <div class="replay-controls">
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
            class="replay-board-mode"
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
 * The replay viewer for one mount: it loads the replay through the injected `loadReplay`, then steps through its
 * precomputed timeline from the controls, the arrow keys and the wheel, rendering the whole view into its host.
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
        prev: () => this.stepBy(-1),
        root: createRef<HTMLElement>(),
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
            const parsed = parseReplayLines(fetched.text);
            this.show(parsed.ok ? loadedScreen(parsed) : messageScreen(parsed.refusal));
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
        this.show({ ...screen, currentStep: stepIndex, openDropdown });
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
