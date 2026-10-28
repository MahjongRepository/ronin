import { t } from "@/i18n";
import { LobbySocket } from "@/lobby-socket";
import { bindToPageLifetime } from "@/page-lifetime";
import {
    buildActionCallbacks,
    buildMessageHandlers,
    describeRoomError,
    handleMessage,
    handleStatusChange,
    joinRoom,
    leaveOnPageHide,
    rejoinOnPageShow,
} from "@/room/handlers";
import { PAGE_ERROR, createRoomState } from "@/room/state";
import { type RoomPage, renderRoom } from "@/room/ui";

interface RoomConfig {
    chatMaxLength: number;
    roomName: string;
    wsUrl: string;
}

function readRoomConfig(container: HTMLElement): RoomConfig | null {
    const { chatMaxLength, roomName, wsUrl } = container.dataset;
    const maxLength = Number(chatMaxLength);
    if (!roomName || !wsUrl || !Number.isInteger(maxLength) || maxLength <= 0) {
        return null;
    }
    return { chatMaxLength: maxLength, roomName, wsUrl };
}

function renderSetupFailure(container: HTMLElement): void {
    const state = createRoomState();
    const code = PAGE_ERROR.PAGE_SETUP_FAILED;
    state.pageError = { code, text: describeRoomError(code) };
    renderRoom({
        actions: buildActionCallbacks(state),
        chatMaxLength: 0,
        container,
        roomName: container.dataset.roomName || t("room.fallback_name"),
        state,
    });
}

function openRoomPage(container: HTMLElement, config: RoomConfig): void {
    const state = createRoomState();
    const page: RoomPage = {
        actions: buildActionCallbacks(state),
        chatMaxLength: config.chatMaxLength,
        container,
        roomName: config.roomName,
        state,
    };
    function render(): void {
        renderRoom(page);
    }
    function rejoin(): void {
        joinRoom(state, render, config.wsUrl);
    }
    const handlers = buildMessageHandlers(state, render, rejoin);

    state.socket = new LobbySocket(
        (message) => handleMessage(handlers, message),
        (status) => handleStatusChange(state, status, render),
    );

    bindToPageLifetime({
        release: () => leaveOnPageHide(state),
        restore: () => rejoinOnPageShow(state, rejoin),
    });

    rejoin();
}

export function initRoomPage(container: HTMLElement): void {
    const config = readRoomConfig(container);
    if (!config) {
        renderSetupFailure(container);
        return;
    }
    openRoomPage(container, config);
}
