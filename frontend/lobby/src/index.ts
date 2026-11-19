import "@/styles/lobby-app.scss";
import { startLobbyApp } from "@/app/start";
import { showUnsupportedBrowserNotice } from "@/browser-support";

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
    showUnsupportedBrowserNotice();
    dropNoticeParam();
}

const spaHost = document.getElementById("lobby-spa");
if (spaHost) {
    startLobbyApp(spaHost);
} else {
    bootJinjaPage();
}
