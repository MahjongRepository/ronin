import { type TemplateResult, html, render } from "lit-html";

import { type ReplayEvent, StateDisplay, type TableState, buildTimeline } from "@/entities/table";
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
    currentIndex: number;
    events: ReplayEvent[];
    parseErrors: string[];
    states: TableState[];
    viewGeneration: number;
}

let state: ReplayViewState = {
    abortController: null,
    currentIndex: 0,
    events: [],
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
    state.currentIndex = 0;
    state.events = parsed.events;
    state.parseErrors = parsed.errors;
    state.states = buildTimeline(parsed.events);
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
        const response = await fetch(`/api/replays/${gameId}`, {
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
    if (state.currentIndex > 0) {
        state.currentIndex--;
        updateStateDisplay();
    }
}

function handleNext(): void {
    if (state.currentIndex < state.events.length) {
        state.currentIndex++;
        updateStateDisplay();
    }
}

function updateStateDisplay(): void {
    const container = document.getElementById("replay-state-container");
    if (!container) {
        return;
    }

    const currentState = state.states[state.currentIndex];
    const total = state.events.length;

    render(
        html`
            ${
                state.parseErrors.length > 0
                    ? html`<div class="replay-state__warning">
                    ${state.parseErrors.length} line(s) could not be parsed
                </div>`
                    : ""
            }
            <div class="replay-state__nav">
                <button
                    class="replay-state__nav-btn"
                    @click=${handlePrev}
                    ?disabled=${state.currentIndex === 0}
                >Prev</button>
                <span class="replay-state__counter">
                    Event ${state.currentIndex} / ${total}
                </span>
                <button
                    class="replay-state__nav-btn"
                    @click=${handleNext}
                    ?disabled=${state.currentIndex >= total}
                >Next</button>
            </div>
            <div class="replay-state__description">
                ${currentState?.lastEventDescription ?? ""}
            </div>
            ${currentState ? StateDisplay(currentState) : ""}
        `,
        container,
    );
}

function createEmptyState(generation: number): ReplayViewState {
    return {
        abortController: null,
        currentIndex: 0,
        events: [],
        parseErrors: [],
        states: [],
        viewGeneration: generation,
    };
}

export function replayView(gameId: string): TemplateResult {
    const generation = state.viewGeneration + 1;
    state = createEmptyState(generation);

    setTimeout(() => {
        if (state.viewGeneration !== generation) {
            return;
        }
        renderSystemMessage("Loading replay...");
        fetchReplay(gameId, generation);
    }, 0);

    return html`
        <div class="game">
            <div class="game-header">
                <a href="/history" class="secondary" role="button">Back to History</a>
                <h2>Game: ${gameId}</h2>
                <span class="connection-status status-replay">Replay</span>
            </div>
            <div class="replay-state" id="replay-state-container"></div>
        </div>
    `;
}

export function cleanupReplayView(): void {
    const { abortController } = state;
    state = createEmptyState(state.viewGeneration + 1);
    abortController?.abort();
}
