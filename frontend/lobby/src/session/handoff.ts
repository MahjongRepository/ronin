import { readString } from "@/lobby-socket";
import { storeGameSession } from "@/session/session-storage";

const DEFAULT_GAME_CLIENT_URL = "/play";

interface GameStart {
    gameClientUrl: string;
    gameId: string;
    gameTicket: string | null;
    wsUrl: string | null;
}

export function readGameStart(message: Record<string, unknown>): GameStart | null {
    const gameId = readString(message, "game_id");
    if (!gameId) {
        return null;
    }
    return {
        gameClientUrl: readString(message, "game_client_url") ?? DEFAULT_GAME_CLIENT_URL,
        gameId,
        gameTicket: readString(message, "game_ticket"),
        wsUrl: readString(message, "ws_url"),
    };
}

/** Store the session the game client joins with and leave for the game, so Back skips this page. */
export function enterGame({ gameClientUrl, gameId, gameTicket, wsUrl }: GameStart): void {
    if (wsUrl && gameTicket) {
        storeGameSession(gameId, wsUrl, gameTicket);
    }
    window.location.replace(`${gameClientUrl}/${encodeURIComponent(gameId)}`);
}

export type { GameStart };
