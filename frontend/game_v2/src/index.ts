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
    DEFAULT_MOTION_SETTING,
    DEFAULT_SOUND_SETTING,
    type GameSound,
    INPUT_SETTING_KEY,
    MOTION_SETTING_KEY,
    SOUND_SETTING_KEY,
    type SoundCue,
    readInputSetting,
    readMotionSetting,
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
import { applyPageLocale, resolveLocale, t } from "@/shared/i18n";
import {
    type SoundSource,
    blockDownwardDrags,
    createSoundPlayer,
    localStore,
    onScrollSettled,
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
import { type BrowserBars, type GameViewDeps, mountGameView } from "@/views/game";
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

/** The large viewport's height (`100lvh`, what a phone browser leaves once its bars collapse), off a probe of it. */
function largeViewportHeight(): number {
    const probe = document.createElement("div");
    probe.style.cssText =
        "position: fixed; top: 0; left: 0; width: 0; height: 100lvh; visibility: hidden; pointer-events: none;";
    document.body.append(probe);
    const large = probe.offsetHeight;
    probe.remove();
    return large;
}

/** Whether the browser's bars take part of the screen: the viewport stands shorter than the large viewport. */
function browserBarsShown(): boolean {
    return largeViewportHeight() > window.innerHeight + 1;
}

const PAGE_SCROLL_QUIET_MS = 150;

/**
 * Rest the page past the scroll room it keeps beyond the large viewport, so it still scrolls with the bars collapsed
 * and is not at its top, where a phone browser brings them back and the next swipe down reloads the page. The board is
 * sticky and does not move.
 */
function restPagePastItsTop(): void {
    const room = document.body.offsetHeight - largeViewportHeight();
    if (room > 0 && window.scrollY < room) {
        window.scrollTo(0, room);
    }
}

/** Whether a swipe down can reload the page whatever `overscroll-behavior` says: every browser on iOS is WebKit. */
function isIosWebKit(): boolean {
    return CSS.supports("-webkit-touch-callout", "none");
}

function enterFullscreen(): void {
    document.documentElement.requestFullscreen({ navigationUI: "hide" }).catch((error: unknown) => {
        console.warn("The page could not enter full screen:", error);
    });
}

/**
 * The browser's bars over the page, read again as the viewport resizes, which a collapse does. The page rests past its
 * top whenever its body changes height (the first draw, a rotation, leaving full screen), which a collapse does not do,
 * and whenever a scroll settles, which a swipe down leaves at the top.
 */
function browserBars(): BrowserBars {
    return {
        canEnterFullscreen: () => document.fullscreenEnabled === true,
        enterFullscreen,
        shown: browserBarsShown,
        subscribe(listener) {
            function onResize(): void {
                listener(browserBarsShown());
            }
            const pageRest = new ResizeObserver(restPagePastItsTop);
            pageRest.observe(document.body);
            const stopRestingAfterScroll = onScrollSettled(window, {
                clock: browserClock,
                listener: restPagePastItsTop,
                quietMs: PAGE_SCROLL_QUIET_MS,
            });
            const stopBlockingDrags = isIosWebKit() ? blockDownwardDrags(document) : null;
            window.addEventListener("resize", onResize);
            return () => {
                window.removeEventListener("resize", onResize);
                pageRest.disconnect();
                stopRestingAfterScroll();
                stopBlockingDrags?.();
            };
        },
    };
}

function liveGameDeps(gameId: string, tileSprite: TileSprite): GameViewDeps {
    return {
        browserBars: browserBars(),
        clock: browserClock,
        connect: (url, handlers) => new GameSocket(url, handlers),
        debug: isDebugRequested(window.location.search),
        handoff: getGameSession(gameId),
        inputSetting: localStore(INPUT_SETTING_KEY, readInputSetting, DEFAULT_INPUT_SETTING),
        links: {
            history: getLobbyHistoryUrl(),
            replay: (seat) => replayPageUrl(gameId, seat),
        },
        motionSetting: localStore(MOTION_SETTING_KEY, readMotionSetting, DEFAULT_MOTION_SETTING),
        recoverHandoff: fetchGameHandoff,
        setLanguage: applyPageLocale,
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

document.documentElement.lang = resolveLocale(document.cookie, navigator.languages);
document.title = t("game.page.title");

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
