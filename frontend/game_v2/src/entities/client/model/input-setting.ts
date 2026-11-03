export interface InputSetting {
    readonly rightClick: boolean;
}

export const INPUT_SETTING_KEY = "ronin.v2.input";
export const DEFAULT_INPUT_SETTING: InputSetting = { rightClick: true };

export function readInputSetting(stored: unknown): InputSetting {
    if (
        typeof stored !== "object" ||
        stored === null ||
        !("rightClick" in stored) ||
        typeof stored.rightClick !== "boolean"
    ) {
        return DEFAULT_INPUT_SETTING;
    }
    return { rightClick: stored.rightClick };
}
