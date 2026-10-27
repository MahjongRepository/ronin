import $ from "jquery";

import { GAME_PREF_KEY } from "../game-prefs.js";
import { HISTORY_URL, LOBBY_URL } from "../routes.js";
import { REPLAY_ERROR, loadReplay } from "./load.js";
import { ReplayControls } from "./controls.js";
import { MalformedReplayError, toReplay } from "./paipu.js";
import { ReplayViewer } from "./viewer.js";

const PAGE_TITLE = "Replay · Ronin";

const ERROR_TEXT = Object.freeze({
    [REPLAY_ERROR.NOT_FOUND]: "Replay not found",
    [REPLAY_ERROR.VERSION]: "This replay was recorded by another version of Ronin",
    [REPLAY_ERROR.FAILED]: "Couldn't load the replay",
    [REPLAY_ERROR.MALFORMED]: "This replay file is damaged",
});

const NO_ROUNDS = "This game ended before its first deal: there is nothing to replay";

function errorText({ kind, line }) {
    return line === undefined ? ERROR_TEXT[kind] : `${ERROR_TEXT[kind]} (line ${line})`;
}

/** Replace the board with a message and the ways back to the lobby, and a retry where one may help. */
function showProblem(text, { retry = false } = {}) {
    const links = $('<p class="replay-problem-links">').append(
        retry ? $("<a>").attr("href", window.location.href).text("Try again") : null,
        $("<a>").attr("href", HISTORY_URL).text("Game history"),
        $("<a>").attr("href", LOBBY_URL).text("Lobby"),
    );
    $("body")
        .removeClass("board")
        .addClass("page")
        .empty()
        .append($('<main class="replay-problem" lang="en">').append($("<h1>").text(text), links));
}

function showDamaged(line, ...logged) {
    console.error("[ronin] replay cannot be shown:", ...logged);
    showProblem(errorText({ kind: REPLAY_ERROR.MALFORMED, line }));
}

/** The converted replay, or null once its problem is shown. */
async function readReplay(gameId) {
    const loaded = await loadReplay(gameId);
    if (loaded.error) {
        showProblem(errorText(loaded.error), {
            retry: loaded.error.kind === REPLAY_ERROR.FAILED,
        });
        return null;
    }
    let replay;
    try {
        replay = toReplay(loaded);
    } catch (error) {
        if (!(error instanceof MalformedReplayError)) {
            throw error;
        }
        showDamaged(error.line, error, error.cause);
        return null;
    }
    if (replay.rounds.length === 0) {
        showProblem(NO_ROUNDS);
        return null;
    }
    return replay;
}

/** Refit the table whenever the page's layout resizes the stage, the first layout included. */
function fitTableToStage(stage) {
    const fit = () => Majiang.UI.Util.fitToStage(stage);
    new ResizeObserver(fit).observe(stage[0]);
}

/** The board drawing the replay: every hand open, from the recorded first dealer's seat, with the sound setting. */
function buildBoard(replay, stage) {
    const pai = Majiang.UI.pai($("#loaddata"));
    const audio = Majiang.UI.audio($("#loaddata"));
    const model = new Majiang.Board({
        title: "",
        player: [...replay.players],
        qijia: replay.qijia,
    });
    const root = $("> .board", stage);
    const view = new Majiang.UI.Board(root, pai, audio, model);
    view.viewpoint = replay.qijia;
    view.open_shoupai = true;
    new Majiang.UI.GameCtl(stage, GAME_PREF_KEY, view);
    $(".autoplay, .player-button, .timer", stage).remove();
    return { model, view, root };
}

function startViewer(replay) {
    const stage = $("#board");
    const { model, view, root } = buildBoard(replay, stage);
    const controls = new ReplayControls(replay);
    $("#space").remove();
    $("body").addClass("replay").append(controls.element);
    const viewer = new ReplayViewer({
        replay,
        view,
        model,
        root,
        onChange: (state) => controls.show(state),
    });
    controls.bind(viewer);
    viewer.start();
    fitTableToStage(stage);
}

/**
 * Show a game's replay on the board at its deal, with its control strip, or say why it cannot be shown. The replay loads
 * while `tilesLoaded` (the tile images' decoding) runs; only the board waits for it.
 */
export async function showReplay(gameId, tilesLoaded) {
    document.title = PAGE_TITLE;
    const replay = await readReplay(gameId);
    if (replay === null) {
        return;
    }
    await tilesLoaded;
    try {
        startViewer(replay);
    } catch (error) {
        showDamaged(undefined, error);
    }
}
