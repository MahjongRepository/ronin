import { type TemplateResult, html, render } from "lit-html";
import { LOG_TYPE_UNKNOWN } from "@/protocol";

interface LogEntry {
    raw: string;
    type: string;
}

let logs: LogEntry[] = [];
let viewGeneration = 0;
let abortController: AbortController | null = null;

function isVersionTag(line: string): boolean {
    try {
        return Boolean(JSON.parse(line).version);
    } catch {
        return false;
    }
}

function extractEventType(line: string): string {
    try {
        const parsed = JSON.parse(line);
        return parsed.t !== undefined ? String(parsed.t) : LOG_TYPE_UNKNOWN;
    } catch {
        return LOG_TYPE_UNKNOWN;
    }
}

function parseReplayLines(text: string): LogEntry[] {
    return text
        .split("\n")
        .filter((line, index) => {
            const trimmed = line.trim();
            return trimmed && !(index === 0 && isVersionTag(trimmed));
        })
        .map((line) => {
            const trimmed = line.trim();
            return { raw: trimmed, type: extractEventType(trimmed) };
        });
}

function isAbortError(error: unknown): boolean {
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
    if (viewGeneration !== generation) {
        return;
    }
    logs = parseReplayLines(text);
    updateLogPanel();
}

async function fetchReplay(gameId: string, generation: number): Promise<void> {
    abortController = new AbortController();
    try {
        const response = await fetch(`/api/replays/${gameId}`, {
            signal: abortController.signal,
        });
        if (viewGeneration !== generation) {
            return;
        }
        await processResponse(response, generation);
    } catch (error: unknown) {
        if (isAbortError(error) || viewGeneration !== generation) {
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
        ${logs.map(
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
    logs = [];
    const generation = ++viewGeneration;

    setTimeout(() => {
        if (viewGeneration !== generation) {
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
    viewGeneration++;
    if (abortController) {
        abortController.abort();
        abortController = null;
    }
    logs = [];
}
