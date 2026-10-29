import "@/zod-setup";
import "@/styles/game-app.scss";
import { initRouter } from "@/router";
import { cleanupGameView, gameView } from "@/views/game";
import { cleanupReplayView, replayView } from "@/views/replay";
import { storybookView } from "@/views/storybook";
import { storybookBoardView } from "@/views/storybook-board";
import { storybookDiscardsView } from "@/views/storybook-discards";
import { storybookHandView } from "@/views/storybook-hand";
import { storybookMeldsView } from "@/views/storybook-melds";

const app = document.getElementById("app");
if (app) {
    initRouter(app, [
        {
            cleanup: cleanupReplayView,
            handler: (params) => replayView(params.gameId),
            pattern: /^\/play\/history\/(?<gameId>[^/]+)$/,
        },
        {
            handler: () => storybookBoardView(),
            pattern: /^\/play\/storybook\/board$/,
        },
        {
            handler: () => storybookDiscardsView(),
            pattern: /^\/play\/storybook\/discards$/,
        },
        {
            handler: () => storybookHandView(),
            pattern: /^\/play\/storybook\/hand$/,
        },
        {
            handler: () => storybookMeldsView(),
            pattern: /^\/play\/storybook\/melds$/,
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
