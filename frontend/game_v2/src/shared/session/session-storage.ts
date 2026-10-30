/** The lobby's handoff for one game: the socket to join and the ticket that names the seat. */
export interface GameSessionData {
    readonly wsUrl: string;
    readonly gameTicket: string;
}

function handoffKey(gameId: string): string {
    return `game_session:${gameId}`;
}

function isGameSessionData(data: unknown): data is GameSessionData {
    return (
        typeof data === "object" &&
        data !== null &&
        "wsUrl" in data &&
        typeof data.wsUrl === "string" &&
        "gameTicket" in data &&
        typeof data.gameTicket === "string"
    );
}

/** Keep a game's handoff for a reload, under the key the lobby writes it to. */
export function storeGameSession(gameId: string, wsUrl: string, gameTicket: string): void {
    sessionStorage.setItem(handoffKey(gameId), JSON.stringify({ gameTicket, wsUrl }));
}

/** The game's handoff this tab holds, or null when it holds none or one it cannot read. */
export function getGameSession(gameId: string): GameSessionData | null {
    const raw = sessionStorage.getItem(handoffKey(gameId));
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

/** Forget the game's handoff, which its ticket will never seat again. */
export function clearGameSession(gameId: string): void {
    sessionStorage.removeItem(handoffKey(gameId));
}
