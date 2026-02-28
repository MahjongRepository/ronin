import { buildActionCallbacks, buildMessageHandlers, handleMessage } from "@/lobby/room/handlers";
import {
    renderRoomUI,
    updateActionButton,
    updateChatPanel,
    updatePlayerList,
    updateStatusDisplay,
} from "@/lobby/room/ui";
import { LobbySocket } from "@/lobby/lobby-socket";
import { createRoomState } from "@/lobby/room/state";

interface RoomConfig {
    roomId: string;
    wsUrl: string;
}

export function initRoomPage(config: RoomConfig): void {
    const container = document.getElementById("room-app");
    if (!container) {
        return;
    }

    const state = createRoomState();
    const actions = buildActionCallbacks(state);
    const updateUI = {
        updateActionButton: () => updateActionButton(state, actions),
        updateChatPanel: () => updateChatPanel(state),
        updatePlayerList: () => updatePlayerList(state),
        updateStatusDisplay: () => updateStatusDisplay(state),
    };
    const handlers = buildMessageHandlers(state, updateUI);

    renderRoomUI(container, config.roomId, actions);

    state.socket = new LobbySocket(
        (message) => handleMessage(handlers, message),
        (status) => {
            state.connectionStatus = status;
            updateStatusDisplay(state);
        },
    );

    state.socket.connect(config.wsUrl);
}
