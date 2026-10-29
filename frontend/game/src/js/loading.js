import { t } from "../i18n/index.js";

export async function loadTileImages() {
    await Promise.all(
        [...document.querySelectorAll("#loaddata img")].map((image) => image.decode()),
    );
}

export function finishLoading() {
    document.documentElement.classList.remove("loading");
    document.getElementById("game-loading")?.remove();
}

/** Replace the loading screen's status line with `text`. */
export function showLoadingStatus(text) {
    const status = document.querySelector("#game-loading [role=status]");
    if (status) {
        status.textContent = text;
    }
}

export function showLoadingError() {
    showLoadingStatus(t("loading.error"));
    document.querySelector("#game-loading .loading-dots")?.remove();
}
