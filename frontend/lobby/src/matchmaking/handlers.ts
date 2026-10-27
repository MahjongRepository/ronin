import { type SocketStatus, readString } from "@/lobby-socket";
import {
    GAME_START_INVALID,
    type MatchmakingEnd,
    type MatchmakingState,
    isFinished,
    isServerEndingCode,
} from "@/matchmaking/state";
import { OCCUPANCY } from "@/occupancy-errors";
import { enterGame, readGameStart } from "@/session";

type RenderMatchmaking = () => void;

function readQueueSize(message: Record<string, unknown>): number {
    const value = message.queue_size;
    return typeof value === "number" ? value : 0;
}

function endSearch(state: MatchmakingState, end: MatchmakingEnd, render: RenderMatchmaking): void {
    state.phase = "ended";
    state.end = end;
    render();
}

function onGameStarting(
    state: MatchmakingState,
    message: Record<string, unknown>,
    render: RenderMatchmaking,
): void {
    state.socket?.disconnect();
    const start = readGameStart(message);
    if (!start) {
        endSearch(state, { code: GAME_START_INVALID }, render);
        return;
    }
    state.phase = "starting";
    render();
    enterGame(start);
}

function onError(
    state: MatchmakingState,
    message: Record<string, unknown>,
    render: RenderMatchmaking,
): void {
    const code = message.message;
    if (!isServerEndingCode(code)) {
        return;
    }
    const seatedRoomId =
        code === OCCUPANCY.ALREADY_IN_ROOM
            ? (readString(message, "room_id") ?? undefined)
            : undefined;
    endSearch(state, { code, seatedRoomId }, render);
}

function handleMessage(
    state: MatchmakingState,
    message: Record<string, unknown>,
    render: RenderMatchmaking,
): void {
    if (isFinished(state)) {
        return;
    }
    switch (message.type) {
        case "queue_joined":
        case "queue_update":
            state.phase = "searching";
            state.queueSize = readQueueSize(message);
            render();
            break;
        case "game_starting":
            onGameStarting(state, message, render);
            break;
        case "error":
            onError(state, message, render);
            break;
    }
}

function handleStatusChange(
    state: MatchmakingState,
    status: SocketStatus,
    render: RenderMatchmaking,
): void {
    if (isFinished(state) || status === "connected") {
        return;
    }
    state.phase = "disconnected";
    state.queueSize = 0;
    render();
}

function joinQueue(state: MatchmakingState, render: RenderMatchmaking, wsUrl: string): void {
    state.phase = "connecting";
    state.end = null;
    state.queueSize = 0;
    render();
    state.socket?.connect(wsUrl);
}

function leaveOnPageHide(state: MatchmakingState): void {
    state.socket?.disconnect();
}

function rejoinOnPageShow(state: MatchmakingState, rejoin: () => void): void {
    if (state.phase === "ended") {
        return;
    }
    rejoin();
}

export { handleMessage, handleStatusChange, joinQueue, leaveOnPageHide, rejoinOnPageShow };
export type { RenderMatchmaking };
