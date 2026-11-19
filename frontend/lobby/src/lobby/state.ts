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

export interface OwnTournament {
    readonly id: string;
    readonly name: string;
}

export interface OwnTournaments {
    readonly nameMaxLength: number;
    readonly tournaments: readonly OwnTournament[];
}

export interface LobbyState {
    creating: boolean;
    createFailed: boolean;
    creatingTournament: boolean;
    games: CurrentGame[] | null;
    loadFailed: boolean;
    readonly notice: MessageKey | null;
    ownTournaments: OwnTournaments | null;
    rooms: LobbyRooms | null;
    tournamentCreateFailed: boolean;
}

const LOBBY_NOTICES: ReadonlyMap<string, MessageKey> = new Map([
    ["table_gone", "lobby.notice.table_gone"],
]);

export function createLobbyState(notice: MessageKey | null): LobbyState {
    return {
        createFailed: false,
        creating: false,
        creatingTournament: false,
        games: null,
        loadFailed: false,
        notice,
        ownTournaments: null,
        rooms: null,
        tournamentCreateFailed: false,
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

function parseOwnTournament(value: unknown): OwnTournament | null {
    if (!isRecord(value) || typeof value.id !== "string" || typeof value.name !== "string") {
        return null;
    }
    return { id: value.id, name: value.name };
}

export function parseOwnTournaments(data: unknown): OwnTournaments | null {
    if (!isRecord(data) || !Array.isArray(data.tournaments)) {
        return null;
    }
    const nameMaxLength = data.name_max_length;
    const tournaments = data.tournaments.map(parseOwnTournament);
    if (!isCount(nameMaxLength) || nameMaxLength === 0 || tournaments.includes(null)) {
        return null;
    }
    return { nameMaxLength, tournaments: tournaments.filter((entry) => entry !== null) };
}

export function parseCreatedTournamentId(data: unknown): string | null {
    return isRecord(data) && typeof data.tournament_id === "string" && data.tournament_id !== ""
        ? data.tournament_id
        : null;
}

export function tournamentPath(tournamentId: string): string {
    return `/tournaments/${encodeURIComponent(tournamentId)}`;
}

export function roomPath(roomId: string): string {
    return `/rooms/${encodeURIComponent(roomId)}`;
}
