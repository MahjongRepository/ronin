import { type TemplateResult, html, nothing, render, svg } from "lit-html";

import { pageFailedView } from "@/app/page-failed";
import { formatDuration } from "@/format-duration";
import { type MessageKey, formatNumber, reportI18nError, t } from "@/i18n";
import {
    type GamesSummary,
    type LiveStatus,
    type MonitoringChart,
    type MonitoringChartGroup,
    type MonitoringReport,
    type MonitoringState,
} from "@/monitoring/state";

const RANGE_LABELS: ReadonlyMap<string, MessageKey> = new Map([
    ["1h", "monitoring.range.1h"],
    ["24h", "monitoring.range.24h"],
    ["7d", "monitoring.range.7d"],
    ["30d", "monitoring.range.30d"],
    ["90d", "monitoring.range.90d"],
]);

const GROUP_LABELS: ReadonlyMap<string, MessageKey> = new Map([
    ["host", "monitoring.group.host"],
    ["services", "monitoring.group.services"],
    ["game", "monitoring.group.game"],
    ["sockets", "monitoring.group.sockets"],
    ["traefik", "monitoring.group.traefik"],
    ["storage", "monitoring.group.storage"],
]);

const SERIES_LABELS: ReadonlyMap<string, MessageKey> = new Map([
    ["host.cpu_busy", "monitoring.series.host.cpu_busy"],
    ["host.memory_used", "monitoring.series.host.memory_used"],
    ["host.disk_used", "monitoring.series.host.disk_used"],
    ["services.lobby_memory", "monitoring.series.services.lobby_memory"],
    ["services.game_memory", "monitoring.series.services.game_memory"],
    ["services.traefik_memory", "monitoring.series.services.traefik_memory"],
    ["services.lobby_cpu", "monitoring.series.services.lobby_cpu"],
    ["services.game_cpu", "monitoring.series.services.game_cpu"],
    ["services.traefik_cpu", "monitoring.series.services.traefik_cpu"],
    ["services.oom_kills", "monitoring.series.services.oom_kills"],
    ["game.active_games", "monitoring.series.game.active_games"],
    ["game.loop_lag_max", "monitoring.series.game.loop_lag_max"],
    ["game.timeouts", "monitoring.series.game.timeouts"],
    ["game.ai_replacements", "monitoring.series.game.ai_replacements"],
    ["game.reconnects", "monitoring.series.game.reconnects"],
    ["sockets.open", "monitoring.series.sockets.open"],
    ["sockets.messages_in", "monitoring.series.sockets.messages_in"],
    ["sockets.handling_time", "monitoring.series.sockets.handling_time"],
    ["sockets.rejected_messages", "monitoring.series.sockets.rejected_messages"],
    ["sockets.abnormal_closes", "monitoring.series.sockets.abnormal_closes"],
    ["traefik.requests", "monitoring.series.traefik.requests"],
    ["traefik.server_errors", "monitoring.series.traefik.server_errors"],
    ["traefik.response_time", "monitoring.series.traefik.response_time"],
    ["storage.database", "monitoring.series.storage.database"],
    ["storage.replays", "monitoring.series.storage.replays"],
]);

const UNIT_LABELS: ReadonlyMap<string, MessageKey> = new Map([
    ["percent", "monitoring.unit.percent"],
    ["mib", "monitoring.unit.mib"],
    ["cores", "monitoring.unit.cores"],
    ["count", "monitoring.unit.count"],
    ["per_second", "monitoring.unit.per_second"],
    ["per_minute", "monitoring.unit.per_minute"],
    ["milliseconds", "monitoring.unit.milliseconds"],
]);

const CHART_STATE = {
    NEVER_COLLECTED: "never_collected",
    STALE: "stale",
    UNAVAILABLE: "unavailable",
} as const;

const DEFAULT_RANGE = "24h";
const STORAGE_GROUP = "storage";
const NOT_FOUND_STATUS = "404";
const ROUNDS_TO_ZERO_BELOW = 0.05;

function codeLabel(labels: ReadonlyMap<string, MessageKey>, code: string, family: string): string {
    const key = labels.get(code);
    if (key === undefined) {
        reportI18nError(`${family}${code}`, "unknown monitoring code");
        return code;
    }
    return t(key);
}

function formatDecimal(value: number): string {
    const roundsToZero = value !== 0 && Math.abs(value) < ROUNDS_TO_ZERO_BELOW;
    return formatNumber(
        value,
        roundsToZero ? { maximumSignificantDigits: 2 } : { maximumFractionDigits: 1 },
    );
}

function unitValue(unit: string, value: number): string {
    const key = UNIT_LABELS.get(unit);
    if (key === undefined) {
        reportI18nError(`monitoring.unit.${unit}`, "unknown monitoring code");
        return formatDecimal(value);
    }
    return t(key, { value: formatDecimal(value) });
}

function stat(name: string, label: MessageKey, value: string): TemplateResult {
    return html`<div class="monitoring-stat"><dt>${t(label)}</dt><dd data-stat=${name}>${value}</dd></div>`;
}

function rangesTemplate(
    ranges: readonly string[],
    current: string,
    collectedSince: string | null,
): TemplateResult {
    return html`<nav class="monitoring-ranges" aria-label=${t("monitoring.range.label")}>
            ${ranges.map(
                (choice) =>
                    html`<a
                        href="?range=${choice}"
                        class="monitoring-range"
                        aria-current=${choice === current ? "page" : nothing}
                        >${codeLabel(RANGE_LABELS, choice, "monitoring.range.")}</a
                    >`,
            )}
        </nav>
        <p class="monitoring-chart-note monitoring-range-note">
            <span>${t("monitoring.range.times_utc")}</span>${
                collectedSince === null
                    ? nothing
                    : html`<span>${t("monitoring.range.collected_since", { time: collectedSince })}</span>`
            }
        </p>`;
}

function livePanel(liveStatus: LiveStatus | null): TemplateResult {
    return html`<article class="monitoring-panel">
        <h3>${t("monitoring.live.title")}</h3>
        ${
            liveStatus
                ? html`<dl class="monitoring-stats">
                      ${stat("active", "monitoring.live.active", formatNumber(liveStatus.activeGames))}
                      ${stat("pending", "monitoring.live.pending", formatNumber(liveStatus.pendingGames))}
                  </dl>`
                : html`<p class="monitoring-unavailable">${t("monitoring.live.unavailable")}</p>`
        }
    </article>`;
}

function durationsTemplate(games: GamesSummary): TemplateResult {
    const durations = games.completedDurations;
    if (durations === null) {
        return html`<p class="monitoring-unavailable">${t("monitoring.games.no_completed")}</p>`;
    }
    return html`<dl class="monitoring-stats">
        ${stat("mean", "monitoring.games.duration_mean", formatDuration(durations.meanSeconds))}
        ${stat("median", "monitoring.games.duration_median", formatDuration(durations.medianSeconds))}
        ${stat("p90", "monitoring.games.duration_p90", formatDuration(durations.p90Seconds))}
    </dl>`;
}

function gamesPanel(games: GamesSummary): TemplateResult {
    return html`<article class="monitoring-panel">
        <h3>${t("monitoring.games.title")}</h3>
        <dl class="monitoring-stats">
            ${stat("started", "monitoring.games.started", formatNumber(games.started))}
            ${stat("completed", "monitoring.games.completed", formatNumber(games.completed))}
            ${stat("abandoned", "monitoring.games.abandoned", formatNumber(games.abandoned))}
            ${stat("error", "monitoring.games.error", formatNumber(games.error))}
            ${stat("unfinished", "monitoring.games.unfinished", formatNumber(games.unfinished))}
        </dl>

        <h4>${t("monitoring.games.durations")}</h4>
        ${durationsTemplate(games)}
    </article>`;
}

function lastBackupTemplate(ageSeconds: number | null): TemplateResult {
    const shown =
        ageSeconds === null
            ? t("monitoring.storage.last_backup_unknown")
            : t("monitoring.storage.last_backup_age", { age: formatDuration(ageSeconds) });
    return html`<dl class="monitoring-stats monitoring-group-stats">
        ${stat("last_backup", "monitoring.storage.last_backup", shown)}
    </dl>`;
}

function captionTemplate(chart: MonitoringChart, group: string): TemplateResult {
    const { latest } = chart;
    return html`<figcaption class="monitoring-chart-caption">
        <span class="monitoring-chart-label"
            >${codeLabel(SERIES_LABELS, `${group}.${chart.name}`, "monitoring.series.")}</span
        >
        ${
            latest === null || latest.value === null
                ? nothing
                : html`<span class="monitoring-chart-latest"
                      >${t("monitoring.chart.latest", {
                          age: formatDuration(latest.ageSeconds),
                          value: unitValue(chart.unit, latest.value),
                      })}</span
                  >`
        }
    </figcaption>`;
}

function plotTemplate(chart: MonitoringChart, report: MonitoringReport): TemplateResult {
    const { plot } = chart;
    if (plot === null) {
        return html`<p class="monitoring-chart-note">${t("monitoring.chart.no_samples")}</p>`;
    }
    const width = report.plotWidth;
    const height = report.plotHeight;
    return html`<span class="monitoring-chart-axis">${unitValue(chart.unit, plot.axisMaximum)}</span>
        <svg
            class="monitoring-chart-plot"
            viewBox="0 0 ${width} ${height}"
            preserveAspectRatio="none"
            aria-hidden="true"
        >
            <line class="monitoring-chart-grid" x1="0" y1=${height / 2} x2=${width} y2=${height / 2} />
            ${plot.lines.map((line) => svg`<polyline points=${line} />`)}
        </svg>
        <div class="monitoring-chart-times" aria-hidden="true">
            ${report.timeAxis.map((label) => html`<span>${label}</span>`)}
        </div>`;
}

function chartBody(chart: MonitoringChart, report: MonitoringReport): TemplateResult {
    if (chart.state === CHART_STATE.NEVER_COLLECTED) {
        return html`<p class="monitoring-chart-note">${t("monitoring.chart.never_collected")}</p>`;
    }
    if (chart.state === CHART_STATE.UNAVAILABLE) {
        return html`<p class="monitoring-unavailable">${t("monitoring.chart.unavailable")}</p>`;
    }
    const { latest } = chart;
    return html`${plotTemplate(chart, report)}
    ${
        chart.state === CHART_STATE.STALE && latest !== null
            ? html`<p class="monitoring-unavailable">
                  ${t("monitoring.chart.stale", { age: formatDuration(latest.ageSeconds) })}
              </p>`
            : nothing
    }
    ${
        chart.retentionDays
            ? html`<p class="monitoring-chart-note">
                  ${t("monitoring.chart.retention", { count: chart.retentionDays })}
              </p>`
            : nothing
    }`;
}

function chartTemplate(
    chart: MonitoringChart,
    group: string,
    report: MonitoringReport,
): TemplateResult {
    return html`<figure
        class="monitoring-chart"
        data-chart="${group}.${chart.name}"
        data-state=${chart.state}
    >
        ${captionTemplate(chart, group)} ${chartBody(chart, report)}
    </figure>`;
}

function chartGroupTemplate(group: MonitoringChartGroup, report: MonitoringReport): TemplateResult {
    return html`<article class="monitoring-panel monitoring-chart-group">
        <h3>${codeLabel(GROUP_LABELS, group.group, "monitoring.group.")}</h3>
        ${group.group === STORAGE_GROUP ? lastBackupTemplate(report.lastBackupAgeSeconds) : nothing}
        <div class="monitoring-charts">
            ${group.charts.map((chart) => chartTemplate(chart, group.group, report))}
        </div>
    </article>`;
}

function reportTemplate(report: MonitoringReport): TemplateResult {
    return html`${rangesTemplate(report.ranges, report.range, report.collectedSince)}
        <div class="monitoring-panels">${livePanel(report.liveStatus)} ${gamesPanel(report.games)}</div>
        ${report.chartGroups.map((group) => chartGroupTemplate(group, report))}`;
}

function loadingRangesTemplate(requestedRange: string | null): TemplateResult {
    const current =
        requestedRange !== null && RANGE_LABELS.has(requestedRange)
            ? requestedRange
            : DEFAULT_RANGE;
    return rangesTemplate([...RANGE_LABELS.keys()], current, null);
}

function notFoundTemplate(): TemplateResult {
    return html`<section class="lobby-error-page" aria-labelledby="error-title">
        <p class="lobby-error-code">${NOT_FOUND_STATUS}</p>
        <h1 id="error-title">${t("error.not_found.title")}</h1>
        <p class="lobby-muted">${t("error.not_found.message")}</p>
        <p class="lobby-button-row lobby-button-row--center lobby-error-actions">
            <a href="/" role="button">${t("common.back_to_lobby")}</a>
        </p>
    </section>`;
}

function monitoringTemplate(state: MonitoringState): TemplateResult {
    if (state.failure === "not_found") {
        return notFoundTemplate();
    }
    if (state.failure === "failed") {
        return pageFailedView();
    }
    return html`<section class="lobby-section">
        <div class="lobby-section-header">
            <h2>${t("monitoring.title")}</h2>
        </div>

        ${state.report ? reportTemplate(state.report) : loadingRangesTemplate(state.requestedRange)}
    </section>`;
}

export function renderMonitoring(host: HTMLElement, state: MonitoringState): void {
    const page = state.failure === "not_found" ? t("error.not_found.title") : t("monitoring.title");
    document.title = t("page.title.with_page", { page });
    render(monitoringTemplate(state), host);
}
