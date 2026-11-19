export interface SoundSetting {
    readonly sound_on: boolean;
}

export const SOUND_SETTING_KEY = "Majiang.pref";

export const DEFAULT_SOUND_SETTING: SoundSetting = { sound_on: true };

export function readSoundSetting(stored: unknown): SoundSetting {
    if (typeof stored !== "object" || stored === null || !("sound_on" in stored)) {
        return DEFAULT_SOUND_SETTING;
    }
    const { sound_on: soundOn } = stored;
    return typeof soundOn === "boolean" ? { sound_on: soundOn } : DEFAULT_SOUND_SETTING;
}
