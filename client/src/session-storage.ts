const SESSION_KEYS = ["ws_url", "player_name", "room_id", "session_token"] as const;

/** Clear all session storage keys used during room/game lifecycle. */
export function clearSessionData(gameId?: string): void {
    if (gameId) {
        sessionStorage.removeItem(`session_token:${gameId}`);
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
