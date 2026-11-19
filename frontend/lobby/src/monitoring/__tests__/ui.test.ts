import { afterEach, describe, expect, it } from "vitest";

import { createMonitoringState, parseMonitoring } from "@/monitoring/state";
import { renderMonitoring } from "@/monitoring/ui";

const NEVER_COLLECTED_CHART = {
    bucketed: null,
    latest: null,
    name: "disk_used",
    plot: null,
    retention_days: null,
    state: "never_collected",
    unit: "percent",
};

const PLOTTED_CHART = {
    bucketed: { buckets: 4, empty_buckets: 1, max: 75, mean: 50 },
    latest: { age_seconds: 90, value: 75 },
    name: "memory_used",
    plot: { axis_maximum: 100, lines: ["37.50,50.00 112.50,25.00", "262.50,22.00 262.50,22.00"] },
    retention_days: null,
    state: "current",
    unit: "percent",
};

const REPORT = {
    chart_groups: { host: [PLOTTED_CHART, NEVER_COLLECTED_CHART] },
    charted_from: 1_800_000_000,
    charted_to: 1_800_003_600,
    collected_since: null,
    games: {
        abandoned: 0,
        completed: 0,
        completed_durations: null,
        error: 0,
        started: 0,
        unfinished: 0,
    },
    last_backup_age_seconds: null,
    live_status: "unavailable",
    plot_height: 100,
    plot_width: 300,
    range: "1h",
    ranges: ["1h", "24h", "7d", "30d", "90d"],
    starts_at_oldest_sample: false,
    time_axis: ["11:00", "11:30", "12:00"],
};

function renderReport(): HTMLElement {
    const state = createMonitoringState(null);
    state.report = parseMonitoring(REPORT);
    const host = document.createElement("main");
    document.body.append(host);
    renderMonitoring(host, state);
    return host;
}

afterEach(() => {
    document.body.replaceChildren();
});

describe("renderMonitoring", () => {
    it("draws one polyline per plot line in the server's plot box, with its axis and latest reading", () => {
        const host = renderReport();

        const chart = host.querySelector('[data-chart="host.memory_used"]');
        const plot = chart?.querySelector("svg.monitoring-chart-plot");
        expect(plot?.getAttribute("viewBox")).toBe("0 0 300 100");
        expect(
            [...(plot?.querySelectorAll("polyline") ?? [])].map((line) =>
                line.getAttribute("points"),
            ),
        ).toEqual(PLOTTED_CHART.plot.lines);
        expect(chart?.querySelector(".monitoring-chart-axis")?.textContent).toBe("100%");
        expect(chart?.querySelector(".monitoring-chart-latest")?.textContent).toBe(
            "Latest 75%, 1m 30s ago",
        );
        expect(
            [...(chart?.querySelectorAll(".monitoring-chart-times span") ?? [])].map(
                (span) => span.textContent,
            ),
        ).toEqual(REPORT.time_axis);
    });

    it("shows a never-collected chart's state text instead of a plot", () => {
        const host = renderReport();

        const chart = host.querySelector('[data-chart="host.disk_used"]');
        expect(chart?.getAttribute("data-state")).toBe("never_collected");
        expect(chart?.querySelector(".monitoring-chart-note")?.textContent).toBe("Never collected");
        expect(chart?.querySelector("svg")).toBeNull();
    });

    it("keeps the range bar on the requested range while the report loads", () => {
        const host = document.createElement("main");
        document.body.append(host);

        renderMonitoring(host, createMonitoringState("7d"));

        expect(
            [...host.querySelectorAll(".monitoring-range")].map((link) => [
                link.getAttribute("href"),
                link.getAttribute("aria-current"),
            ]),
        ).toEqual([
            ["?range=1h", null],
            ["?range=24h", null],
            ["?range=7d", "page"],
            ["?range=30d", null],
            ["?range=90d", null],
        ]);
        expect(host.querySelector(".monitoring-panels")).toBeNull();
    });
});
