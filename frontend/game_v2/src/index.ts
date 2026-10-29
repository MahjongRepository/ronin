import "@/zod-setup";
import "@/styles/game-app.scss";
import { type Route, lazyRoute, startRouter } from "@/router";
import { fetchGameHandoff, fetchReplay } from "@/shared/api";
import { browserClock } from "@/shared/clock";
import { gamePageUrl, getLobbyUrl, isDebugRequested } from "@/shared/config";
import {
    type GameSessionData,
    clearSessionData,
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

function liveGameDeps(gameId: string): GameViewDeps {
    return {
        clock: browserClock,
        connect: (url, handlers) => new GameSocket(url, handlers),
        debug: isDebugRequested(window.location.search),
        handoff: getGameSession(gameId),
        recoverHandoff: fetchGameHandoff,
        sink: {
            clearHandoff: clearSessionData,
            leaveToLobby,
            openGame,
            reload: () => window.location.reload(),
            storeHandoff,
        },
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
    startRouter(
        app,
        [
            lazyRoute(/^\/play\/history\/(?<gameId>[^/]+)$/, async () => {
                const { mountReplayView } = await import("@/views/replay");
                return (host, params) =>
                    mountReplayView(host, params.gameId, { loadReplay: fetchReplay });
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
            storybookRoute(/^\/play\/storybook\/rotate$/, (routes) => routes.mountStorybookRotate),
            storybookRoute(/^\/play\/storybook$/, (routes) => routes.mountStorybookIndex),
            {
                mount: (host, params) =>
                    mountGameView(host, params.gameId, liveGameDeps(params.gameId)),
                pattern: /^\/play\/(?<gameId>[^/]+)$/,
            },
        ],
        leaveToLobby,
    );
}
