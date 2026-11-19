import { type WindScript, pageWindScript } from "./winds";

export const TILE_LABELS_KEY = "ronin.v2.tile-labels";

export function pageTileLabels(): WindScript | null {
    return document.documentElement.dataset.tileLabels === "on" ? pageWindScript() : null;
}

function showTileLabels(on: boolean): void {
    if (on) {
        document.documentElement.dataset.tileLabels = "on";
        return;
    }
    delete document.documentElement.dataset.tileLabels;
}

export function applyTileLabels(on: boolean): void {
    showTileLabels(on);
    try {
        localStorage.setItem(TILE_LABELS_KEY, JSON.stringify(on));
    } catch {
        return;
    }
}

export function restoreTileLabels(): void {
    try {
        showTileLabels(JSON.parse(localStorage.getItem(TILE_LABELS_KEY) ?? "false") === true);
    } catch {
        showTileLabels(false);
    }
}
