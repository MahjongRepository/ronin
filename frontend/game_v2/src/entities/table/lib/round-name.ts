import { windName } from "./wind-name";

/** A round's name from its wind and its number within the wind: "East 2". */
export function roundName(wind: number, roundInWind: number): string {
    return `${windName(wind)} ${roundInWind}`;
}

/** A round's name with its honba: "East 2" or "East 2, 1 honba". */
export function formatRoundName(wind: number, roundInWind: number, honba: number): string {
    const base = roundName(wind, roundInWind);
    if (honba === 0) {
        return base;
    }
    return `${base}, ${honba} honba`;
}
