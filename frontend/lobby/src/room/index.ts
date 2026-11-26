import { type MountedView } from "@ronin/shared/router";

import { t } from "@/i18n";
import { LobbySocket } from "@/lobby-socket";
import { bindToPageLifetime, bindToResume } from "@/page-lifetime";
import {
    type Navigate,
    RESUME_RECONNECT_AFTER_HIDDEN_MS,
    buildActionCallbacks,
    buildMessageHandlers,
    buildStatusHandler,
    fetchRoomConfig,
    handleMessage,
    joinRoom,
    leaveOnPageExit,
    reconnectOnResume,
    rejoinOnPageShow,
} from "@/room/handlers";
import {
    PAGE_ERROR,
    type PageError,
    type RoomConfig,
    type RoomConfigAnswer,
    createRoomState,
} from "@/room/state";
import { renderRoom } from "@/room/ui";

export interface RoomViewDeps {
    readonly navigate: Navigate;
}

const TABLE_GONE_URL = "/?notice=table_gone";

function showRoomFrame(
    host: HTMLElement,
    navigate: Navigate,
    pageError: PageError | null,
): MountedView {
    const state = createRoomState();
    state.pageError = pageError;
    function draw(): void {
        renderRoom({
            actions: buildActionCallbacks(state, draw, navigate),
            chatMaxLength: 0,
            container: host,
            roomName: t("room.fallback_name"),
            state,
        });
    }
    draw();
    return { rerender: draw, unmount: () => {} };
}

function leaveGoneRoom(gameUrl: string | null, navigate: Navigate): MountedView {
    if (gameUrl === null) {
        navigate(TABLE_GONE_URL, { replace: true });
    } else {
        window.location.replace(gameUrl);
    }
    return { rerender: () => {}, unmount: () => {} };
}

function openRoom(host: HTMLElement, config: RoomConfig, navigate: Navigate): MountedView {
    const state = createRoomState();
    const page = {
        actions: buildActionCallbacks(state, draw, navigate),
        chatMaxLength: config.chatMaxLength,
        container: host,
        roomName: config.roomName,
        state,
    };
    function draw(): void {
        renderRoom(page);
    }
    function rejoin(): void {
        joinRoom(state, draw, config.wsUrl);
    }
    const handlers = buildMessageHandlers(state, draw, rejoin);

    state.socket = new LobbySocket(
        (message) => handleMessage(handlers, message),
        buildStatusHandler(state, draw, rejoin),
    );

    const unbindLifetime = bindToPageLifetime({
        release: () => leaveOnPageExit(state),
        restore: () => rejoinOnPageShow(state, rejoin),
    });
    const unbindResume = bindToResume(
        () => reconnectOnResume(state, rejoin),
        RESUME_RECONNECT_AFTER_HIDDEN_MS,
    );

    rejoin();
    return {
        rerender: draw,
        unmount: () => {
            leaveOnPageExit(state);
            unbindLifetime();
            unbindResume();
        },
    };
}

function showAnswer(host: HTMLElement, answer: RoomConfigAnswer, navigate: Navigate): MountedView {
    switch (answer.kind) {
        case "open": {
            return openRoom(host, answer.config, navigate);
        }
        case "gone": {
            return leaveGoneRoom(answer.gameUrl, navigate);
        }
        case "failed": {
            return showRoomFrame(host, navigate, { code: PAGE_ERROR.PAGE_SETUP_FAILED });
        }
    }
}

export function mountRoomView(host: HTMLElement, roomId: string, deps: RoomViewDeps): MountedView {
    let disposed = false;
    let shown = showRoomFrame(host, deps.navigate, null);

    async function load(): Promise<void> {
        const answer = await fetchRoomConfig(roomId);
        if (!disposed) {
            shown = showAnswer(host, answer, deps.navigate);
        }
    }

    void load();
    return {
        rerender: () => shown.rerender(),
        unmount: () => {
            disposed = true;
            shown.unmount();
        },
    };
}
