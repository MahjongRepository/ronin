import { LobbySocket } from "@/lobby/lobby-socket";
import { storeGameSession } from "@/session-storage";

interface MatchmakingElements {
    queueCount: HTMLElement;
    status: HTMLElement;
}

function getElements(container: HTMLElement): MatchmakingElements | null {
    const status = container.querySelector<HTMLElement>(".matchmaking-status");
    const queueCount = container.querySelector<HTMLElement>(".matchmaking-queue-count");
    if (!status || !queueCount) {
        return null;
    }
    return { queueCount, status };
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

function handleMessage(
    message: Record<string, unknown>,
    elements: MatchmakingElements,
    socket: LobbySocket,
): void {
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
            elements.status.textContent = `Error: ${message.message}`;
            elements.queueCount.textContent = "";
            break;
        case "pong":
            break;
    }
}

function handleStatusChange(
    status: "connected" | "disconnected" | "error",
    elements: MatchmakingElements,
): void {
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

    const socket = new LobbySocket(
        (message) => handleMessage(message, elements, socket),
        (status) => handleStatusChange(status, elements),
    );

    socket.connect(wsUrl);
}
