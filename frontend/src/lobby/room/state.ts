import { type LobbySocket } from "@/lobby/lobby-socket";

interface PlayerInfo {
    name: string;
    ready: boolean;
    is_bot: boolean;
    is_owner: boolean;
}

interface ChatEntry {
    sender: string;
    text: string;
    timestamp: string;
}

type ConnectionStatus = "connected" | "disconnected" | "error";

const LOG_TYPE_SYSTEM = "system";

interface RoomState {
    players: PlayerInfo[];
    chatMessages: ChatEntry[];
    connectionStatus: ConnectionStatus;
    isOwner: boolean;
    canStart: boolean;
    currentPlayerName: string;
    socket: LobbySocket | null;
}

function createRoomState(): RoomState {
    return {
        canStart: false,
        chatMessages: [],
        connectionStatus: "disconnected",
        currentPlayerName: "",
        isOwner: false,
        players: [],
        socket: null,
    };
}

function getMyReadyState(state: RoomState): boolean {
    const me = state.players.find(
        (player) => player.name === state.currentPlayerName && !player.is_bot,
    );
    return me?.ready ?? false;
}

export { LOG_TYPE_SYSTEM, createRoomState, getMyReadyState };
export type { ChatEntry, ConnectionStatus, PlayerInfo, RoomState };
