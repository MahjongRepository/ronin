import "./majiang.js";
import "../styles/game-app.scss";

import $ from "jquery";

import { applyStaticText } from "../i18n/index.js";
import { RECOVERY, readGameSession, recoverGameSession } from "./game-session.js";
import { finishLoading, loadTileImages, showLoadingError } from "./loading.js";
import { showReplay } from "./replay/page.js";
import startGame from "./ronin.js";
import { LOBBY_URL, ROUTE, matchRoute } from "./routes.js";
import { showStorybook } from "./storybook.js";

function showSessionProblem(text, ...links) {
    finishLoading();
    $("body")
        .removeClass("board")
        .addClass("page")
        .empty()
        .append($('<p class="missing-session">').append(text, ...links));
}

function lobbyLink() {
    return $("<a>").attr("href", LOBBY_URL).text("ロビーへ");
}

async function findGameSession(gameId) {
    const stored = readGameSession(gameId);
    if (stored) {
        return stored;
    }
    const recovery = await recoverGameSession();
    if (recovery.status === RECOVERY.FAILED) {
        showSessionProblem(
            "セッションを復元できませんでした。",
            $("<a>").attr("href", window.location.href).text("再読み込み"),
            " ",
            lobbyLink(),
        );
        return null;
    }
    if (recovery.status === RECOVERY.MISSING) {
        showSessionProblem("セッションが見つかりません。", lobbyLink());
        return null;
    }
    if (recovery.gameId !== gameId) {
        window.location.replace(recovery.gameUrl);
        return null;
    }
    return recovery.session;
}

async function showGame(gameId) {
    const session = await findGameSession(gameId);
    if (!session) {
        return;
    }
    await loadTileImages();
    startGame(gameId, session);
}

async function showReplayPage(gameId) {
    await showReplay(gameId, loadTileImages());
    finishLoading();
}

async function start() {
    applyStaticText(document);
    const route = matchRoute(window.location.pathname);
    if (!route) {
        window.location.replace(LOBBY_URL);
        return;
    }
    try {
        if (route.name === ROUTE.GAME) {
            await showGame(route.gameId);
        } else if (route.name === ROUTE.REPLAY) {
            await showReplayPage(route.gameId);
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
