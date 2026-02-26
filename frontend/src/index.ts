import "./styles/game-app.scss";
import { cleanupGameView, gameView } from "./views/game";
import { initRouter } from "./router";

const app = document.getElementById("app");
if (app) {
    initRouter(app, [
        {
            cleanup: cleanupGameView,
            handler: (params) => gameView(params.gameId),
            pattern: /^\/game\/(?<gameId>[^/]+)$/,
        },
    ]);
}
