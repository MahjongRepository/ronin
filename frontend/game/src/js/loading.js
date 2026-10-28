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

/**
 * Turn the loading screen into a gate: `text` in its status line and a focused OK button in its dots' place, resolving
 * once pressed. The press is the page's first user activation, without which the browser refuses its sounds.
 */
export function waitForStart(text) {
    showLoadingStatus(text);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "loading-start";
    button.textContent = t("loading.start");
    document.querySelector("#game-loading .loading-dots").replaceWith(button);
    button.focus();
    return new Promise((resolve) => {
        button.addEventListener("click", resolve, { once: true });
    });
}

export function showLoadingError() {
    showLoadingStatus(t("loading.error"));
    document.querySelector("#game-loading .loading-dots")?.remove();
}
