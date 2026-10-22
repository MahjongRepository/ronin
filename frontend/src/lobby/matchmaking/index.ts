import { LobbySocket } from "@/lobby/lobby-socket";
import { describeOccupancyError } from "@/lobby/occupancy-errors";
import { storeGameSession } from "@/shared/session";

const MATCH_FAILED = "match_failed";
const RETRYABLE_ERRORS: ReadonlySet<unknown> = new Set([MATCH_FAILED, "already_in_game"]);
const TERMINAL_ERRORS: ReadonlySet<unknown> = new Set([
    MATCH_FAILED,
    "already_in_game",
    "already_in_queue",
    "already_in_room",
]);

interface MatchmakingElements {
    queueCount: HTMLElement;
    retry: HTMLButtonElement;
    status: HTMLElement;
}

interface MatchmakingPage {
    elements: MatchmakingElements;
    endedWithError: boolean;
}

function getElements(container: HTMLElement): MatchmakingElements | null {
    const status = container.querySelector<HTMLElement>(".matchmaking-status");
    const queueCount = container.querySelector<HTMLElement>(".matchmaking-queue-count");
    const retry = container.querySelector<HTMLButtonElement>(".matchmaking-retry");
    if (!status || !queueCount || !retry) {
        return null;
    }
    return { queueCount, retry, status };
}

function updateQueueDisplay(elements: MatchmakingElements, size: number): void {
    elements.queueCount.textContent = `${size}/4 players in queue`;
}

function onGameStarting(
    message: Record<string, unknown>,
    elements: MatchmakingElements,
    socket: LobbySocket,
): void {
    const gameId = message.game_id as string;
    const wsUrl = message.ws_url as string;
    const gameTicket = message.game_ticket as string;
    const gameClientUrl = (message.game_client_url as string) || "/play";

    if (gameId && wsUrl && gameTicket) {
        storeGameSession(gameId, wsUrl, gameTicket);
    }

    elements.status.textContent = "Match found! Starting game...";
    elements.queueCount.textContent = "";
    socket.disconnect();
    window.location.href = `${gameClientUrl}/${gameId}`;
}

function describeError(message: unknown): string {
    if (message === MATCH_FAILED) {
        return "The match could not be started.";
    }
    return describeOccupancyError(message) ?? `Error: ${String(message)}`;
}

function showError(message: unknown, page: MatchmakingPage): void {
    const { elements } = page;
    page.endedWithError = TERMINAL_ERRORS.has(message);
    elements.status.textContent = describeError(message);
    elements.queueCount.textContent = "";
    elements.retry.hidden = !RETRYABLE_ERRORS.has(message);
}

function handleMessage(
    message: Record<string, unknown>,
    page: MatchmakingPage,
    socket: LobbySocket,
): void {
    if (page.endedWithError) {
        return;
    }
    const { elements } = page;
    switch (message.type) {
        case "queue_joined":
            elements.status.textContent = "Waiting for players...";
            updateQueueDisplay(elements, message.queue_size as number);
            break;
        case "queue_update":
            updateQueueDisplay(elements, message.queue_size as number);
            break;
        case "game_starting":
            onGameStarting(message, elements, socket);
            break;
        case "error":
            showError(message.message, page);
            break;
        case "pong":
            break;
    }
}

function handleStatusChange(
    status: "connected" | "disconnected" | "error",
    page: MatchmakingPage,
): void {
    if (page.endedWithError) {
        return;
    }
    const { elements } = page;
    switch (status) {
        case "connected":
            elements.status.textContent = "Connected, waiting for players...";
            break;
        case "disconnected":
            elements.status.textContent = "Disconnected from server";
            elements.queueCount.textContent = "";
            break;
        case "error":
            elements.status.textContent = "Connection error";
            elements.queueCount.textContent = "";
            break;
    }
}

export function initMatchmakingPage(wsUrl: string): void {
    const container = document.getElementById("matchmaking-app");
    if (!container) {
        return;
    }

    const elements = getElements(container);
    if (!elements) {
        return;
    }

    const page: MatchmakingPage = { elements, endedWithError: false };
    const socket = new LobbySocket(
        (message) => handleMessage(message, page, socket),
        (status) => handleStatusChange(status, page),
    );

    elements.retry.addEventListener("click", () => {
        page.endedWithError = false;
        elements.retry.hidden = true;
        elements.status.textContent = "Connecting...";
        socket.connect(wsUrl);
    });

    socket.connect(wsUrl);
}
