import "@/zod-setup";
import "@/styles/game-app.scss";
import { startRouter, staticRoute } from "@/router";
import { fetchReplay } from "@/shared/api";
import { browserClock } from "@/shared/clock";
import { getLobbyUrl } from "@/shared/config";
import { clearSessionData, getGameSession } from "@/shared/session";
import { GameSocket } from "@/shared/websocket";
import { type GameViewDeps, mountGameView } from "@/views/game";
import { mountReplayView } from "@/views/replay";
import { storybookView } from "@/views/storybook";
import { mountStorybookBoard } from "@/views/storybook-board";
import { storybookDiscardsView } from "@/views/storybook-discards";
import { storybookHandView } from "@/views/storybook-hand";
import { storybookMeldsView } from "@/views/storybook-melds";
import { mountStorybookRotate } from "@/views/storybook-rotate";

function leaveToLobby(): void {
    window.location.replace(getLobbyUrl());
}

function liveGameDeps(gameId: string): GameViewDeps {
    return {
        clock: browserClock,
        connect: (url, handlers) => new GameSocket(url, handlers),
        handoff: getGameSession(gameId),
        sink: { clearHandoff: clearSessionData, leaveToLobby },
    };
}

const app = document.getElementById("app");
if (app) {
    startRouter(
        app,
        [
            {
                mount: (host, params) =>
                    mountReplayView(host, params.gameId, { loadReplay: fetchReplay }),
                pattern: /^\/play\/history\/(?<gameId>[^/]+)$/,
            },
            { mount: mountStorybookBoard, pattern: /^\/play\/storybook\/board$/ },
            staticRoute(/^\/play\/storybook\/discards$/, storybookDiscardsView),
            staticRoute(/^\/play\/storybook\/hand$/, storybookHandView),
            staticRoute(/^\/play\/storybook\/melds$/, storybookMeldsView),
            { mount: mountStorybookRotate, pattern: /^\/play\/storybook\/rotate$/ },
            staticRoute(/^\/play\/storybook$/, storybookView),
            {
                mount: (host, params) =>
                    mountGameView(host, params.gameId, liveGameDeps(params.gameId)),
                pattern: /^\/play\/(?<gameId>[^/]+)$/,
            },
        ],
        leaveToLobby,
    );
}
