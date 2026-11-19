import { apiGet, apiPost } from "@/api";
import {
    type TournamentsState,
    parseCreatedTournamentId,
    parseOwnTournaments,
    tournamentPath,
} from "@/tournaments/state";

export interface TournamentsViewContext {
    readonly isDisposed: () => boolean;
    readonly navigate: (url: string) => void;
    readonly render: () => void;
}

export async function loadOwnTournaments(
    state: TournamentsState,
    context: TournamentsViewContext,
): Promise<void> {
    const result = await apiGet("/api/lobby/tournaments");
    if (context.isDisposed()) {
        return;
    }
    const own = result.ok ? parseOwnTournaments(result.data) : null;
    if (own === null) {
        console.error("own tournaments not loaded", result.ok ? "invalid answer" : result.error);
        state.loadFailed = true;
    } else {
        state.own = own;
    }
    context.render();
}

async function postNewTournament(name: string): Promise<string | null> {
    const result = await apiPost("/api/lobby/tournaments", { name });
    const tournamentId = result.ok ? parseCreatedTournamentId(result.data) : null;
    if (tournamentId === null) {
        console.error("tournament not created", result.ok ? "invalid answer" : result.error);
    }
    return tournamentId;
}

function enterCreatedTournament(
    state: TournamentsState,
    context: TournamentsViewContext,
    tournamentId: string | null,
): void {
    state.creating = false;
    if (tournamentId === null) {
        state.createFailed = true;
        context.render();
        return;
    }
    context.navigate(tournamentPath(tournamentId));
}

export async function createTournament(
    state: TournamentsState,
    context: TournamentsViewContext,
    name: string,
): Promise<void> {
    if (state.creating) {
        return;
    }
    state.creating = true;
    state.createFailed = false;
    context.render();
    const tournamentId = await postNewTournament(name);
    if (!context.isDisposed()) {
        enterCreatedTournament(state, context, tournamentId);
    }
}
