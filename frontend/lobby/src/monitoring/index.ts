import { type MountedView } from "@ronin/shared/router";

import { type ApiResult, apiGet } from "@/api";
import { type MonitoringState, createMonitoringState, parseMonitoring } from "@/monitoring/state";
import { renderMonitoring } from "@/monitoring/ui";

const NOT_FOUND = "not_found";

function monitoringPath(url: URL): string {
    const range = url.searchParams.get("range");
    return range === null
        ? "/api/lobby/monitoring"
        : `/api/lobby/monitoring?${new URLSearchParams({ range }).toString()}`;
}

function applyMonitoringResult(state: MonitoringState, result: ApiResult): void {
    const report = result.ok ? parseMonitoring(result.data) : null;
    if (report !== null) {
        state.report = report;
    } else if (!result.ok && result.error === NOT_FOUND) {
        state.failure = "not_found";
    } else {
        console.error("monitoring not loaded", result.ok ? "invalid answer" : result.error);
        state.failure = "failed";
    }
}

export function mountMonitoringView(
    host: HTMLElement,
    _params: Record<string, string>,
    url: URL,
): MountedView {
    const state = createMonitoringState();
    let disposed = false;
    function render(): void {
        renderMonitoring(host, state);
    }

    async function load(): Promise<void> {
        const result = await apiGet(monitoringPath(url));
        if (!disposed) {
            applyMonitoringResult(state, result);
            render();
        }
    }

    render();
    void load();
    return {
        rerender: render,
        unmount: () => {
            disposed = true;
        },
    };
}
