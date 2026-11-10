import { LobbySocket } from "@/lobby-socket";
import { bindToPageLifetime, bindToResume } from "@/page-lifetime";
import {
    RESUME_RECONNECT_AFTER_HIDDEN_MS,
    buildMessageHandlers,
    buildStatusHandler,
    handleMessage,
    joinTournament,
    leaveOnPageExit,
    reconnectOnResume,
    rejoinOnPageShow,
    sendChat,
} from "@/tournament/handlers";
import { PAGE_ERROR, createTournamentState } from "@/tournament/state";
import { renderTournament } from "@/tournament/ui";

interface TournamentConfig {
    chatMaxLength: number;
    wsUrl: string;
}

function readTournamentConfig(container: HTMLElement): TournamentConfig | null {
    const { chatMaxLength, wsUrl } = container.dataset;
    const maxLength = Number(chatMaxLength);
    if (!wsUrl || !Number.isInteger(maxLength) || maxLength <= 0) {
        return null;
    }
    return { chatMaxLength: maxLength, wsUrl };
}

function renderSetupFailure(container: HTMLElement): void {
    const state = createTournamentState();
    state.pageError = PAGE_ERROR.PAGE_SETUP_FAILED;
    renderTournament({ chatMaxLength: 0, container, sendChat: () => false, state });
}

function openTournamentPage(container: HTMLElement, config: TournamentConfig): void {
    const state = createTournamentState();
    function render(): void {
        renderTournament({
            chatMaxLength: config.chatMaxLength,
            container,
            sendChat: (text) => sendChat(state, text),
            state,
        });
    }
    function rejoin(): void {
        joinTournament(state, render, config.wsUrl);
    }
    const handlers = buildMessageHandlers(state, render);

    state.socket = new LobbySocket(
        (message) => handleMessage(handlers, message),
        buildStatusHandler(state, render, rejoin),
    );

    bindToPageLifetime({
        release: () => leaveOnPageExit(state),
        restore: () => rejoinOnPageShow(state, rejoin),
    });
    bindToResume(() => reconnectOnResume(state, rejoin), RESUME_RECONNECT_AFTER_HIDDEN_MS);

    rejoin();
}

export function initTournamentPage(container: HTMLElement): void {
    const config = readTournamentConfig(container);
    if (!config) {
        renderSetupFailure(container);
        return;
    }
    openTournamentPage(container, config);
}
