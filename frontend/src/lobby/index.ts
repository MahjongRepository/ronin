import "@/styles/lobby-app.scss";
import { initGamesCopyLinkButtons } from "@/lobby/games-history";
import { initMatchmakingPage } from "@/lobby/matchmaking";
import { initRoomPage } from "@/lobby/room";

const roomContainer = document.getElementById("room-app");
if (roomContainer) {
    const roomId = roomContainer.dataset.roomId ?? "";
    const wsUrl = roomContainer.dataset.wsUrl ?? "";

    if (roomId && wsUrl) {
        initRoomPage({ roomId, wsUrl });
    }
}

const matchmakingContainer = document.getElementById("matchmaking-app");
if (matchmakingContainer) {
    const wsUrl = matchmakingContainer.dataset.wsUrl ?? "";
    if (wsUrl) {
        initMatchmakingPage(wsUrl);
    }
}

initGamesCopyLinkButtons();
