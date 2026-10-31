import { type AutoplaySpeed, autoplaySpeedOf } from "./replay-autoplay";

/** A reader's own replay settings, kept across replays: whether the other hands hide, and autoplay's speed. */
export interface ReplayPrefs {
    readonly hideHands: boolean;
    readonly speed: AutoplaySpeed;
}

/** Where a replay view keeps its reader's settings: the entry hands it the browser's (`localStore`). */
export interface ReplayPrefsStore {
    readonly load: () => ReplayPrefs;
    readonly save: (prefs: ReplayPrefs) => void;
}

export const DEFAULT_REPLAY_PREFS: ReplayPrefs = { hideHands: false, speed: 1 };

/** The reader's settings from whatever was kept for them: each readable field, the default for any other. */
export function readReplayPrefs(stored: unknown): ReplayPrefs {
    if (typeof stored !== "object" || stored === null) {
        return DEFAULT_REPLAY_PREFS;
    }
    const { hideHands, speed } = { ...DEFAULT_REPLAY_PREFS, ...stored };
    return {
        hideHands: typeof hideHands === "boolean" ? hideHands : DEFAULT_REPLAY_PREFS.hideHands,
        speed: typeof speed === "number" ? autoplaySpeedOf(speed) : DEFAULT_REPLAY_PREFS.speed,
    };
}
