import {
    LOG_TYPE_SYSTEM,
    type PlayerInfo,
    type RoomState,
    getMyReadyState,
} from "@/lobby/room/state";
import { storeGameSession } from "@/session-storage";

interface UpdateUICallbacks {
    updateActionButton: () => void;
    updateChatPanel: () => void;
    updatePlayerList: () => void;
    updateStatusDisplay: () => void;
}

interface ActionCallbacks {
    handleLeaveRoom: () => void;
    handleSendChat: () => void;
    handleStartGame: () => void;
    handleToggleReady: () => void;
}

type MessageHandlerMap = Record<string, (msg: Record<string, unknown>) => void>;

function updateFromServerState(
    state: RoomState,
    message: Record<string, unknown>,
    updateUI: UpdateUICallbacks,
): void {
    state.players = (message.players as PlayerInfo[]) ?? state.players;
    state.canStart = (message.can_start as boolean) ?? false;
    // Derive isOwner from the authoritative player list as a fallback,
    // so ownership is corrected even if the owner_changed message was missed.
    const self = state.players.find(
        (player) => player.name === state.currentPlayerName && !player.is_bot,
    );
    if (self) {
        state.isOwner = self.is_owner;
    }
    updateUI.updatePlayerList();
    updateUI.updateActionButton();
}

function disconnectSocket(state: RoomState): void {
    if (state.socket) {
        state.socket.disconnect();
        state.socket = null;
    }
}

function buildMessageHandlers(state: RoomState, updateUI: UpdateUICallbacks): MessageHandlerMap {
    function appendChat(sender: string, text: string): void {
        state.chatMessages.push({
            sender,
            text,
            timestamp: new Date().toLocaleTimeString(),
        });
        updateUI.updateChatPanel();
    }

    function onRoomJoined(message: Record<string, unknown>): void {
        state.currentPlayerName = (message.player_name as string) ?? "";
        state.isOwner = (message.is_owner as boolean) ?? false;
        updateFromServerState(state, message, updateUI);
        appendChat(LOG_TYPE_SYSTEM, "Joined room");
    }

    function onPlayerJoined(message: Record<string, unknown>): void {
        updateFromServerState(state, message, updateUI);
        if (message.player_name) {
            appendChat(LOG_TYPE_SYSTEM, `${message.player_name} joined`);
        }
    }

    function onPlayerLeft(message: Record<string, unknown>): void {
        updateFromServerState(state, message, updateUI);
        if (message.player_name) {
            appendChat(LOG_TYPE_SYSTEM, `${message.player_name} left`);
        }
    }

    function onOwnerChanged(message: Record<string, unknown>): void {
        state.isOwner = (message.is_owner as boolean) ?? false;
        updateFromServerState(state, message, updateUI);
        appendChat(LOG_TYPE_SYSTEM, "You are now the host");
    }

    function onGameStarting(message: Record<string, unknown>): void {
        const gameId = message.game_id as string;
        const wsUrl = message.ws_url as string;
        const gameTicket = message.game_ticket as string;
        const gameClientUrl = (message.game_client_url as string) || "/play";

        if (gameId && wsUrl && gameTicket) {
            storeGameSession(gameId, wsUrl, gameTicket);
        }

        appendChat(LOG_TYPE_SYSTEM, "Game starting!");
        disconnectSocket(state);
        window.location.href = `${gameClientUrl}/${gameId}`;
    }

    return {
        chat: (msg) => appendChat(msg.player_name as string, msg.text as string),
        error: (msg) => appendChat(LOG_TYPE_SYSTEM, `Error: ${msg.message}`),
        game_starting: onGameStarting,
        owner_changed: onOwnerChanged,
        player_joined: onPlayerJoined,
        player_left: onPlayerLeft,
        player_ready_changed: (msg) => updateFromServerState(state, msg, updateUI),
        pong: () => {},
        room_joined: onRoomJoined,
    };
}

function handleMessage(handlers: MessageHandlerMap, message: Record<string, unknown>): void {
    const handler = handlers[message.type as string];
    if (handler) {
        handler(message);
    }
}

function buildActionCallbacks(state: RoomState): ActionCallbacks {
    return {
        handleLeaveRoom() {
            if (state.socket) {
                state.socket.send({ type: "leave_room" });
            }
            disconnectSocket(state);
            window.location.href = "/";
        },
        handleSendChat() {
            const input = document.getElementById("chat-input") as HTMLInputElement | null;
            if (!input || !state.socket) {
                return;
            }
            const text = input.value.trim();
            if (!text) {
                return;
            }
            state.socket.send({ text, type: "chat" });
            input.value = "";
        },
        handleStartGame() {
            if (!state.socket || !state.canStart) {
                return;
            }
            state.socket.send({ type: "start_game" });
        },
        handleToggleReady() {
            if (!state.socket) {
                return;
            }
            state.socket.send({ ready: !getMyReadyState(state), type: "set_ready" });
        },
    };
}

export { buildActionCallbacks, buildMessageHandlers, handleMessage };
export type { ActionCallbacks, MessageHandlerMap, UpdateUICallbacks };
