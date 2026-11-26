/**
 * The lobby's handoff for one game (the socket to join, the ticket that names the seat and the seat version the
 * lobby read) and this tab's claim on the seat, sent unchanged on every join and reconnect of the handoff.
 */
export interface GameSessionData {
    readonly wsUrl: string;
    readonly gameTicket: string;
    readonly seatVersion: number;
    readonly claimId: string;
}

const HANDOFF_KEY_PREFIX = "game_session:";
const CLAIM_ID_BYTES = 16;

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
        typeof data.gameTicket === "string" &&
        "seatVersion" in data &&
        Number.isInteger(data.seatVersion) &&
        Number(data.seatVersion) >= 0 &&
        "claimId" in data &&
        typeof data.claimId === "string" &&
        data.claimId !== ""
    );
}

function newClaimId(): string {
    const bytes = crypto.getRandomValues(new Uint8Array(CLAIM_ID_BYTES));
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/**
 * Claim the seat a lobby handoff names: a new claim id with the seat version the lobby read. Each handoff the lobby
 * gives is a new claim, which takes the seat over from any older one, so only a deliberate entry makes one.
 */
export function claimGameSession(
    wsUrl: string,
    gameTicket: string,
    seatVersion: number,
): GameSessionData {
    return { claimId: newClaimId(), gameTicket, seatVersion, wsUrl };
}

/** Keep a game's handoff for a reload, under the key the lobby writes it to. */
export function storeGameSession(gameId: string, session: GameSessionData): void {
    sessionStorage.setItem(handoffKey(gameId), JSON.stringify(session));
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
