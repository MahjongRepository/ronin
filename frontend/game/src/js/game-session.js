const GAME_SESSION_KEY_PREFIX = "game_session:";

function isNonEmptyString(value) {
    return typeof value === "string" && value !== "";
}

function isGameSession(value) {
    return (
        typeof value === "object" &&
        value !== null &&
        isNonEmptyString(value.wsUrl) &&
        isNonEmptyString(value.gameTicket)
    );
}

export function readGameSession(gameId) {
    try {
        const raw = sessionStorage.getItem(`${GAME_SESSION_KEY_PREFIX}${gameId}`);
        const parsed = raw === null ? null : JSON.parse(raw);
        return isGameSession(parsed)
            ? { wsUrl: parsed.wsUrl, gameTicket: parsed.gameTicket }
            : null;
    } catch {
        return null;
    }
}
