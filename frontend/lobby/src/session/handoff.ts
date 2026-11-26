import { claimGameSession, storeGameSession } from "@ronin/shared/session-storage";

import { readString } from "@/lobby-socket";

const DEFAULT_GAME_CLIENT_URL = "/play";

interface GameStart {
    gameClientUrl: string;
    gameId: string;
    gameTicket: string | null;
    seatVersion: number;
    wsUrl: string | null;
}

function readSeatVersion(message: Record<string, unknown>): number | null {
    const version = message.seat_version;
    return Number.isInteger(version) && Number(version) >= 0 ? Number(version) : null;
}

export function readGameStart(message: Record<string, unknown>): GameStart | null {
    const gameId = readString(message, "game_id");
    const seatVersion = readSeatVersion(message);
    if (!gameId || seatVersion === null) {
        return null;
    }
    return {
        gameClientUrl: readString(message, "game_client_url") ?? DEFAULT_GAME_CLIENT_URL,
        gameId,
        gameTicket: readString(message, "game_ticket"),
        seatVersion,
        wsUrl: readString(message, "ws_url"),
    };
}

/** Store the session the game client joins with and leave for the game, so Back skips this page. */
export function enterGame({
    gameClientUrl,
    gameId,
    gameTicket,
    seatVersion,
    wsUrl,
}: GameStart): void {
    if (wsUrl && gameTicket) {
        storeGameSession(gameId, claimGameSession(wsUrl, gameTicket, seatVersion));
    }
    window.location.replace(`${gameClientUrl}/${encodeURIComponent(gameId)}`);
}

export type { GameStart };
