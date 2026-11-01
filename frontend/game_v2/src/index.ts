import "@/zod-setup";
import "@/styles/game-app.scss";
import beepUrl from "@/assets/audio/beep.wav?url";
import chiUrl from "@/assets/audio/chii.wav?url";
import discardUrl from "@/assets/audio/dahai11.wav?url";
import kanUrl from "@/assets/audio/kan.wav?url";
import yakumanUrl from "@/assets/audio/nc43994.wav?url";
import ponUrl from "@/assets/audio/pon.wav?url";
import riichiUrl from "@/assets/audio/richi.wav?url";
import ronUrl from "@/assets/audio/ron.wav?url";
import tsumoUrl from "@/assets/audio/tsumo.wav?url";
import tileSpriteUrl from "@/assets/tiles/sprites/fluffy-stuff.svg?url";
import {
    DEFAULT_SOUND_SETTING,
    type GameSound,
    SOUND_SETTING_KEY,
    type SoundCue,
    readSoundSetting,
} from "@/entities/client";
import { DEFAULT_REPLAY_PREFS, readReplayPrefs } from "@/entities/replay";
import { type TileSprite, injectTileSprite, loadTileSprite } from "@/entities/tile";
import { type Route, lazyRoute, startRouter } from "@/router";
import { fetchGameHandoff, fetchReplay } from "@/shared/api";
import { browserClock } from "@/shared/clock";
import {
    gamePageUrl,
    getLobbyHistoryUrl,
    getLobbyUrl,
    isDebugRequested,
    replayPageUrl,
} from "@/shared/config";
import { type SoundSource, createSoundPlayer, localStore, webAudioOutput } from "@/shared/lib";
import {
    type GameSessionData,
    clearGameSession,
    getGameSession,
    storeGameSession,
} from "@/shared/session";
import { GameSocket } from "@/shared/websocket";
import { type GameViewDeps, mountGameView } from "@/views/game";
import type * as StorybookRoutes from "@/views/storybook-routes";

/** Where this browser keeps the replay reader's settings. */
const REPLAY_PREFS_KEY = "ronin.v2.replay-prefs";

/** The v1 client's sounds at its volumes: the voices and clicks quiet, the yakuman gong full. */
const VOICE_VOLUME = 0.2;
const GAME_SOUNDS: Readonly<Record<SoundCue, SoundSource>> = {
    beep: { url: beepUrl, volume: VOICE_VOLUME },
    chi: { url: chiUrl, volume: VOICE_VOLUME },
    discard: { url: discardUrl, volume: VOICE_VOLUME },
    kan: { url: kanUrl, volume: VOICE_VOLUME },
    pon: { url: ponUrl, volume: VOICE_VOLUME },
    riichi: { url: riichiUrl, volume: VOICE_VOLUME },
    ron: { url: ronUrl, volume: VOICE_VOLUME },
    tsumo: { url: tsumoUrl, volume: VOICE_VOLUME },
    yakuman: { url: yakumanUrl, volume: 1 },
};

function gameSound(): GameSound {
    const output = webAudioOutput(() => navigator.userActivation.hasBeenActive);
    const player = createSoundPlayer(GAME_SOUNDS, output);
    return {
        play: player.play,
        setting: localStore(SOUND_SETTING_KEY, readSoundSetting, DEFAULT_SOUND_SETTING),
    };
}

function leaveToLobby(): void {
    window.location.replace(getLobbyUrl());
}

/** Keep a recovered handoff for a reload, as the lobby would have; storage that refuses it only costs a refetch. */
function storeHandoff(gameId: string, handoff: GameSessionData): void {
    try {
        storeGameSession(gameId, handoff.wsUrl, handoff.gameTicket);
    } catch (error: unknown) {
        console.warn("The recovered game session holds for this page only:", error);
    }
}

function openGame(gameId: string, gameClientUrl: string): void {
    window.location.replace(gamePageUrl(gameClientUrl, gameId, window.location.search));
}

async function fetchTileSprite(): Promise<string> {
    const response = await fetch(tileSpriteUrl);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    return response.text();
}

function onOnline(listener: () => void): () => void {
    window.addEventListener("online", listener);
    return () => window.removeEventListener("online", listener);
}

function startTileSprite(): TileSprite {
    return loadTileSprite({
        fetchSprite: fetchTileSprite,
        inject: injectTileSprite,
        onOnline,
        reportFailure: (error) => console.warn("The tile sprite failed to load:", error),
        setTimer: browserClock.setTimer,
    });
}

function liveGameDeps(gameId: string, tileSprite: TileSprite): GameViewDeps {
    return {
        clock: browserClock,
        connect: (url, handlers) => new GameSocket(url, handlers),
        debug: isDebugRequested(window.location.search),
        handoff: getGameSession(gameId),
        links: {
            history: getLobbyHistoryUrl(),
            replay: (seat) => replayPageUrl(gameId, seat, window.location.search),
        },
        recoverHandoff: fetchGameHandoff,
        sink: {
            clearHandoff: clearGameSession,
            leaveToLobby,
            openGame,
            reload: () => window.location.reload(),
            storeHandoff,
        },
        sound: gameSound(),
        tileSprite,
    };
}

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

function replayDeps() {
    return {
        clock: browserClock,
        links: { history: getLobbyHistoryUrl(), lobby: getLobbyUrl() },
        loadReplay: fetchReplay,
        location: { onPageHide, replaceSearch, search: window.location.search },
        prefs: localStore(REPLAY_PREFS_KEY, readReplayPrefs, DEFAULT_REPLAY_PREFS),
        sound: gameSound(),
    };
}

/** A storybook page, loaded with the rest of the storybook the first time one is opened. */
function storybookRoute(
    pattern: RegExp,
    pick: (routes: typeof StorybookRoutes) => Route["mount"],
): Route {
    return lazyRoute(pattern, async () => pick(await import("@/views/storybook-routes")));
}

const app = document.getElementById("app");
if (app) {
    const tileSprite = startTileSprite();
    startRouter(
        app,
        [
            lazyRoute(/^\/play\/history\/(?<gameId>[^/]+)$/, async () => {
                const { mountReplayView } = await import("@/views/replay");
                return (host, params) => mountReplayView(host, params.gameId, replayDeps());
            }),
            storybookRoute(/^\/play\/storybook\/board$/, (routes) => routes.mountStorybookBoard),
            storybookRoute(
                /^\/play\/storybook\/decisions$/,
                (routes) => routes.mountStorybookDecisions,
            ),
            storybookRoute(
                /^\/play\/storybook\/discards$/,
                (routes) => routes.mountStorybookDiscards,
            ),
            storybookRoute(/^\/play\/storybook\/hand$/, (routes) => routes.mountStorybookHand),
            storybookRoute(/^\/play\/storybook\/melds$/, (routes) => routes.mountStorybookMelds),
            storybookRoute(/^\/play\/storybook\/replay$/, (routes) => routes.mountStorybookReplay),
            storybookRoute(/^\/play\/storybook\/rotate$/, (routes) => routes.mountStorybookRotate),
            storybookRoute(/^\/play\/storybook$/, (routes) => routes.mountStorybookIndex),
            {
                mount: (host, params) =>
                    mountGameView(host, params.gameId, liveGameDeps(params.gameId, tileSprite)),
                pattern: /^\/play\/(?<gameId>[^/]+)$/,
            },
        ],
        leaveToLobby,
    );
}
