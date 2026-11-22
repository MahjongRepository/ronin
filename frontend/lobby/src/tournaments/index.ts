import { type MountedView } from "@ronin/shared/router";

import { createTournament, loadTournaments } from "@/tournaments/handlers";
import { createTournamentsState } from "@/tournaments/state";
import { renderTournaments } from "@/tournaments/ui";

export interface TournamentsViewDeps {
    readonly navigate: (url: string) => void;
}

export function mountTournamentsView(host: HTMLElement, deps: TournamentsViewDeps): MountedView {
    const state = createTournamentsState();
    let disposed = false;
    const context = {
        isDisposed: () => disposed,
        navigate: deps.navigate,
        render,
    };
    const actions = {
        createTournament: (name: string) => void createTournament(state, context, name),
    };

    function render(): void {
        renderTournaments(host, state, actions);
    }

    render();
    void loadTournaments(state, context);
    return {
        rerender: render,
        unmount: () => {
            disposed = true;
        },
    };
}
