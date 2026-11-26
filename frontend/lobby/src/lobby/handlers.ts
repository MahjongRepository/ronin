import { type ApiResult, apiGet, apiPost } from "@/api";
import {
    type LobbyRooms,
    type LobbyState,
    parseCreatedRoomId,
    parseGamesWsUrl,
    parseLobbyRooms,
    roomPath,
} from "@/lobby/state";

export interface LobbyViewContext {
    readonly isDisposed: () => boolean;
    readonly navigate: (url: string) => void;
    readonly render: () => void;
}

interface RoomsAnswer {
    readonly gamesWsUrl: string;
    readonly rooms: LobbyRooms;
}

function readRoomsAnswer(result: ApiResult): RoomsAnswer | null {
    const rooms = result.ok ? parseLobbyRooms(result.data) : null;
    const gamesWsUrl = result.ok ? parseGamesWsUrl(result.data) : null;
    if (rooms === null || gamesWsUrl === null) {
        console.error("lobby rooms not loaded", result.ok ? "invalid answer" : result.error);
        return null;
    }
    return { gamesWsUrl, rooms };
}

export async function loadRooms(
    state: LobbyState,
    context: LobbyViewContext,
): Promise<string | null> {
    const result = await apiGet("/api/lobby/rooms");
    if (context.isDisposed()) {
        return null;
    }
    const answer = readRoomsAnswer(result);
    if (answer === null) {
        state.loadFailed = true;
    } else {
        state.rooms = answer.rooms;
    }
    context.render();
    return answer?.gamesWsUrl ?? null;
}

async function postNewRoom(): Promise<string | null> {
    const result = await apiPost("/api/lobby/rooms", {});
    const roomId = result.ok ? parseCreatedRoomId(result.data) : null;
    if (roomId === null) {
        console.error("room not created", result.ok ? "invalid answer" : result.error);
    }
    return roomId;
}

function enterCreatedRoom(
    state: LobbyState,
    context: LobbyViewContext,
    roomId: string | null,
): void {
    state.creating = false;
    if (roomId === null) {
        state.createFailed = true;
        context.render();
        return;
    }
    context.navigate(roomPath(roomId));
}

export async function createRoom(state: LobbyState, context: LobbyViewContext): Promise<void> {
    if (state.creating) {
        return;
    }
    state.creating = true;
    state.createFailed = false;
    const roomId = await postNewRoom();
    if (!context.isDisposed()) {
        enterCreatedRoom(state, context, roomId);
    }
}
