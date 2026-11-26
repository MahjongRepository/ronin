import { type ApiResult, apiGet, apiPost, isRecord } from "@/api";
import {
    type LobbyRooms,
    type LobbyState,
    parseCreatedRoomId,
    parseGamesWsUrl,
    parseLobbyRooms,
    roomPath,
} from "@/lobby/state";
import { type GameStart, enterGame, readGameStart } from "@/session";

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

const NOT_PLAYING = "not_playing";

type LiveGameLookup =
    | { readonly kind: "playing"; readonly game: GameStart }
    | { readonly kind: "none" }
    | { readonly kind: "failed" };

async function lookUpLiveGame(): Promise<LiveGameLookup> {
    const result = await apiGet("/api/game-session");
    if (!result.ok) {
        return result.error === NOT_PLAYING ? { kind: "none" } : { kind: "failed" };
    }
    const game = isRecord(result.data) ? readGameStart(result.data) : null;
    if (game === null) {
        console.error("game session not read", "invalid answer");
        return { kind: "failed" };
    }
    return { game, kind: "playing" };
}

/** Find whether the user plays a game, of any kind, so the lobby offers the way back into it. */
export async function checkLiveGame(state: LobbyState, context: LobbyViewContext): Promise<void> {
    const lookup = await lookUpLiveGame();
    if (context.isDisposed()) {
        return;
    }
    state.playing = lookup.kind === "playing";
    context.render();
}

function finishReturn(state: LobbyState, lookup: LiveGameLookup, context: LobbyViewContext): void {
    if (lookup.kind === "playing") {
        enterGame(lookup.game);
        return;
    }
    state.returning = false;
    state.playing = lookup.kind !== "none";
    state.returnFailed = lookup.kind === "failed";
    context.render();
}

/**
 * Enter the user's live game with a fresh handoff, taking the seat over from any tab that holds it; a game that
 * ended meanwhile turns the lobby back, and a lookup that failed can be retried.
 */
export async function returnToGame(state: LobbyState, context: LobbyViewContext): Promise<void> {
    if (state.returning) {
        return;
    }
    state.returning = true;
    state.returnFailed = false;
    context.render();
    const lookup = await lookUpLiveGame();
    if (!context.isDisposed()) {
        finishReturn(state, lookup, context);
    }
}
