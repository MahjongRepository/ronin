export interface TournamentRow {
    readonly createdAt: Date;
    readonly finished: number;
    readonly finishedAt: Date | null;
    readonly id: string;
    readonly name: string;
    readonly playing: number;
}

export interface TournamentLists {
    readonly canCreate: boolean;
    readonly nameMaxLength: number;
    readonly others: readonly TournamentRow[];
    readonly own: readonly TournamentRow[];
}

export interface TournamentsState {
    creating: boolean;
    createFailed: boolean;
    loadFailed: boolean;
    lists: TournamentLists | null;
}

export function createTournamentsState(): TournamentsState {
    return { createFailed: false, creating: false, lists: null, loadFailed: false };
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}

function isCount(value: unknown): value is number {
    return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function parseTournamentRow(value: unknown): TournamentRow | null {
    if (
        !isRecord(value) ||
        typeof value.id !== "string" ||
        typeof value.name !== "string" ||
        typeof value.created_at !== "number" ||
        (value.finished_at !== null && typeof value.finished_at !== "number") ||
        !isCount(value.playing) ||
        !isCount(value.finished)
    ) {
        return null;
    }
    return {
        createdAt: new Date(value.created_at * 1000),
        finished: value.finished,
        finishedAt:
            typeof value.finished_at === "number" ? new Date(value.finished_at * 1000) : null,
        id: value.id,
        name: value.name,
        playing: value.playing,
    };
}

function parseTournamentRows(value: unknown): readonly TournamentRow[] | null {
    if (!Array.isArray(value)) {
        return null;
    }
    const rows = value.map(parseTournamentRow);
    return rows.includes(null) ? null : rows.filter((row) => row !== null);
}

export function parseTournamentLists(data: unknown): TournamentLists | null {
    if (!isRecord(data)) {
        return null;
    }
    const { can_create: canCreate, name_max_length: nameMaxLength } = data;
    const own = parseTournamentRows(data.own);
    const others = parseTournamentRows(data.others);
    if (
        typeof canCreate !== "boolean" ||
        typeof nameMaxLength !== "number" ||
        !Number.isInteger(nameMaxLength) ||
        nameMaxLength <= 0 ||
        own === null ||
        others === null
    ) {
        return null;
    }
    return { canCreate, nameMaxLength, others, own };
}

export function parseCreatedTournamentId(data: unknown): string | null {
    return isRecord(data) && typeof data.tournament_id === "string" && data.tournament_id !== ""
        ? data.tournament_id
        : null;
}

export function tournamentPath(tournamentId: string): string {
    return `/tournaments/${encodeURIComponent(tournamentId)}`;
}
