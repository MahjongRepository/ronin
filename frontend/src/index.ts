import { cleanupGameView, gameView } from "./views/game";
import { cleanupRoomView, roomView } from "./views/room";
import { initRouter } from "./router";

const app = document.getElementById("app");
if (app) {
    initRouter(app, [
        {
            cleanup: cleanupRoomView,
            handler: (params) => roomView(params.roomId),
            pattern: /^\/room\/(?<roomId>[^/]+)$/,
        },
        {
            cleanup: cleanupGameView,
            handler: (params) => gameView(params.gameId),
            pattern: /^\/game\/(?<gameId>[^/]+)$/,
        },
    ]);
}
