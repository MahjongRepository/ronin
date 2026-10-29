import { t } from "@/i18n";
import { bindLanguageSwitchInPlace } from "@/language-switch";
import { LobbySocket } from "@/lobby-socket";
import { bindToPageLifetime } from "@/page-lifetime";
import {
    buildActionCallbacks,
    buildMessageHandlers,
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

function bindLanguageSwitch(roomName: string | undefined, render: () => void): void {
    bindLanguageSwitchInPlace(() => {
        document.title = t("page.title.with_page", { page: roomName || t("room.fallback_name") });
        render();
    });
}

function renderSetupFailure(container: HTMLElement): void {
    const state = createRoomState();
    state.pageError = { code: PAGE_ERROR.PAGE_SETUP_FAILED };
    function render(): void {
        renderRoom({
            actions: buildActionCallbacks(state),
            chatMaxLength: 0,
            container,
            roomName: container.dataset.roomName || t("room.fallback_name"),
            state,
        });
    }
    bindLanguageSwitch(container.dataset.roomName, render);
    render();
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
    bindLanguageSwitch(config.roomName, render);

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
