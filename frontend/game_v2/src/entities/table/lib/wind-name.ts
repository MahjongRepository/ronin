import { type MessageKey, WIND_LETTERS, pageWindScript, t } from "@/shared/i18n";

const WIND_NAMES: readonly MessageKey[] = ["wind.east", "wind.south", "wind.west", "wind.north"];
const UNKNOWN_WIND_LETTER = "?";

export function windName(wind: number): string {
    return t(WIND_NAMES[wind] ?? "wind.unknown");
}

export function windLetter(wind: number): string {
    return WIND_LETTERS[pageWindScript()][wind] ?? UNKNOWN_WIND_LETTER;
}
