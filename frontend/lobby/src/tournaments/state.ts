export interface OwnTournament {
    readonly id: string;
    readonly name: string;
}

export interface OwnTournaments {
    readonly nameMaxLength: number;
    readonly tournaments: readonly OwnTournament[];
}

export interface TournamentsState {
    creating: boolean;
    createFailed: boolean;
    loadFailed: boolean;
    own: OwnTournaments | null;
}

export function createTournamentsState(): TournamentsState {
    return { createFailed: false, creating: false, loadFailed: false, own: null };
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

function parseOwnTournament(value: unknown): OwnTournament | null {
    if (!isRecord(value) || typeof value.id !== "string" || typeof value.name !== "string") {
        return null;
    }
    return { id: value.id, name: value.name };
}

export function parseOwnTournaments(data: unknown): OwnTournaments | null {
    if (!isRecord(data) || !Array.isArray(data.tournaments)) {
        return null;
    }
    const nameMaxLength = data.name_max_length;
    const tournaments = data.tournaments.map(parseOwnTournament);
    if (
        typeof nameMaxLength !== "number" ||
        !Number.isInteger(nameMaxLength) ||
        nameMaxLength <= 0 ||
        tournaments.includes(null)
    ) {
        return null;
    }
    return { nameMaxLength, tournaments: tournaments.filter((entry) => entry !== null) };
}

export function parseCreatedTournamentId(data: unknown): string | null {
    return isRecord(data) && typeof data.tournament_id === "string" && data.tournament_id !== ""
        ? data.tournament_id
        : null;
}

export function tournamentPath(tournamentId: string): string {
    return `/tournaments/${encodeURIComponent(tournamentId)}`;
}
