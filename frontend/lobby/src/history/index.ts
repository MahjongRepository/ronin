import { type MountedView } from "@ronin/shared/router";

import { apiGet } from "@/api";
import { type HistoryState, createHistoryState, parseHistory } from "@/history/state";
import { renderHistory } from "@/history/ui";

async function loadHistory(
    state: HistoryState,
    isDisposed: () => boolean,
    render: () => void,
): Promise<void> {
    const result = await apiGet("/api/lobby/history");
    if (isDisposed()) {
        return;
    }
    const games = result.ok ? parseHistory(result.data) : null;
    if (games === null) {
        console.error("history not loaded", result.ok ? "invalid answer" : result.error);
        state.loadFailed = true;
    } else {
        state.games = games;
    }
    render();
}

export function mountHistoryView(host: HTMLElement): MountedView {
    const state = createHistoryState();
    let disposed = false;
    function render(): void {
        renderHistory(host, state);
    }

    render();
    void loadHistory(state, () => disposed, render);
    return {
        rerender: render,
        unmount: () => {
            disposed = true;
        },
    };
}
