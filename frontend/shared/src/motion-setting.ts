export interface MotionSetting {
    readonly animations: boolean;
}

export const MOTION_SETTING_KEY = "ronin.v2.motion";
export const DEFAULT_MOTION_SETTING: MotionSetting = { animations: true };

export function readMotionSetting(stored: unknown): MotionSetting {
    if (
        typeof stored !== "object" ||
        stored === null ||
        !("animations" in stored) ||
        typeof stored.animations !== "boolean"
    ) {
        return DEFAULT_MOTION_SETTING;
    }
    return { animations: stored.animations };
}
