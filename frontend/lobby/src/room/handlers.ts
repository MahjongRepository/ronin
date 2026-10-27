import { type SocketStatus, readString } from "@/lobby-socket";
import { OCCUPANCY, type OccupancyText, describeOccupancyError } from "@/occupancy-errors";
import {
    LOG_TYPE_SYSTEM,
    PAGE_ERROR,
    type PlayerInfo,
    type RoomState,
    canAct,
    getMyReadyState,
    isMe,
    resetSeat,
} from "@/room/state";
import { enterGame, readGameStart } from "@/session";

type RenderRoom = () => void;

interface ActionCallbacks {
    handleLeaveRoom: () => void;
    handleSendChat: (text: string) => boolean;
    handleStartGame: () => void;
    handleToggleReady: () => void;
}

type MessageHandlerMap = Record<string, (msg: Record<string, unknown>) => void>;

const JOIN_RETRY_DELAY_MS = 2000;
const MAX_JOIN_RETRIES = 30;
const ROOM_TRANSITIONING = "room_transitioning";
const RETRYABLE_JOIN_ERRORS: ReadonlySet<unknown> = new Set([
    OCCUPANCY.MATCH_STARTING,
    ROOM_TRANSITIONING,
]);

const ROOM_OCCUPANCY_TEXT: OccupancyText = {
    [OCCUPANCY.ALREADY_IN_ROOM]:
        "You are already seated at another table. Leave it before joining this one.",
    [OCCUPANCY.REPLACED_BY_NEW_CONNECTION]:
        "This table is open in another tab or window and continues there. You can close this one.",
};

const ROOM_ERROR_TEXT: Readonly<Record<string, string>> = {
    game_server_error: "The game server could not create the game. Try starting again.",
    game_server_full: "The game server is full. Try again in a few minutes.",
    game_server_unavailable: "The game server could not be reached. Try starting again.",
    [PAGE_ERROR.GAME_START_INVALID]:
        "The game started, but it could not be opened. Reload the page to join it.",
    internal_error: "Something went wrong starting the game. Try again.",
    [PAGE_ERROR.JOIN_RETRIES_EXHAUSTED]:
        "The game did not start in time. Reload the page to try again.",
    [PAGE_ERROR.PAGE_SETUP_FAILED]: "This table could not be loaded. Reload the page to try again.",
    player_in_game: "A player at this table is already in a game.",
    room_full: "This table filled up before you joined.",
    room_not_found: "This table no longer exists.",
    [ROOM_TRANSITIONING]: "The game is starting.",
};

function describeRoomError(code: unknown): string {
    if (typeof code === "string" && Object.hasOwn(ROOM_ERROR_TEXT, code)) {
        return ROOM_ERROR_TEXT[code];
    }
    return describeOccupancyError(code, ROOM_OCCUPANCY_TEXT) ?? `Error: ${String(code)}`;
}

function updateFromServerState(
    state: RoomState,
    message: Record<string, unknown>,
    render: RenderRoom,
): void {
    state.players = (message.players as PlayerInfo[]) ?? state.players;
    state.canStart = (message.can_start as boolean) ?? false;
    // Derive isOwner from the authoritative player list as a fallback,
    // so ownership is corrected even if the owner_changed message was missed.
    const self = state.players.find((player) => isMe(state, player));
    if (self) {
        state.isOwner = self.is_owner;
    }
    render();
}

function readSeatedRoomId(message: Record<string, unknown>): string | undefined {
    if (message.message !== OCCUPANCY.ALREADY_IN_ROOM) {
        return undefined;
    }
    return readString(message, "room_id") ?? undefined;
}

function cancelJoinRetry(state: RoomState): void {
    if (state.joinRetryTimer !== null) {
        clearTimeout(state.joinRetryTimer);
        state.joinRetryTimer = null;
    }
}

function joinRoom(state: RoomState, render: RenderRoom, wsUrl: string): void {
    state.connectionStatus = "connecting";
    render();
    state.socket?.connect(wsUrl);
}

function handleStatusChange(state: RoomState, status: SocketStatus, render: RenderRoom): void {
    state.connectionStatus = status;
    render();
}

function buildMessageHandlers(
    state: RoomState,
    render: RenderRoom,
    rejoin: () => void,
): MessageHandlerMap {
    function appendChat(sender: string, text: string): void {
        state.chatMessages.push({
            sender,
            text,
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        });
        render();
    }

    function endPage(code: string, seatedRoomId?: string): void {
        cancelJoinRetry(state);
        state.pageError = { code, seatedRoomId, text: describeRoomError(code) };
        render();
    }

    function onRoomJoined(message: Record<string, unknown>): void {
        state.currentPlayerName = (message.player_name as string) ?? "";
        state.isOwner = (message.is_owner as boolean) ?? false;
        updateFromServerState(state, message, render);
        appendChat(LOG_TYPE_SYSTEM, "You joined the table");
    }

    function onPlayerJoined(message: Record<string, unknown>): void {
        updateFromServerState(state, message, render);
        if (message.player_name) {
            appendChat(LOG_TYPE_SYSTEM, `${message.player_name} joined`);
        }
    }

    function onPlayerLeft(message: Record<string, unknown>): void {
        updateFromServerState(state, message, render);
        if (message.player_name) {
            appendChat(LOG_TYPE_SYSTEM, `${message.player_name} left`);
        }
    }

    function onOwnerChanged(message: Record<string, unknown>): void {
        state.isOwner = (message.is_owner as boolean) ?? false;
        updateFromServerState(state, message, render);
        appendChat(LOG_TYPE_SYSTEM, "You are now the host");
    }

    function scheduleRejoin(code: unknown): void {
        if (state.joinRetries >= MAX_JOIN_RETRIES) {
            endPage(PAGE_ERROR.JOIN_RETRIES_EXHAUSTED);
            return;
        }
        if (state.joinRetries === 0) {
            appendChat(LOG_TYPE_SYSTEM, describeRoomError(code));
        }
        state.joinRetries += 1;
        cancelJoinRetry(state);
        state.joinRetryTimer = setTimeout(() => {
            state.joinRetryTimer = null;
            rejoin();
        }, JOIN_RETRY_DELAY_MS);
    }

    function onError(message: Record<string, unknown>): void {
        const code = message.message;
        const joined = state.currentPlayerName !== "";
        if (!joined && RETRYABLE_JOIN_ERRORS.has(code)) {
            scheduleRejoin(code);
            return;
        }
        if (!joined || code === OCCUPANCY.REPLACED_BY_NEW_CONNECTION) {
            endPage(String(code), readSeatedRoomId(message));
            return;
        }
        appendChat(LOG_TYPE_SYSTEM, describeRoomError(code));
    }

    function onGameStarting(message: Record<string, unknown>): void {
        state.socket?.disconnect();
        const start = readGameStart(message);
        if (!start) {
            endPage(PAGE_ERROR.GAME_START_INVALID);
            return;
        }
        cancelJoinRetry(state);
        appendChat(LOG_TYPE_SYSTEM, "Game starting!");
        enterGame(start);
    }

    return {
        chat: (msg) => appendChat(msg.player_name as string, msg.text as string),
        error: onError,
        game_starting: onGameStarting,
        owner_changed: onOwnerChanged,
        player_joined: onPlayerJoined,
        player_left: onPlayerLeft,
        player_ready_changed: (msg) => updateFromServerState(state, msg, render),
        room_joined: onRoomJoined,
    };
}

function handleMessage(handlers: MessageHandlerMap, message: Record<string, unknown>): void {
    const handler = handlers[message.type as string];
    if (handler) {
        handler(message);
    }
}

function leaveOnPageHide(state: RoomState): void {
    cancelJoinRetry(state);
    state.socket?.disconnect();
}

function rejoinOnPageShow(state: RoomState, rejoin: () => void): void {
    if (state.pageError) {
        return;
    }
    cancelJoinRetry(state);
    resetSeat(state);
    rejoin();
}

function buildActionCallbacks(state: RoomState): ActionCallbacks {
    return {
        handleLeaveRoom() {
            state.socket?.send({ type: "leave_room" });
            state.socket?.disconnect();
            window.location.replace("/");
        },
        handleSendChat(text) {
            const trimmed = text.trim();
            if (!trimmed || !state.socket || !canAct(state)) {
                return false;
            }
            return state.socket.send({ text: trimmed, type: "chat" });
        },
        handleStartGame() {
            if (!state.socket || !canAct(state) || !state.canStart) {
                return;
            }
            state.socket.send({ type: "start_game" });
        },
        handleToggleReady() {
            if (!state.socket || !canAct(state)) {
                return;
            }
            state.socket.send({ ready: !getMyReadyState(state), type: "set_ready" });
        },
    };
}

export {
    JOIN_RETRY_DELAY_MS,
    MAX_JOIN_RETRIES,
    buildActionCallbacks,
    buildMessageHandlers,
    describeRoomError,
    handleMessage,
    handleStatusChange,
    joinRoom,
    leaveOnPageHide,
    rejoinOnPageShow,
};
export type { ActionCallbacks, MessageHandlerMap, RenderRoom };
