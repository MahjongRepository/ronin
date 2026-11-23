import { type LocalStore } from "./local-store";

export interface MotionSetting {
    readonly animations: boolean;
    readonly discardSlide: boolean;
}

export type MotionChange = Pick<MotionSetting, "animations"> | Pick<MotionSetting, "discardSlide">;

export const MOTION_SETTING_KEY = "ronin.v2.motion";
export const DEFAULT_MOTION_SETTING: MotionSetting = { animations: true, discardSlide: true };

function storedSwitch(stored: object, name: keyof MotionSetting): boolean {
    const value: unknown = Reflect.get(stored, name);
    return typeof value === "boolean" ? value : DEFAULT_MOTION_SETTING[name];
}

export function readMotionSetting(stored: unknown): MotionSetting {
    if (typeof stored !== "object" || stored === null) {
        return DEFAULT_MOTION_SETTING;
    }
    return {
        animations: storedSwitch(stored, "animations"),
        discardSlide: storedSwitch(stored, "discardSlide"),
    };
}

export function saveMotionChange(store: LocalStore<MotionSetting>, change: MotionChange): void {
    store.save({ ...store.load(), ...change });
}
