import { type TileFace } from "@/entities/tile/lib/tile-utils";
import { WIND_LETTERS, type WindScript, pageWindScript } from "@/shared/i18n";

export const TILE_LABELS_KEY = "ronin.v2.tile-labels";

/**
 * The honors' labels in rank order, the winds then white, green and red: the dragons take two letters where one would
 * read as West. None in kanji, which the honors' faces already are.
 */
const HONOR_LABELS: Readonly<Record<WindScript, readonly string[]>> = {
    cyrillic: [...WIND_LETTERS.cyrillic, "Б", "Зе", "К"],
    kanji: [],
    latin: [...WIND_LETTERS.latin, "Wh", "G", "R"],
};

/** The script of the tiles' corner labels on the page, its wind script; null while the labels are off. */
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

/** Turn the corner labels on or off, kept in this browser. */
export function applyTileLabels(on: boolean): void {
    showTileLabels(on);
    try {
        localStorage.setItem(TILE_LABELS_KEY, JSON.stringify(on));
    } catch {
        return;
    }
}

/** The page at the choice this browser kept; off when there is none. */
export function restoreTileLabels(): void {
    try {
        showTileLabels(JSON.parse(localStorage.getItem(TILE_LABELS_KEY) ?? "false") === true);
    } catch {
        showTileLabels(false);
    }
}

/** A face's corner label: a suit tile's rank, an honor's letters in `script`. */
export function tileLabel(face: TileFace, script: WindScript): string | null {
    const [rank, suit] = face;
    if (suit !== "z") {
        return rank === "0" ? "5" : rank;
    }
    return HONOR_LABELS[script][Number(rank) - 1] ?? null;
}
