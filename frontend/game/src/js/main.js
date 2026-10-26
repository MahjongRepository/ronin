import "./majiang.js";
import "../css/index.styl";
import "../css/pages.styl";

import $ from "jquery";

import { readGameSession } from "./game-session.js";
import { finishLoading, loadTileImages, showLoadingError } from "./loading.js";
import { showReplay } from "./replay.js";
import startGame from "./ronin.js";
import { ROUTE, matchRoute } from "./routes.js";
import { showStorybook } from "./storybook.js";

const LOBBY_URL = "/";

function showMissingSession() {
    finishLoading();
    $("body")
        .removeClass("board")
        .addClass("page")
        .empty()
        .append(
            $('<p class="missing-session">').append(
                "セッションが見つかりません。",
                $("<a>").attr("href", LOBBY_URL).text("ロビーへ"),
            ),
        );
}

async function showGame(gameId) {
    const session = readGameSession(gameId);
    if (!session) {
        showMissingSession();
        return;
    }
    await loadTileImages();
    startGame(gameId, session);
}

function showReplayPage(gameId) {
    finishLoading();
    const root = $('<main class="replay">');
    $("body").removeClass("board").addClass("page").empty().append(root);
    showReplay(root[0], gameId);
}

async function start() {
    const route = matchRoute(window.location.pathname);
    if (!route) {
        window.location.replace(LOBBY_URL);
        return;
    }
    try {
        if (route.name === ROUTE.GAME) {
            await showGame(route.gameId);
        } else if (route.name === ROUTE.REPLAY) {
            showReplayPage(route.gameId);
        } else {
            await loadTileImages();
            showStorybook(route.page);
            finishLoading();
        }
    } catch (error) {
        console.error("[ronin] startup failed:", error);
        showLoadingError();
    }
}

$(start);
