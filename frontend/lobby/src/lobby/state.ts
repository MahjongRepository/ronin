import { type CurrentGame } from "@/current-games";
import { type MessageKey } from "@/i18n";

export interface LobbyPlayer {
    readonly isBot: boolean;
    readonly name: string;
}

export interface LobbyRoom {
    readonly name: string;
    readonly numAiPlayers: number;
    readonly playerCount: number;
    readonly players: readonly LobbyPlayer[];
    readonly roomId: string;
}

export interface LobbyRooms {
    readonly myRoomId: string | null;
    readonly rooms: readonly LobbyRoom[];
}

export interface LobbyState {
    creating: boolean;
    createFailed: boolean;
    games: CurrentGame[] | null;
    loadFailed: boolean;
    readonly notice: MessageKey | null;
    rooms: LobbyRooms | null;
}

const LOBBY_NOTICES: ReadonlyMap<string, MessageKey> = new Map([
    ["table_gone", "lobby.notice.table_gone"],
]);

export function createLobbyState(notice: MessageKey | null): LobbyState {
    return {
        createFailed: false,
        creating: false,
        games: null,
        loadFailed: false,
        notice,
        rooms: null,
    };
}

export function noticeFromUrl(url: URL): MessageKey | null {
    return LOBBY_NOTICES.get(url.searchParams.get("notice") ?? "") ?? null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

function isCount(value: unknown): value is number {
    return Number.isInteger(value) && Number(value) >= 0;
}

function parsePlayer(value: unknown): LobbyPlayer | null {
    if (!isRecord(value) || typeof value.name !== "string" || typeof value.is_bot !== "boolean") {
        return null;
    }
    return { isBot: value.is_bot, name: value.name };
}

function parseRoom(value: unknown): LobbyRoom | null {
    if (!isRecord(value) || !Array.isArray(value.players)) {
        return null;
    }
    const {
        name,
        num_ai_players: numAiPlayers,
        player_count: playerCount,
        room_id: roomId,
    } = value;
    const players = value.players.map(parsePlayer);
    if (
        typeof roomId !== "string" ||
        typeof name !== "string" ||
        !isCount(playerCount) ||
        !isCount(numAiPlayers) ||
        players.includes(null)
    ) {
        return null;
    }
    return { name, numAiPlayers, playerCount, players: players.filter((p) => p !== null), roomId };
}

export function parseLobbyRooms(data: unknown): LobbyRooms | null {
    if (!isRecord(data) || !Array.isArray(data.rooms)) {
        return null;
    }
    const myRoomId = data.my_room;
    const rooms = data.rooms.map(parseRoom);
    if ((myRoomId !== null && typeof myRoomId !== "string") || rooms.includes(null)) {
        return null;
    }
    return { myRoomId, rooms: rooms.filter((room) => room !== null) };
}

export function parseGamesWsUrl(data: unknown): string | null {
    return isRecord(data) && typeof data.games_ws_url === "string" && data.games_ws_url !== ""
        ? data.games_ws_url
        : null;
}

export function parseCreatedRoomId(data: unknown): string | null {
    return isRecord(data) && typeof data.room_id === "string" && data.room_id !== ""
        ? data.room_id
        : null;
}

export interface SeatedTable {
    readonly name: string | null;
    readonly roomId: string;
}

export function seatedTable(rooms: LobbyRooms): SeatedTable | null {
    if (rooms.myRoomId === null) {
        return null;
    }
    const listed = rooms.rooms.find((room) => room.roomId === rooms.myRoomId);
    return { name: listed?.name ?? null, roomId: rooms.myRoomId };
}

export function roomPath(roomId: string): string {
    return `/rooms/${encodeURIComponent(roomId)}`;
}
