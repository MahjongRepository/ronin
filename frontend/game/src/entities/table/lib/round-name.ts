import { windName } from "./wind-name";

/** Formats wind + round number + honba: "East 2" or "East 2, 1 honba". */
export function formatRoundName(wind: number, roundNumber: number, honba: number): string {
    const base = `${windName(wind)} ${roundNumber}`;
    if (honba === 0) {
        return base;
    }
    return `${base}, ${honba} honba`;
}
