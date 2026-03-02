const WIND_NAMES = ["East", "South", "West", "North"] as const;

export function windName(wind: number): string {
    return WIND_NAMES[wind] ?? "Unknown";
}
