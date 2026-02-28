import "@/styles/lobby-app.scss";
import { initGamesCopyLinkButtons } from "@/lobby/games-history";
import { initRoomPage } from "@/lobby/room";

const roomContainer = document.getElementById("room-app");
if (roomContainer) {
    const roomId = roomContainer.dataset.roomId ?? "";
    const wsUrl = roomContainer.dataset.wsUrl ?? "";

    if (roomId && wsUrl) {
        initRoomPage({ roomId, wsUrl });
    }
}

initGamesCopyLinkButtons();
