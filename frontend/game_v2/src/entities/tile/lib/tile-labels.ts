import { type TileFace } from "@/entities/tile/lib/tile-utils";
import { WIND_LETTERS, type WindScript } from "@/shared/i18n";

/**
 * The honors' labels in rank order, the winds then white, green and red: the dragons take two letters where one would
 * read as West. None in kanji, which the honors' faces already are.
 */
const HONOR_LABELS: Readonly<Record<WindScript, readonly string[]>> = {
    cyrillic: [...WIND_LETTERS.cyrillic, "Б", "Зе", "К"],
    kanji: [],
    latin: [...WIND_LETTERS.latin, "Wh", "G", "R"],
};

/** A face's corner label: a suit tile's rank, an honor's letters in `script`. */
export function tileLabel(face: TileFace, script: WindScript): string | null {
    const [rank, suit] = face;
    if (suit !== "z") {
        return rank === "0" ? "5" : rank;
    }
    return HONOR_LABELS[script][Number(rank) - 1] ?? null;
}
