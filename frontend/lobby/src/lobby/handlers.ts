import { apiGet, apiPost } from "@/api";
import { type LobbyState, parseCreatedRoomId, parseLobbyRooms, roomPath } from "@/lobby/state";

export interface LobbyViewContext {
    readonly isDisposed: () => boolean;
    readonly navigate: (url: string) => void;
    readonly render: () => void;
}

export async function loadRooms(state: LobbyState, context: LobbyViewContext): Promise<void> {
    const result = await apiGet("/api/lobby/rooms");
    if (context.isDisposed()) {
        return;
    }
    const rooms = result.ok ? parseLobbyRooms(result.data) : null;
    if (rooms === null) {
        console.error("lobby rooms not loaded", result.ok ? "invalid answer" : result.error);
        state.loadFailed = true;
    } else {
        state.rooms = rooms;
    }
    context.render();
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
