export interface AutoWinSetting {
    readonly keepBetweenRounds: boolean;
}

export const AUTO_WIN_SETTING_KEY = "ronin.v2.auto_win";
export const DEFAULT_AUTO_WIN_SETTING: AutoWinSetting = { keepBetweenRounds: false };

export function readAutoWinSetting(stored: unknown): AutoWinSetting {
    if (
        typeof stored !== "object" ||
        stored === null ||
        !("keepBetweenRounds" in stored) ||
        typeof stored.keepBetweenRounds !== "boolean"
    ) {
        return DEFAULT_AUTO_WIN_SETTING;
    }
    return { keepBetweenRounds: stored.keepBetweenRounds };
}
