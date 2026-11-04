import "@/styles/lobby-app.scss";
import { initGamesCopyLinkButtons, showGameTimesInLocalTime } from "@/games-history";
import { initMatchmakingPage } from "@/matchmaking";
import { initRoomPage } from "@/room";

if (import.meta.env.DEV) {
    void import("@/styles/development.scss");
}

const roomContainer = document.getElementById("room-app");
if (roomContainer) {
    initRoomPage(roomContainer);
}

const matchmakingContainer = document.getElementById("matchmaking-app");
if (matchmakingContainer) {
    initMatchmakingPage(matchmakingContainer);
}

initGamesCopyLinkButtons();
showGameTimesInLocalTime();

const pageUrl = new URL(window.location.href);
if (pageUrl.searchParams.has("notice")) {
    pageUrl.searchParams.delete("notice");
    window.history.replaceState(window.history.state, "", pageUrl);
}
