import { isRecord } from "@/api";

export interface HistoryPlayer {
    readonly finalScore: number | null;
    readonly isViewer: boolean;
    readonly isWinner: boolean;
    readonly name: string;
    readonly score: number | null;
}

export interface HistoryGame {
    readonly durationSeconds: number | null;
    readonly gameType: string;
    readonly numRoundsPlayed: number | null;
    readonly players: readonly HistoryPlayer[];
    readonly replayUrl: string;
    readonly startedAt: Date;
    readonly viewerReplayUrl: string;
    readonly wind: string | null;
}

export interface HistoryState {
    games: readonly HistoryGame[] | null;
    loadFailed: boolean;
}

export function createHistoryState(): HistoryState {
    return { games: null, loadFailed: false };
}

function isNumberOrNull(value: unknown): value is number | null {
    return value === null || typeof value === "number";
}

function isStringOrNull(value: unknown): value is string | null {
    return value === null || typeof value === "string";
}

function parsePlayer(value: unknown): HistoryPlayer | null {
    if (!isRecord(value)) {
        return null;
    }
    const {
        final_score: finalScore,
        is_viewer: isViewer,
        is_winner: isWinner,
        name,
        score,
    } = value;
    if (
        typeof name !== "string" ||
        !isNumberOrNull(score) ||
        !isNumberOrNull(finalScore) ||
        typeof isWinner !== "boolean" ||
        typeof isViewer !== "boolean"
    ) {
        return null;
    }
    return { finalScore, isViewer, isWinner, name, score };
}

function parseStartedAt(value: unknown): Date | null {
    if (typeof value !== "string") {
        return null;
    }
    const startedAt = new Date(value);
    return Number.isNaN(startedAt.getTime()) ? null : startedAt;
}

function parseGame(value: unknown): HistoryGame | null {
    if (!isRecord(value) || !Array.isArray(value.players)) {
        return null;
    }
    const {
        duration_seconds: durationSeconds,
        game_type: gameType,
        num_rounds_played: numRoundsPlayed,
        replay_url: replayUrl,
        viewer_replay_url: viewerReplayUrl,
        wind,
    } = value;
    const startedAt = parseStartedAt(value.started_at);
    const players = value.players.map(parsePlayer);
    if (
        startedAt === null ||
        typeof gameType !== "string" ||
        !isStringOrNull(wind) ||
        !isNumberOrNull(numRoundsPlayed) ||
        !isNumberOrNull(durationSeconds) ||
        typeof replayUrl !== "string" ||
        typeof viewerReplayUrl !== "string" ||
        players.includes(null)
    ) {
        return null;
    }
    return {
        durationSeconds,
        gameType,
        numRoundsPlayed,
        players: players.filter((player) => player !== null),
        replayUrl,
        startedAt,
        viewerReplayUrl,
        wind,
    };
}

export function parseHistory(data: unknown): HistoryGame[] | null {
    if (!isRecord(data) || !Array.isArray(data.games)) {
        return null;
    }
    const games = data.games.map(parseGame);
    return games.includes(null) ? null : games.filter((game) => game !== null);
}
