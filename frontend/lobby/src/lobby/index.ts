import { type MountedView } from "@ronin/shared/router";

import { watchCurrentGames } from "@/lobby/games-feed";
import {
    type LobbyViewContext,
    createRoom,
    createTournament,
    loadOwnTournaments,
    loadRooms,
} from "@/lobby/handlers";
import { type LobbyState, createLobbyState, noticeFromUrl } from "@/lobby/state";
import { renderLobby } from "@/lobby/ui";

export interface LobbyViewDeps {
    readonly navigate: (url: string) => void;
}

function dropNoticeFromUrl(url: URL): void {
    if (!url.searchParams.has("notice")) {
        return;
    }
    const clean = new URL(url);
    clean.searchParams.delete("notice");
    window.history.replaceState(window.history.state, "", clean);
}

function loadRoomsAndWatchGames(state: LobbyState, context: LobbyViewContext): () => void {
    let stop: (() => void) | null = null;
    let stopped = false;
    void loadRooms(state, context).then((gamesWsUrl) => {
        if (gamesWsUrl === null || stopped) {
            return;
        }
        stop = watchCurrentGames(gamesWsUrl, (games) => {
            state.games = games;
            context.render();
        });
    });
    return () => {
        stopped = true;
        stop?.();
    };
}

export function mountLobbyView(host: HTMLElement, url: URL, deps: LobbyViewDeps): MountedView {
    const state = createLobbyState(noticeFromUrl(url));
    let disposed = false;
    const context = {
        isDisposed: () => disposed,
        navigate: deps.navigate,
        render,
    };
    const actions = {
        createRoom: () => void createRoom(state, context),
        createTournament: (name: string) => void createTournament(state, context, name),
    };

    function render(): void {
        renderLobby(host, state, actions);
    }

    dropNoticeFromUrl(url);
    render();
    const stopWatchingGames = loadRoomsAndWatchGames(state, context);
    void loadOwnTournaments(state, context);
    return {
        rerender: render,
        unmount: () => {
            disposed = true;
            stopWatchingGames();
        },
    };
}
