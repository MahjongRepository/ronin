import { type MountedView } from "@ronin/shared/router";
import { render } from "lit-html";

import { pageFailedView } from "@/app/page-failed";
import { t } from "@/i18n";
import { LobbySocket } from "@/lobby-socket";
import {
    fetchMatchmakingWsUrl,
    handleMessage,
    handleStatusChange,
    joinQueue,
    leaveOnPageExit,
    rejoinOnPageShow,
} from "@/matchmaking/handlers";
import { createMatchmakingState } from "@/matchmaking/state";
import { renderMatchmaking } from "@/matchmaking/ui";
import { bindToPageLifetime } from "@/page-lifetime";

function showFailure(host: HTMLElement): MountedView {
    function draw(): void {
        document.title = t("page.title.with_page", { page: t("lobby.action.quick_match") });
        render(pageFailedView(), host);
    }
    draw();
    return { rerender: draw, unmount: () => {} };
}

function showConnecting(host: HTMLElement): MountedView {
    const state = createMatchmakingState();
    function draw(): void {
        renderMatchmaking(host, state, { onRetry: () => {} });
    }
    draw();
    return { rerender: draw, unmount: () => {} };
}

function openQueue(host: HTMLElement, wsUrl: string): MountedView {
    const state = createMatchmakingState();
    function draw(): void {
        renderMatchmaking(host, state, { onRetry: rejoin });
    }
    function rejoin(): void {
        joinQueue(state, draw, wsUrl);
    }

    state.socket = new LobbySocket(
        (message) => handleMessage(state, message, draw),
        (status) => handleStatusChange(state, status, draw),
    );

    const unbindLifetime = bindToPageLifetime({
        release: () => leaveOnPageExit(state),
        restore: () => rejoinOnPageShow(state, rejoin),
    });

    rejoin();
    return {
        rerender: draw,
        unmount: () => {
            leaveOnPageExit(state);
            unbindLifetime();
        },
    };
}

export function mountMatchmakingView(host: HTMLElement): MountedView {
    let disposed = false;
    let shown = showConnecting(host);

    async function load(): Promise<void> {
        const wsUrl = await fetchMatchmakingWsUrl();
        if (disposed) {
            return;
        }
        shown = wsUrl === null ? showFailure(host) : openQueue(host, wsUrl);
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
