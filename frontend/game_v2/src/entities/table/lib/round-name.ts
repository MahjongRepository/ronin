import { type MessageKey, t } from "@/shared/i18n";

import { windName } from "./wind-name";

const ROUND_NAMES: readonly (readonly MessageKey[])[] = [
    ["round.east_1", "round.east_2", "round.east_3", "round.east_4"],
    ["round.south_1", "round.south_2", "round.south_3", "round.south_4"],
    ["round.west_1", "round.west_2", "round.west_3", "round.west_4"],
    ["round.north_1", "round.north_2", "round.north_3", "round.north_4"],
];

export function roundName(wind: number, roundInWind: number): string {
    const key = ROUND_NAMES[wind]?.[roundInWind - 1];
    if (key === undefined) {
        return t("round.unknown", { number: roundInWind, wind: windName(wind) });
    }
    return t(key);
}

export function formatRoundName(wind: number, roundInWind: number, honba: number): string {
    const base = roundName(wind, roundInWind);
    return honba === 0 ? base : t("round.with_honba", { count: honba, round: base });
}
