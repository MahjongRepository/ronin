import { apiGet, apiPost } from "@/api";
import { fetchSession } from "@/app/session";
import {
    type LobbyState,
    type OwnTournaments,
    parseCreatedRoomId,
    parseCreatedTournamentId,
    parseLobbyRooms,
    parseOwnTournaments,
    roomPath,
    tournamentPath,
} from "@/lobby/state";

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

export async function loadOwnTournaments(
    state: LobbyState,
    context: LobbyViewContext,
): Promise<void> {
    const session = await fetchSession();
    if (context.isDisposed() || session?.user?.isAdmin !== true) {
        return;
    }
    const tournaments = await fetchOwnTournaments();
    if (tournaments !== null && !context.isDisposed()) {
        state.ownTournaments = tournaments;
        context.render();
    }
}

async function fetchOwnTournaments(): Promise<OwnTournaments | null> {
    const result = await apiGet("/api/lobby/tournaments");
    const tournaments = result.ok ? parseOwnTournaments(result.data) : null;
    if (tournaments === null) {
        console.error("own tournaments not loaded", result.ok ? "invalid answer" : result.error);
    }
    return tournaments;
}

async function postNewTournament(name: string): Promise<string | null> {
    const result = await apiPost("/api/lobby/tournaments", { name });
    const tournamentId = result.ok ? parseCreatedTournamentId(result.data) : null;
    if (tournamentId === null) {
        console.error("tournament not created", result.ok ? "invalid answer" : result.error);
    }
    return tournamentId;
}

export async function createTournament(
    state: LobbyState,
    context: LobbyViewContext,
    name: string,
): Promise<void> {
    if (state.creatingTournament) {
        return;
    }
    state.creatingTournament = true;
    state.tournamentCreateFailed = false;
    context.render();
    const tournamentId = await postNewTournament(name);
    if (!context.isDisposed()) {
        enterCreatedTournament(state, context, tournamentId);
    }
}

function enterCreatedTournament(
    state: LobbyState,
    context: LobbyViewContext,
    tournamentId: string | null,
): void {
    state.creatingTournament = false;
    if (tournamentId === null) {
        state.tournamentCreateFailed = true;
        context.render();
        return;
    }
    context.navigate(tournamentPath(tournamentId));
}
