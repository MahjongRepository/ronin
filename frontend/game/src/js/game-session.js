const GAME_SESSION_KEY_PREFIX = "game_session:";
const RECOVERY_URL = "/api/game-session";
const DEFAULT_GAME_CLIENT_URL = "/play";
const HTTP_UNAUTHORIZED = 401;
const HTTP_NOT_FOUND = 404;

export const RECOVERY = Object.freeze({
    FOUND: "found",
    MISSING: "missing",
    FAILED: "failed",
});

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

function isHandoff(value) {
    return (
        typeof value === "object" &&
        value !== null &&
        isNonEmptyString(value.game_id) &&
        isNonEmptyString(value.ws_url) &&
        isNonEmptyString(value.game_ticket)
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

function storeGameSession(gameId, session) {
    try {
        sessionStorage.setItem(`${GAME_SESSION_KEY_PREFIX}${gameId}`, JSON.stringify(session));
    } catch (error) {
        console.warn("[ronin] the recovered game session holds for this page only:", error);
    }
}

async function fetchHandoff() {
    const response = await fetch(RECOVERY_URL, {
        cache: "no-store",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
    });
    if (response.status === HTTP_NOT_FOUND || response.status === HTTP_UNAUTHORIZED) {
        return { status: RECOVERY.MISSING };
    }
    if (!response.ok) {
        return { status: RECOVERY.FAILED };
    }
    const handoff = await response.json();
    return isHandoff(handoff) ? { status: RECOVERY.FOUND, handoff } : { status: RECOVERY.FAILED };
}

/**
 * Ask the lobby for the handoff of the game the logged-in player is playing, when this tab has none (it was lost
 * before the game page opened, or the page opened in a new tab), and store it as the lobby would have.
 */
export async function recoverGameSession() {
    let result;
    try {
        result = await fetchHandoff();
    } catch {
        return { status: RECOVERY.FAILED };
    }
    if (result.status !== RECOVERY.FOUND) {
        return result;
    }
    const { handoff } = result;
    const session = { wsUrl: handoff.ws_url, gameTicket: handoff.game_ticket };
    storeGameSession(handoff.game_id, session);
    const gameClientUrl = handoff.game_client_url || DEFAULT_GAME_CLIENT_URL;
    return {
        status: RECOVERY.FOUND,
        gameId: handoff.game_id,
        gameUrl: `${gameClientUrl}/${encodeURIComponent(handoff.game_id)}`,
        session,
    };
}
