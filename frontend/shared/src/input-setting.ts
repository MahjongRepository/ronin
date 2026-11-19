/** The keyboard and mouse settings this browser keeps: right-click's shortcuts, and the decision controls' keycaps. */
export interface InputSetting {
    readonly rightClick: boolean;
    readonly keyHints: boolean;
}

export const INPUT_SETTING_KEY = "ronin.v2.input";
export const DEFAULT_INPUT_SETTING: InputSetting = { keyHints: false, rightClick: true };

function storedFlag(stored: unknown, name: keyof InputSetting): boolean {
    const value: unknown =
        typeof stored === "object" && stored !== null && name in stored
            ? Reflect.get(stored, name)
            : undefined;
    return typeof value === "boolean" ? value : DEFAULT_INPUT_SETTING[name];
}

/** The stored setting, each field read on its own, so one saved before key hints keeps its right-click choice. */
export function readInputSetting(stored: unknown): InputSetting {
    return {
        keyHints: storedFlag(stored, "keyHints"),
        rightClick: storedFlag(stored, "rightClick"),
    };
}
