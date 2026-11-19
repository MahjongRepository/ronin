import "@/styles/lobby-app.scss";
import { startLobbyApp, startRetainedPage } from "@/app/start";

if (import.meta.env.DEV) {
    void import("@/styles/development.scss");
}

const spaHost = document.getElementById("lobby-spa");
if (spaHost) {
    startLobbyApp(spaHost);
} else {
    startRetainedPage();
}
