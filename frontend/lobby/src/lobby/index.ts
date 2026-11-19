import { type MountedView } from "@ronin/shared/router";

import { createRoom, createTournament, loadOwnTournaments, loadRooms } from "@/lobby/handlers";
import { createLobbyState, noticeFromUrl } from "@/lobby/state";
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
    void loadRooms(state, context);
    void loadOwnTournaments(state, context);
    return {
        rerender: render,
        unmount: () => {
            disposed = true;
        },
    };
}
