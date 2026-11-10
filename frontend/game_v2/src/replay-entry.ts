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
import { localStore } from "@/shared/lib";
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

export function mountReplay(host: HTMLElement, gameId: string, sound: GameSound): () => void {
    return mountReplayView(host, gameId, {
        clock: browserClock,
        links: { history: getLobbyHistoryUrl(), lobby: getLobbyUrl() },
        loadReplay: fetchReplay,
        location: { onPageHide, replaceSearch, search: window.location.search },
        motionSetting: localStore(MOTION_SETTING_KEY, readMotionSetting, DEFAULT_MOTION_SETTING),
        prefs: localStore(REPLAY_PREFS_KEY, readReplayPrefs, DEFAULT_REPLAY_PREFS),
        setLanguage: applyPageLocale,
        setTileLabels: applyTileLabels,
        setWinds: applyWindScript,
        sound,
    });
}
