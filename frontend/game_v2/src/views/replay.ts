import { type TemplateResult, html, render } from "lit-html";

import {
    type ActionStep,
    GameBoard,
    GameEndDisplay,
    type GamePhase,
    GameStartDisplay,
    type NavigationIndex,
    type ReplayEvent,
    RoundEndDisplay,
    RoundSelector,
    type TableState,
    TurnSelector,
    buildActionSteps,
    buildNavigationIndex,
    buildTimeline,
    formatRoundName,
    roundForStep,
    tableStateToDisplayState,
    turnsForStep,
} from "@/entities/table";
import { type ParsedServerMessage, parseServerMessage } from "@/shared/protocol";

const REPLAY_EVENT_TYPES: Record<ReplayEvent["type"], true> = {
    discard: true,
    dora_revealed: true,
    draw: true,
    game_end: true,
    game_started: true,
    meld: true,
    riichi_declared: true,
    round_end: true,
    round_started: true,
};

export function isReplayEvent(msg: ParsedServerMessage): msg is ReplayEvent {
    return msg.type in REPLAY_EVENT_TYPES;
}

interface ParsedReplay {
    errors: string[];
    events: ReplayEvent[];
}

interface ReplayViewState {
    abortController: AbortController | null;
    actionSteps: ActionStep[];
    currentStep: number;
    events: ReplayEvent[];
    navigationIndex: NavigationIndex | null;
    openDropdown: "round" | "turn" | null;
    parseErrors: string[];
    states: TableState[];
    viewGeneration: number;
}

let state: ReplayViewState = {
    abortController: null,
    actionSteps: [],
    currentStep: 0,
    events: [],
    navigationIndex: null,
    openDropdown: null,
    parseErrors: [],
    states: [],
    viewGeneration: 0,
};

export function isVersionTag(line: string): boolean {
    try {
        return Boolean(JSON.parse(line).version);
    } catch {
        return false;
    }
}

function classifyParsedMessage(parsed: ParsedServerMessage, result: ParsedReplay): void {
    if (isReplayEvent(parsed)) {
        result.events.push(parsed);
    } else {
        result.errors.push(`Non-replay event type: ${parsed.type}`);
    }
}

function parseLine(trimmed: string, result: ParsedReplay): void {
    try {
        const raw = JSON.parse(trimmed) as Record<string, unknown>;
        const [error, parsed] = parseServerMessage(raw);
        if (error) {
            result.errors.push(`Parse error: ${error.message}`);
        } else {
            classifyParsedMessage(parsed, result);
        }
    } catch (parseError) {
        const detail = parseError instanceof Error ? parseError.message : String(parseError);
        result.errors.push(`JSON parse error: ${detail}`);
    }
}

export function parseReplayLines(text: string): ParsedReplay {
    const result: ParsedReplay = { errors: [], events: [] };

    const lines = text.split("\n").filter((line, index) => {
        const trimmed = line.trim();
        return trimmed && !(index === 0 && isVersionTag(trimmed));
    });

    for (const line of lines) {
        parseLine(line.trim(), result);
    }

    return result;
}

export function isAbortError(error: unknown): boolean {
    return error instanceof DOMException && error.name === "AbortError";
}

function handleResponseError(response: Response): void {
    if (response.status === 404) {
        renderSystemMessage("Replay not found");
    } else {
        renderSystemMessage(`Failed to load replay (${response.status})`);
    }
}

function applyParsedReplay(parsed: ParsedReplay): void {
    state.currentStep = 0;
    state.events = parsed.events;
    state.parseErrors = parsed.errors;
    state.states = buildTimeline(parsed.events);
    state.actionSteps = buildActionSteps(parsed.events);
    state.navigationIndex = buildNavigationIndex(parsed.events, state.actionSteps, state.states);
}

async function processResponse(response: Response, generation: number): Promise<void> {
    if (!response.ok) {
        handleResponseError(response);
        return;
    }
    const text = await response.text();
    if (state.viewGeneration !== generation) {
        return;
    }
    applyParsedReplay(parseReplayLines(text));
    updateStateDisplay();
}

async function fetchReplay(gameId: string, generation: number): Promise<void> {
    state.abortController = new AbortController();
    try {
        const response = await fetch(`/api/replays/${encodeURIComponent(gameId)}`, {
            signal: state.abortController.signal,
        });
        if (state.viewGeneration !== generation) {
            return;
        }
        await processResponse(response, generation);
    } catch (error: unknown) {
        if (isAbortError(error) || state.viewGeneration !== generation) {
            return;
        }
        renderSystemMessage("Failed to load replay");
    }
}

function renderSystemMessage(message: string): void {
    const container = document.getElementById("replay-state-container");
    if (!container) {
        return;
    }
    render(html`<div class="replay-state__message">${message}</div>`, container);
}

function handlePrev(): void {
    if (state.currentStep > 0) {
        state.currentStep--;
        updateStateDisplay();
    }
}

function handleNext(): void {
    if (state.currentStep < state.actionSteps.length - 1) {
        state.currentStep++;
        updateStateDisplay();
    }
}

function handleJumpToStep(stepIndex: number): void {
    if (stepIndex < 0 || stepIndex >= state.actionSteps.length) {
        return;
    }
    state.currentStep = stepIndex;
    state.openDropdown = null;
    updateStateDisplay();
}

function handleToggleDropdown(which: "round" | "turn"): void {
    state.openDropdown = state.openDropdown === which ? null : which;
    updateStateDisplay();
}

export function handleClickOutside(event: MouseEvent): void {
    if (state.openDropdown === null) {
        return;
    }
    const target = event.target as Element | null;
    if (target?.closest(".dropdown-select")) {
        return;
    }
    state.openDropdown = null;
    updateStateDisplay();
}

let wheelNavElement: HTMLElement | null = null;

const IGNORED_KEY_TARGETS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function handleKeydown(event: KeyboardEvent): void {
    const target = event.target as Element | null;
    if (target && IGNORED_KEY_TARGETS.has(target.tagName)) {
        return;
    }
    if (event.key === "ArrowLeft") {
        event.preventDefault();
        handlePrev();
    } else if (event.key === "ArrowRight") {
        event.preventDefault();
        handleNext();
    }
}

export function handleWheel(event: WheelEvent): void {
    const target = event.target as Element | null;
    if (target?.closest(".dropdown-select__panel")) {
        return;
    }
    if (event.deltaY > 0) {
        event.preventDefault();
        handleNext();
    } else if (event.deltaY < 0) {
        event.preventDefault();
        handlePrev();
    }
}

interface StepCounterParams {
    currentStep: number;
    navIndex: NavigationIndex | null;
    phase: GamePhase;
    totalSteps: number;
}

function stepPrefix(
    navIndex: NavigationIndex | null,
    currentStep: number,
    phase: GamePhase,
): string {
    if (!navIndex) {
        return "";
    }
    if (phase === "game_ended") {
        return "Game ended";
    }
    const round = roundForStep(navIndex, currentStep);
    if (!round) {
        return "";
    }
    return formatRoundName(round.wind, round.roundNumber, round.honba);
}

/**
 * Formats the step counter with game context.
 * Shows round info (wind, number, honba) when inside a round,
 * "Game ended" after the game ends, or just the step when pre-game.
 */
export function formatStepCounter(params: StepCounterParams): string {
    const { currentStep, navIndex, phase, totalSteps } = params;
    const stepLabel = `Step ${currentStep + 1} / ${totalSteps}`;
    const prefix = stepPrefix(navIndex, currentStep, phase);
    return prefix ? `${prefix} \u2014 ${stepLabel}` : stepLabel;
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

function updateStateDisplay(): void {
    const container = document.getElementById("replay-state-container");
    if (!container) {
        return;
    }

    const step = state.actionSteps[state.currentStep];
    const displayState = step ? state.states[step.stateIndex] : undefined;
    const totalSteps = state.actionSteps.length;

    render(
        html`
            <div class="replay-board-layout__board">
                ${displayState ? buildBoardContent(displayState) : ""}
            </div>
            <div class="replay-controls">
                ${
                    state.parseErrors.length > 0
                        ? html`<div class="replay-state__warning">
                        ${state.parseErrors.length} line(s) could not be parsed
                    </div>`
                        : ""
                }
                <div class="replay-controls__nav">
                    <button
                        class="replay-state__nav-btn"
                        @click=${handlePrev}
                        ?disabled=${state.currentStep === 0}
                    >&lt;</button>
                    ${
                        state.navigationIndex
                            ? RoundSelector({
                                  currentRound: roundForStep(
                                      state.navigationIndex,
                                      state.currentStep,
                                  ),
                                  isOpen: state.openDropdown === "round",
                                  onSelect: handleJumpToStep,
                                  onToggle: () => handleToggleDropdown("round"),
                                  rounds: state.navigationIndex.rounds,
                              })
                            : html`
                                  <button class="dropdown-select__trigger" disabled>Rounds</button>
                              `
                    }
                    ${
                        state.navigationIndex &&
                        (displayState?.phase === "in_round" ||
                            displayState?.phase === "round_ended")
                            ? TurnSelector({
                                  currentStep: state.currentStep,
                                  isOpen: state.openDropdown === "turn",
                                  onSelect: handleJumpToStep,
                                  onToggle: () => handleToggleDropdown("turn"),
                                  turns: turnsForStep(state.navigationIndex, state.currentStep),
                              })
                            : html`
                                  <button class="dropdown-select__trigger" disabled>Turns</button>
                              `
                    }
                    <button
                        class="replay-state__nav-btn"
                        @click=${handleNext}
                        ?disabled=${state.currentStep >= totalSteps - 1}
                    >&gt;</button>
                </div>
            </div>
        `,
        container,
    );

    attachWheelListener(container);
}

function attachWheelListener(container: HTMLElement): void {
    if (wheelNavElement) {
        return;
    }
    container.addEventListener("wheel", handleWheel, { passive: false });
    wheelNavElement = container;
}

function createEmptyState(generation: number): ReplayViewState {
    return {
        abortController: null,
        actionSteps: [],
        currentStep: 0,
        events: [],
        navigationIndex: null,
        openDropdown: null,
        parseErrors: [],
        states: [],
        viewGeneration: generation,
    };
}

export function replayView(gameId: string): TemplateResult {
    const generation = state.viewGeneration + 1;
    state = createEmptyState(generation);
    wheelNavElement = null;

    setTimeout(() => {
        if (state.viewGeneration !== generation) {
            return;
        }
        renderSystemMessage("Loading replay...");
        fetchReplay(gameId, generation);
    }, 0);

    document.addEventListener("keydown", handleKeydown);
    document.addEventListener("click", handleClickOutside);

    return html`
        <div class="replay-board-mode" id="replay-state-container"></div>
    `;
}

export function cleanupReplayView(): void {
    document.removeEventListener("keydown", handleKeydown);
    document.removeEventListener("click", handleClickOutside);
    if (wheelNavElement) {
        wheelNavElement.removeEventListener("wheel", handleWheel);
        wheelNavElement = null;
    }
    const { abortController } = state;
    state = createEmptyState(state.viewGeneration + 1);
    abortController?.abort();
}
