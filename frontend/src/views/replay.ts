import { type TemplateResult, html, render } from "lit-html";

import { LOG_TYPE_UNKNOWN, parseServerMessage } from "@/shared/protocol";

interface LogEntry {
    raw: string;
    type: string;
}

interface ReplayViewState {
    abortController: AbortController | null;
    logs: LogEntry[];
    viewGeneration: number;
}

let state: ReplayViewState = {
    abortController: null,
    logs: [],
    viewGeneration: 0,
};

export function isVersionTag(line: string): boolean {
    try {
        return Boolean(JSON.parse(line).version);
    } catch {
        return false;
    }
}

export function parseReplayLines(text: string): LogEntry[] {
    return text
        .split("\n")
        .filter((line, index) => {
            const trimmed = line.trim();
            return trimmed && !(index === 0 && isVersionTag(trimmed));
        })
        .map((line) => {
            const trimmed = line.trim();
            try {
                const raw = JSON.parse(trimmed) as Record<string, unknown>;
                const [error, parsed] = parseServerMessage(raw);
                if (error) {
                    return {
                        raw: `${trimmed}\n[Parse error: ${error.message}]`,
                        type: LOG_TYPE_UNKNOWN,
                    };
                }
                return {
                    raw: JSON.stringify(parsed, null, 2),
                    type: parsed.type,
                };
            } catch (parseError) {
                const detail =
                    parseError instanceof Error ? parseError.message : String(parseError);
                return {
                    raw: `${trimmed}\n[JSON parse error: ${detail}]`,
                    type: LOG_TYPE_UNKNOWN,
                };
            }
        });
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

async function processResponse(response: Response, generation: number): Promise<void> {
    if (!response.ok) {
        handleResponseError(response);
        return;
    }
    const text = await response.text();
    if (state.viewGeneration !== generation) {
        return;
    }
    state.logs = parseReplayLines(text);
    updateLogPanel();
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
    const container = document.getElementById("log-entries");
    if (!container) {
        return;
    }
    render(
        html`<div class="log-entry log-system"><span class="log-type">${message}</span></div>`,
        container,
    );
}

function updateLogPanel(): void {
    const container = document.getElementById("log-entries");
    if (!container) {
        return;
    }
    render(
        html`
        ${state.logs.map(
            (entry) => html`
            <div class="log-entry log-${entry.type}">
                <span class="log-type">${entry.type}</span>
                <pre class="log-raw">${entry.raw}</pre>
            </div>
        `,
        )}
    `,
        container,
    );
}

export function replayView(gameId: string): TemplateResult {
    const generation = state.viewGeneration + 1;
    state = { abortController: null, logs: [], viewGeneration: generation };

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
            <div class="log-panel" id="log-panel">
                <div class="log-entries" id="log-entries"></div>
            </div>
        </div>
    `;
}

export function cleanupReplayView(): void {
    const { abortController } = state;
    state = {
        ...state,
        abortController: null,
        logs: [],
        viewGeneration: state.viewGeneration + 1,
    };
    if (abortController) {
        abortController.abort();
    }
}
