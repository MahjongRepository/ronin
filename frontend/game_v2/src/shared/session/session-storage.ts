const SESSION_KEYS = ["ws_url", "game_ticket", "room_id"] as const;

/** Clear all session storage keys used during room/game lifecycle. */
export function clearSessionData(gameId?: string): void {
    if (gameId) {
        sessionStorage.removeItem(`game_session:${gameId}`);
    }
    for (const key of SESSION_KEYS) {
        sessionStorage.removeItem(key);
    }
}

/** Retrieve the game ticket from sessionStorage. */
export function getGameTicket(): string | null {
    return sessionStorage.getItem("game_ticket");
}

/** Store the game ticket received from the lobby. */
export function setGameTicket(ticket: string): void {
    sessionStorage.setItem("game_ticket", ticket);
}

interface GameSessionData {
    wsUrl: string;
    gameTicket: string;
}

function isGameSessionData(data: unknown): data is GameSessionData {
    return (
        typeof data === "object" &&
        data !== null &&
        "wsUrl" in data &&
        typeof (data as Record<string, unknown>).wsUrl === "string" &&
        "gameTicket" in data &&
        typeof (data as Record<string, unknown>).gameTicket === "string"
    );
}

/** Store game session data for reconnection. */
export function storeGameSession(gameId: string, wsUrl: string, gameTicket: string): void {
    sessionStorage.setItem(`game_session:${gameId}`, JSON.stringify({ gameTicket, wsUrl }));
}

/** Retrieve stored game session data for reconnection. */
export function getGameSession(gameId: string): GameSessionData | null {
    const raw = sessionStorage.getItem(`game_session:${gameId}`);
    if (!raw) {
        return null;
    }
    try {
        const parsed: unknown = JSON.parse(raw);
        return isGameSessionData(parsed) ? parsed : null;
    } catch {
        return null;
    }
}

/** Clear stored game session data. */
export function clearGameSession(gameId: string): void {
    sessionStorage.removeItem(`game_session:${gameId}`);
}
