import { type LobbySocket } from "@/lobby-socket";
import { OCCUPANCY } from "@/occupancy-errors";

const MATCHMAKING_SEATS = 4;

const MATCH_FAILED = "match_failed";
const GAME_START_INVALID = "game_start_invalid";

const SERVER_ENDING_CODES = [
    MATCH_FAILED,
    OCCUPANCY.ALREADY_IN_GAME,
    OCCUPANCY.ALREADY_IN_ROOM,
    OCCUPANCY.MATCH_STARTING,
    OCCUPANCY.REPLACED_BY_NEW_CONNECTION,
] as const;

type ServerEndingCode = (typeof SERVER_ENDING_CODES)[number];
type EndingCode = ServerEndingCode | typeof GAME_START_INVALID;

const RETRYABLE_CODES: ReadonlySet<EndingCode> = new Set([
    GAME_START_INVALID,
    MATCH_FAILED,
    OCCUPANCY.ALREADY_IN_GAME,
    OCCUPANCY.MATCH_STARTING,
]);

type MatchmakingPhase = "connecting" | "searching" | "starting" | "ended" | "disconnected";

interface MatchmakingEnd {
    code: EndingCode;
    seatedRoomId?: string;
}

interface MatchmakingState {
    end: MatchmakingEnd | null;
    phase: MatchmakingPhase;
    queueSize: number;
    socket: Pick<LobbySocket, "connect" | "disconnect"> | null;
}

function createMatchmakingState(): MatchmakingState {
    return { end: null, phase: "connecting", queueSize: 0, socket: null };
}

function isServerEndingCode(code: unknown): code is ServerEndingCode {
    return SERVER_ENDING_CODES.some((ending) => ending === code);
}

function canRetry(state: MatchmakingState): boolean {
    if (state.phase === "disconnected") {
        return true;
    }
    return state.phase === "ended" && state.end !== null && RETRYABLE_CODES.has(state.end.code);
}

function isFinished(state: MatchmakingState): boolean {
    return state.phase === "ended" || state.phase === "starting";
}

export {
    GAME_START_INVALID,
    MATCHMAKING_SEATS,
    MATCH_FAILED,
    canRetry,
    createMatchmakingState,
    isFinished,
    isServerEndingCode,
};
export type { EndingCode, MatchmakingEnd, MatchmakingPhase, MatchmakingState };
