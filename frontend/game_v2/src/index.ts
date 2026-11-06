import "@/zod-setup";
import "@/styles/game-app.scss";
import { render } from "lit-html";

import chiUrl from "@/assets/audio/calls/chi.mp3?no-inline";
import kanUrl from "@/assets/audio/calls/kan.mp3?no-inline";
import ponUrl from "@/assets/audio/calls/pon.mp3?no-inline";
import riichiUrl from "@/assets/audio/calls/riichi.mp3?no-inline";
import ronUrl from "@/assets/audio/calls/ron.mp3?no-inline";
import tsumoUrl from "@/assets/audio/calls/tsumo.mp3?no-inline";
import yakumanUrl from "@/assets/audio/calls/yakuman.mp3?no-inline";
import countdownUrl from "@/assets/audio/countdown-soft-reply.flac?no-inline";
import decisionUrl from "@/assets/audio/decision-radar-reply.flac?no-inline";
import discardUrl from "@/assets/audio/discard-resin.flac?no-inline";
import tileSpriteUrl from "@/assets/tiles/sprites/fluffy-stuff.svg?url";
import {
    DEFAULT_INPUT_SETTING,
    DEFAULT_SOUND_SETTING,
    type GameSound,
    INPUT_SETTING_KEY,
    SOUND_SETTING_KEY,
    type SoundCue,
    readInputSetting,
    readSoundSetting,
} from "@/entities/client";
import { type TileSprite, injectTileSprite, loadTileSprite } from "@/entities/tile";
import { type Route, lazyRoute, startRouter } from "@/router";
import { fetchGameHandoff } from "@/shared/api";
import { browserClock } from "@/shared/clock";
import {
    gamePageUrl,
    getLobbyHistoryUrl,
    getLobbyUrl,
    isDebugRequested,
    replayPageUrl,
} from "@/shared/config";
import {
    type SoundSource,
    createSoundPlayer,
    localStore,
    supportsBoardCss,
    unlockOnGesture,
    webAudioOutput,
} from "@/shared/lib";
import {
    type GameSessionData,
    clearGameSession,
    getGameSession,
    storeGameSession,
} from "@/shared/session";
import { GameSocket } from "@/shared/websocket";
import { type GameViewDeps, mountGameView } from "@/views/game";
import type * as StorybookRoutes from "@/views/storybook-routes";
import { unsupportedBrowserTemplate } from "@/views/unsupported-browser";

const VOICE_VOLUME = 0.2;
const DISCARD_VOLUME = 0.1;
const GAME_SOUNDS: Readonly<Record<SoundCue, SoundSource>> = {
    beep: { kind: "file", url: countdownUrl, volume: VOICE_VOLUME },
    chi: { kind: "file", url: chiUrl, volume: VOICE_VOLUME },
    decision: { kind: "file", url: decisionUrl, volume: VOICE_VOLUME },
    discard: { kind: "file", url: discardUrl, volume: DISCARD_VOLUME },
    kan: { kind: "file", url: kanUrl, volume: VOICE_VOLUME },
    pon: { kind: "file", url: ponUrl, volume: VOICE_VOLUME },
    riichi: { kind: "file", url: riichiUrl, volume: VOICE_VOLUME },
    ron: { kind: "file", url: ronUrl, volume: VOICE_VOLUME },
    tsumo: { kind: "file", url: tsumoUrl, volume: VOICE_VOLUME },
    yakuman: { kind: "file", url: yakumanUrl, volume: VOICE_VOLUME },
};

/**
 * The game's sounds for a page, their audio unlocked inside the page's first gesture (the opening screen's OK, a tap
 * anywhere), as iOS Safari requires, and played only after it.
 */
function gameSound(): GameSound {
    const output = webAudioOutput(navigator.userActivation);
    unlockOnGesture(window, output.unlock);
    const player = createSoundPlayer(GAME_SOUNDS, output, browserClock.now);
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
        inputSetting: localStore(INPUT_SETTING_KEY, readInputSetting, DEFAULT_INPUT_SETTING),
        links: {
            history: getLobbyHistoryUrl(),
            replay: (seat) => replayPageUrl(gameId, seat),
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

/** A storybook page, loaded with the rest of the storybook the first time one is opened. */
function storybookRoute(
    pattern: RegExp,
    pick: (routes: typeof StorybookRoutes) => Route["mount"],
): Route {
    return lazyRoute(pattern, async () => pick(await import("@/views/storybook-routes")));
}

function createStorybookRoutes(): Route[] {
    return [
        lazyRoute(/^\/play\/storybook\/sounds$/, async () => {
            const { mountStorybookSounds } = await import("@/views/storybook-sounds");
            return (host) =>
                mountStorybookSounds(host, {
                    play: gameSound().play,
                    sounds: GAME_SOUNDS,
                });
        }),
        storybookRoute(/^\/play\/storybook\/board$/, (routes) => routes.mountStorybookBoard),
        storybookRoute(
            /^\/play\/storybook\/decisions$/,
            (routes) => routes.mountStorybookDecisions,
        ),
        storybookRoute(/^\/play\/storybook\/discards$/, (routes) => routes.mountStorybookDiscards),
        storybookRoute(/^\/play\/storybook\/hand$/, (routes) => routes.mountStorybookHand),
        storybookRoute(/^\/play\/storybook\/melds$/, (routes) => routes.mountStorybookMelds),
        storybookRoute(/^\/play\/storybook\/replay$/, (routes) => routes.mountStorybookReplay),
        storybookRoute(/^\/play\/storybook\/rotate$/, (routes) => routes.mountStorybookRotate),
        storybookRoute(/^\/play\/storybook$/, (routes) => routes.mountStorybookIndex),
    ];
}

const app = document.getElementById("app");
if (app && !supportsBoardCss()) {
    render(unsupportedBrowserTemplate(getLobbyUrl()), app);
} else if (app) {
    const tileSprite = startTileSprite();
    startRouter(
        app,
        [
            ...(import.meta.env.DEV ? createStorybookRoutes() : []),
            lazyRoute(/^\/play\/history\/(?<gameId>[^/]+)$/, async () => {
                const { mountReplay } = await import("@/replay-entry");
                return (host, params) => mountReplay(host, params.gameId, gameSound());
            }),
            {
                mount: (host, params) =>
                    mountGameView(host, params.gameId, liveGameDeps(params.gameId, tileSprite)),
                pattern: /^\/play\/(?<gameId>[^/]+)$/,
            },
        ],
        leaveToLobby,
    );
}
