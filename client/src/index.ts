import { cleanupGameView, gameView } from "./views/game";
import { initRouter } from "./router";
import { lobbyView } from "./views/lobby";

const app = document.getElementById("app");
if (app) {
    initRouter(app, [
        { handler: () => lobbyView(), pattern: /^\/$/ },
        {
            cleanup: cleanupGameView,
            handler: (params) => gameView(params.gameId),
            pattern: /^\/game\/(?<gameId>[^/]+)$/,
        },
    ]);
}
