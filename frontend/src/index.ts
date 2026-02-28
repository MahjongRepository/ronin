import "@/styles/game-app.scss";
import { cleanupGameView, gameView } from "@/views/game";
import { cleanupReplayView, replayView } from "@/views/replay";
import { initRouter } from "@/router";
import { storybookView } from "@/views/storybook";

const app = document.getElementById("app");
if (app) {
    initRouter(app, [
        {
            cleanup: cleanupReplayView,
            handler: (params) => replayView(params.gameId),
            pattern: /^\/play\/history\/(?<gameId>[^/]+)$/,
        },
        {
            handler: () => storybookView(),
            pattern: /^\/play\/storybook$/,
        },
        {
            cleanup: cleanupGameView,
            handler: (params) => gameView(params.gameId),
            pattern: /^\/play\/(?<gameId>[^/]+)$/,
        },
    ]);
}
