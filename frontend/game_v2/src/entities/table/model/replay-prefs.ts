import { type AutoplaySpeed, autoplaySpeedOf } from "./replay-autoplay";

/** A reader's own replay settings, kept across replays: whether the other hands hide, and autoplay's speed. */
export interface ReplayPrefs {
    readonly hideHands: boolean;
    readonly speed: AutoplaySpeed;
}

/** Where a replay view keeps its reader's settings. */
export interface ReplayPrefsStore {
    readonly load: () => ReplayPrefs;
    readonly save: (prefs: ReplayPrefs) => void;
}

export const DEFAULT_REPLAY_PREFS: ReplayPrefs = { hideHands: false, speed: 1 };

const STORAGE_KEY = "ronin.v2.replay-prefs";

function parseReplayPrefs(raw: string | null): ReplayPrefs {
    const parsed: unknown = raw === null ? null : JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) {
        return DEFAULT_REPLAY_PREFS;
    }
    const { hideHands, speed } = { ...DEFAULT_REPLAY_PREFS, ...parsed };
    return {
        hideHands: typeof hideHands === "boolean" ? hideHands : DEFAULT_REPLAY_PREFS.hideHands,
        speed: typeof speed === "number" ? autoplaySpeedOf(speed) : DEFAULT_REPLAY_PREFS.speed,
    };
}

/**
 * The reader's settings in `localStorage`, a convenience of this browser: storage that is blocked, full or holds
 * something unreadable gives the defaults and keeps nothing, and the page works the same without it.
 */
export const localReplayPrefs: ReplayPrefsStore = {
    load: () => {
        try {
            return parseReplayPrefs(localStorage.getItem(STORAGE_KEY));
        } catch {
            return DEFAULT_REPLAY_PREFS;
        }
    },
    save: (prefs) => {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
        } catch {
            return;
        }
    },
};
