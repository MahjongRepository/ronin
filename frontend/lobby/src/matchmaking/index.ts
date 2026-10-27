import { LobbySocket } from "@/lobby-socket";
import {
    handleMessage,
    handleStatusChange,
    joinQueue,
    leaveOnPageHide,
    rejoinOnPageShow,
} from "@/matchmaking/handlers";
import { createMatchmakingState } from "@/matchmaking/state";
import { renderMatchmaking } from "@/matchmaking/ui";
import { bindToPageLifetime } from "@/page-lifetime";

function openMatchmakingPage(container: HTMLElement, wsUrl: string): void {
    const state = createMatchmakingState();
    function render(): void {
        renderMatchmaking(container, state, { onRetry: rejoin });
    }
    function rejoin(): void {
        joinQueue(state, render, wsUrl);
    }

    state.socket = new LobbySocket(
        (message) => handleMessage(state, message, render),
        (status) => handleStatusChange(state, status, render),
    );

    bindToPageLifetime({
        release: () => leaveOnPageHide(state),
        restore: () => rejoinOnPageShow(state, rejoin),
    });

    rejoin();
}

export function initMatchmakingPage(container: HTMLElement): void {
    const { wsUrl } = container.dataset;
    if (wsUrl) {
        openMatchmakingPage(container, wsUrl);
    }
}
