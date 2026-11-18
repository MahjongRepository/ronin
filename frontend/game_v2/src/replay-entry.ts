import {
    DEFAULT_MOTION_SETTING,
    type GameSound,
    MOTION_SETTING_KEY,
    readMotionSetting,
} from "@/entities/client";
import { DEFAULT_REPLAY_PREFS, readReplayPrefs } from "@/entities/replay";
import { applyTileLabels } from "@/entities/tile";
import { fetchReplay } from "@/shared/api";
import { browserClock } from "@/shared/clock";
import { getLobbyHistoryUrl, getLobbyUrl } from "@/shared/config";
import { applyPageLocale, applyWindScript } from "@/shared/i18n";
import { localStore, shortcutKeysOf } from "@/shared/lib";
import { mountReplayView } from "@/views/replay";

const REPLAY_PREFS_KEY = "ronin.v2.replay-prefs";

function replaceSearch(search: string): void {
    const { hash, pathname } = window.location;
    window.history.replaceState(window.history.state, "", `${pathname}${search}${hash}`);
}

/** Call `listener` as the page is hidden or left, when a waiting address write must land. */
function onPageHide(listener: () => void): () => void {
    function onHidden(): void {
        if (document.visibilityState === "hidden") {
            listener();
        }
    }
    window.addEventListener("pagehide", listener);
    document.addEventListener("visibilitychange", onHidden);
    return () => {
        window.removeEventListener("pagehide", listener);
        document.removeEventListener("visibilitychange", onHidden);
    };
}

/** What the page's entry hands the replay: the game's sounds, and the rest that lets a swipe collapse a phone's bars. */
export interface ReplayPage {
    readonly sound: GameSound;
    /** Keep the page resting past its top while the replay is mounted; returns its stop. */
    readonly keepPageRested: () => () => void;
}

export function mountReplay(host: HTMLElement, gameId: string, page: ReplayPage): () => void {
    const stopRestingPage = page.keepPageRested();
    const dispose = mountReplayView(host, gameId, {
        clock: browserClock,
        copyText: (text) => navigator.clipboard.writeText(text),
        links: { history: getLobbyHistoryUrl(), lobby: getLobbyUrl() },
        loadReplay: fetchReplay,
        location: { onPageHide, replaceSearch, search: window.location.search },
        motionSetting: localStore(MOTION_SETTING_KEY, readMotionSetting, DEFAULT_MOTION_SETTING),
        openUrl: (url) => {
            window.open(url, "_blank", "noopener");
        },
        prefersReducedMotion: () => matchMedia("(prefers-reduced-motion: reduce)").matches,
        prefs: localStore(REPLAY_PREFS_KEY, readReplayPrefs, DEFAULT_REPLAY_PREFS),
        setLanguage: applyPageLocale,
        setTileLabels: applyTileLabels,
        setWinds: applyWindScript,
        shortcuts: shortcutKeysOf(navigator.userAgent),
        sound: page.sound,
    });
    return () => {
        dispose();
        stopRestingPage();
    };
}
