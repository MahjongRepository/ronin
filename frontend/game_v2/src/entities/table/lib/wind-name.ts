import { type MessageKey, t } from "@/shared/i18n";

const WIND_NAMES: readonly MessageKey[] = ["wind.east", "wind.south", "wind.west", "wind.north"];
const WIND_LETTERS: readonly MessageKey[] = [
    "wind.short.east",
    "wind.short.south",
    "wind.short.west",
    "wind.short.north",
];

export function windName(wind: number): string {
    return t(WIND_NAMES[wind] ?? "wind.unknown");
}

export function windLetter(wind: number): string {
    return t(WIND_LETTERS[wind] ?? "wind.short.unknown");
}
