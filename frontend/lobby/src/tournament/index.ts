import { type MountedView } from "@ronin/shared/router";

import { redrawElapsedTimes } from "@/current-games";
import { LobbySocket } from "@/lobby-socket";
import { bindToPageLifetime, bindToResume } from "@/page-lifetime";
import {
    type Navigate,
    type OwnerContext,
    RESUME_RECONNECT_AFTER_HIDDEN_MS,
    buildMessageHandlers,
    buildStatusHandler,
    deleteTournament,
    fetchTournamentConfig,
    handleMessage,
    joinTournament,
    leaveOnPageExit,
    reconnectOnResume,
    rejoinOnPageShow,
    renameTournament,
    sendChat,
} from "@/tournament/handlers";
import {
    PAGE_ERROR,
    TOURNAMENT_NOT_FOUND,
    type TournamentConfig,
    type TournamentConfigAnswer,
    type TournamentState,
    createTournamentState,
} from "@/tournament/state";
import { type TournamentActions, renderTournament } from "@/tournament/ui";

export interface TournamentViewDeps {
    readonly navigate: Navigate;
}

interface TournamentMount {
    readonly host: HTMLElement;
    readonly navigate: Navigate;
    readonly tournamentId: string;
}

const NO_ACTIONS: TournamentActions = {
    deleteTournament: () => {},
    renameTournament: () => {},
    selectTab: () => {},
    sendChat: () => false,
};

function showTournamentFrame(mount: TournamentMount, pageError: string | null): MountedView {
    const state = createTournamentState();
    state.pageError = pageError;
    function draw(): void {
        renderTournament({
            actions: NO_ACTIONS,
            config: null,
            container: mount.host,
            state,
            tournamentId: mount.tournamentId,
        });
    }
    draw();
    return { rerender: draw, unmount: () => {} };
}

function buildActions(state: TournamentState, owner: OwnerContext): TournamentActions {
    return {
        deleteTournament: () => void deleteTournament(state, owner),
        renameTournament: (name) => void renameTournament(state, owner, name),
        selectTab: (tab) => {
            state.tab = tab;
            owner.render();
        },
        sendChat: (text) => sendChat(state, text),
    };
}

function attachSocket(state: TournamentState, draw: () => void, rejoin: () => void): () => void {
    const handlers = buildMessageHandlers(state, draw);
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
    return () => {
        leaveOnPageExit(state);
        unbindLifetime();
        unbindResume();
    };
}

function openTournament(mount: TournamentMount, config: TournamentConfig): MountedView {
    const state = createTournamentState();
    state.name = config.name;
    let disposed = false;
    const { navigate, tournamentId } = mount;
    const actions = buildActions(state, {
        isDisposed: () => disposed,
        navigate,
        render: draw,
        tournamentId,
    });
    function draw(): void {
        renderTournament({ actions, config, container: mount.host, state, tournamentId });
    }
    function rejoin(): void {
        joinTournament(state, draw, config.wsUrl);
    }
    const stops = [attachSocket(state, draw, rejoin), redrawElapsedTimes(draw)];
    rejoin();
    return {
        rerender: draw,
        unmount: () => {
            disposed = true;
            for (const stop of stops) {
                stop();
            }
        },
    };
}

function showAnswer(mount: TournamentMount, answer: TournamentConfigAnswer): MountedView {
    switch (answer.kind) {
        case "open": {
            return openTournament(mount, answer.config);
        }
        case "gone": {
            return showTournamentFrame(mount, TOURNAMENT_NOT_FOUND);
        }
        case "failed": {
            return showTournamentFrame(mount, PAGE_ERROR.PAGE_SETUP_FAILED);
        }
    }
}

export function mountTournamentView(
    host: HTMLElement,
    tournamentId: string,
    deps: TournamentViewDeps,
): MountedView {
    const mount = { host, navigate: deps.navigate, tournamentId };
    let disposed = false;
    let shown = showTournamentFrame(mount, null);

    async function load(): Promise<void> {
        const answer = await fetchTournamentConfig(tournamentId);
        if (!disposed) {
            shown = showAnswer(mount, answer);
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
