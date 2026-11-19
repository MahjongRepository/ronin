import "@/styles/lobby-app.scss";
import { startLobbyApp } from "@/app/start";
import { showUnsupportedBrowserNotice } from "@/browser-support";
import { initGamesCopyLinkButtons, showGameTimesInLocalTime } from "@/games-history";
import { initMatchmakingPage } from "@/matchmaking";
import { initRoomPage } from "@/room";

if (import.meta.env.DEV) {
    void import("@/styles/development.scss");
}

function dropNoticeParam(): void {
    const pageUrl = new URL(window.location.href);
    if (pageUrl.searchParams.has("notice")) {
        pageUrl.searchParams.delete("notice");
        window.history.replaceState(window.history.state, "", pageUrl);
    }
}

function bootJinjaPage(): void {
    const roomContainer = document.getElementById("room-app");
    if (roomContainer) {
        initRoomPage(roomContainer);
    }

    const matchmakingContainer = document.getElementById("matchmaking-app");
    if (matchmakingContainer) {
        initMatchmakingPage(matchmakingContainer);
    }

    showUnsupportedBrowserNotice();
    initGamesCopyLinkButtons();
    showGameTimesInLocalTime();
    dropNoticeParam();
}

const spaHost = document.getElementById("lobby-spa");
if (spaHost) {
    startLobbyApp(spaHost);
} else {
    bootJinjaPage();
}
