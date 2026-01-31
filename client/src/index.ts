import { initRouter } from "./router";
import { lobbyView } from "./views/lobby";
import { gameView, cleanupGameView } from "./views/game";

const app = document.getElementById("app");
if (app) {
    initRouter(app, [
        { pattern: /^\/$/, handler: () => lobbyView() },
        {
            pattern: /^\/game\/(?<gameId>[^/]+)$/,
            handler: (p) => gameView(p.gameId),
            cleanup: cleanupGameView,
        },
    ]);
}
