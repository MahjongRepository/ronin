const WIND_NAMES = ["East", "South", "West", "North"] as const;
const WIND_LETTERS = ["E", "S", "W", "N"] as const;

export function windName(wind: number): string {
    return WIND_NAMES[wind] ?? "Unknown";
}

export function windLetter(wind: number): string {
    return WIND_LETTERS[wind] ?? "?";
}
