import { isRecord } from "@/api";

export interface ChartLatest {
    readonly ageSeconds: number;
    readonly value: number | null;
}

export interface ChartPlot {
    readonly axisMaximum: number;
    readonly lines: readonly string[];
}

export interface MonitoringChart {
    readonly latest: ChartLatest | null;
    readonly name: string;
    readonly plot: ChartPlot | null;
    readonly retentionDays: number | null;
    readonly state: string;
    readonly unit: string;
}

export interface MonitoringChartGroup {
    readonly charts: readonly MonitoringChart[];
    readonly group: string;
}

export interface CompletedDurations {
    readonly meanSeconds: number;
    readonly medianSeconds: number;
    readonly p90Seconds: number;
}

export interface GamesSummary {
    readonly abandoned: number;
    readonly completed: number;
    readonly completedDurations: CompletedDurations | null;
    readonly error: number;
    readonly started: number;
    readonly unfinished: number;
}

export interface LiveStatus {
    readonly activeGames: number;
    readonly pendingGames: number;
}

export interface MonitoringReport {
    readonly chartGroups: readonly MonitoringChartGroup[];
    readonly collectedSince: string | null;
    readonly games: GamesSummary;
    readonly lastBackupAgeSeconds: number | null;
    readonly liveStatus: LiveStatus | null;
    readonly plotHeight: number;
    readonly plotWidth: number;
    readonly range: string;
    readonly ranges: readonly string[];
    readonly timeAxis: readonly string[];
}

export type MonitoringFailure = "failed" | "not_found";

export interface MonitoringState {
    failure: MonitoringFailure | null;
    report: MonitoringReport | null;
    readonly requestedRange: string | null;
}

const GAME_SERVER_UNAVAILABLE = "unavailable";

export function createMonitoringState(requestedRange: string | null): MonitoringState {
    return { failure: null, report: null, requestedRange };
}

function isNumberOrNull(value: unknown): value is number | null {
    return value === null || typeof value === "number";
}

function isStringOrNull(value: unknown): value is string | null {
    return value === null || typeof value === "string";
}

function isStringList(value: unknown): value is string[] {
    return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function parseLatest(value: unknown): ChartLatest | null | undefined {
    if (value === null) {
        return null;
    }
    if (!isRecord(value) || !isNumberOrNull(value.value) || typeof value.age_seconds !== "number") {
        return undefined;
    }
    return { ageSeconds: value.age_seconds, value: value.value };
}

function parsePlot(value: unknown): ChartPlot | null | undefined {
    if (value === null) {
        return null;
    }
    if (!isRecord(value) || !isStringList(value.lines) || typeof value.axis_maximum !== "number") {
        return undefined;
    }
    return { axisMaximum: value.axis_maximum, lines: value.lines };
}

function parseChart(value: unknown): MonitoringChart | null {
    if (!isRecord(value)) {
        return null;
    }
    const { name, retention_days: retentionDays, state, unit } = value;
    const latest = parseLatest(value.latest);
    const plot = parsePlot(value.plot);
    if (
        typeof name !== "string" ||
        typeof unit !== "string" ||
        typeof state !== "string" ||
        !isNumberOrNull(retentionDays) ||
        latest === undefined ||
        plot === undefined
    ) {
        return null;
    }
    return { latest, name, plot, retentionDays, state, unit };
}

function parseChartGroups(value: unknown): MonitoringChartGroup[] | null {
    if (!isRecord(value)) {
        return null;
    }
    const groups: MonitoringChartGroup[] = [];
    for (const [group, charts] of Object.entries(value)) {
        const parsed = Array.isArray(charts) ? charts.map(parseChart) : [null];
        if (parsed.includes(null)) {
            return null;
        }
        groups.push({ charts: parsed.filter((chart) => chart !== null), group });
    }
    return groups;
}

function parseDurations(value: unknown): CompletedDurations | null | undefined {
    if (value === null) {
        return null;
    }
    if (
        !isRecord(value) ||
        typeof value.mean_seconds !== "number" ||
        typeof value.median_seconds !== "number" ||
        typeof value.p90_seconds !== "number"
    ) {
        return undefined;
    }
    return {
        meanSeconds: value.mean_seconds,
        medianSeconds: value.median_seconds,
        p90Seconds: value.p90_seconds,
    };
}

function parseGames(value: unknown): GamesSummary | null {
    if (!isRecord(value)) {
        return null;
    }
    const { abandoned, completed, error, started, unfinished } = value;
    const completedDurations = parseDurations(value.completed_durations);
    if (
        typeof started !== "number" ||
        typeof completed !== "number" ||
        typeof abandoned !== "number" ||
        typeof error !== "number" ||
        typeof unfinished !== "number" ||
        completedDurations === undefined
    ) {
        return null;
    }
    return { abandoned, completed, completedDurations, error, started, unfinished };
}

function parseLiveStatus(value: unknown): LiveStatus | null | undefined {
    if (value === GAME_SERVER_UNAVAILABLE) {
        return null;
    }
    if (
        !isRecord(value) ||
        typeof value.active_games !== "number" ||
        typeof value.pending_games !== "number"
    ) {
        return undefined;
    }
    return { activeGames: value.active_games, pendingGames: value.pending_games };
}

export function parseMonitoring(data: unknown): MonitoringReport | null {
    if (!isRecord(data)) {
        return null;
    }
    const {
        collected_since: collectedSince,
        last_backup_age_seconds: lastBackupAgeSeconds,
        plot_height: plotHeight,
        plot_width: plotWidth,
        range,
        ranges,
        time_axis: timeAxis,
    } = data;
    const chartGroups = parseChartGroups(data.chart_groups);
    const games = parseGames(data.games);
    const liveStatus = parseLiveStatus(data.live_status);
    if (
        typeof range !== "string" ||
        !isStringList(ranges) ||
        !isStringOrNull(collectedSince) ||
        !isStringList(timeAxis) ||
        typeof plotWidth !== "number" ||
        typeof plotHeight !== "number" ||
        !isNumberOrNull(lastBackupAgeSeconds) ||
        chartGroups === null ||
        games === null ||
        liveStatus === undefined
    ) {
        return null;
    }
    return {
        chartGroups,
        collectedSince,
        games,
        lastBackupAgeSeconds,
        liveStatus,
        plotHeight,
        plotWidth,
        range,
        ranges,
        timeAxis,
    };
}
