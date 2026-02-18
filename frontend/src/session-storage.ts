const SESSION_KEYS = ["ws_url", "player_name", "room_id", "session_token"] as const;

/** Clear all session storage keys used during room/game lifecycle. */
export function clearSessionData(gameId?: string): void {
    if (gameId) {
        sessionStorage.removeItem(`session_token:${gameId}`);
        sessionStorage.removeItem(`game_session:${gameId}`);
    }
    for (const key of SESSION_KEYS) {
        sessionStorage.removeItem(key);
    }
}

/** Get the session token, generating a new UUID if none exists. */
export function getSessionToken(): string {
    const existing = sessionStorage.getItem("session_token");
    if (existing) {
        return existing;
    }
    const token = crypto.randomUUID();
    sessionStorage.setItem("session_token", token);
    return token;
}

/** Store the session token received from the server. */
export function setSessionToken(token: string): void {
    sessionStorage.setItem("session_token", token);
}

interface GameSessionData {
    wsUrl: string;
    sessionToken: string;
}

function isGameSessionData(data: unknown): data is GameSessionData {
    return (
        typeof data === "object" &&
        data !== null &&
        "wsUrl" in data &&
        typeof (data as Record<string, unknown>).wsUrl === "string" &&
        "sessionToken" in data &&
        typeof (data as Record<string, unknown>).sessionToken === "string"
    );
}

/** Store game session data for reconnection. */
export function storeGameSession(gameId: string, wsUrl: string, sessionToken: string): void {
    sessionStorage.setItem(`game_session:${gameId}`, JSON.stringify({ sessionToken, wsUrl }));
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
