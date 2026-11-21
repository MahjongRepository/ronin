/** The lobby's handoff for one game: the socket to join and the ticket that names the seat. */
export interface GameSessionData {
    readonly wsUrl: string;
    readonly gameTicket: string;
}

const HANDOFF_KEY_PREFIX = "game_session:";

function handoffKey(gameId: string): string {
    return `${HANDOFF_KEY_PREFIX}${gameId}`;
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

/**
 * Forget every game handoff this tab holds, so a ticket never outlives the account it was signed for: on logout and
 * before any sign-in, which may be another account's. The signed-in player's own handoff comes back by recovery.
 * Storage the browser refuses holds no handoff to forget, so it never stops a logout or a sign-in.
 */
export function clearAllGameSessions(): void {
    try {
        for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
            const key = sessionStorage.key(index);
            if (key?.startsWith(HANDOFF_KEY_PREFIX)) {
                sessionStorage.removeItem(key);
            }
        }
    } catch (error: unknown) {
        console.warn("Game handoffs could not be cleared from unavailable session storage:", error);
    }
}
