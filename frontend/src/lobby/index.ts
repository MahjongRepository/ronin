import "../styles/lobby-app.scss";
import { initGamesCopyLinkButtons } from "./games-history";
import { initRoomPage } from "./room";

const roomContainer = document.getElementById("room-app");
if (roomContainer) {
    const roomId = roomContainer.dataset.roomId ?? "";
    const wsUrl = roomContainer.dataset.wsUrl ?? "";

    if (roomId && wsUrl) {
        initRoomPage({ roomId, wsUrl });
    }
}

initGamesCopyLinkButtons();
