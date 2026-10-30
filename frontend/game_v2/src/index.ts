import "@/zod-setup";
import "@/styles/game-app.scss";
import tileSpriteUrl from "@/assets/tiles/sprites/fluffy-stuff.svg?url";
import { type StandingsRenderer, localReplayPrefs, startStandingsLoad } from "@/entities/table";
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
import { type RetryingLoad } from "@/shared/lib";
import {
    type GameSessionData,
    clearGameSession,
    getGameSession,
    storeGameSession,
} from "@/shared/session";
import { GameSocket } from "@/shared/websocket";
import { type GameViewDeps, mountGameView } from "@/views/game";
import type * as StorybookRoutes from "@/views/storybook-routes";

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

function startStandings(): RetryingLoad<StandingsRenderer> {
    return startStandingsLoad({
        onOnline,
        reportFailure: (error) => console.warn("The final standings failed to load:", error),
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
        startStandings,
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
        prefs: localReplayPrefs,
        startStandings,
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
