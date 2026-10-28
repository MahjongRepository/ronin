import $ from "jquery";

import { t } from "../../i18n/index.js";
import { withoutBlockedPlayback } from "../game-audio.js";
import { GAME_PREF_KEY } from "../game-prefs.js";
import { showLoadingStatus, waitForStart } from "../loading.js";
import { HISTORY_URL, LOBBY_URL, replayPath } from "../routes.js";
import { BoardLinks } from "./board-links.js";
import { REPLAY_ERROR, loadReplay } from "./load.js";
import { ReplayControls } from "./controls.js";
import { bindKeys, unbindKeys } from "./keys.js";
import { MalformedReplayError, toReplay } from "./paipu.js";
import { PositionUrl, readPosition } from "./position-url.js";
import { readReplayPrefs } from "./prefs.js";
import { ReplayViewer, UnplayableReplayError } from "./viewer.js";
import { bindWheel } from "./wheel.js";

/** Each way a replay fails to load, by catalog key. */
const ERROR_KEYS = Object.freeze({
    [REPLAY_ERROR.NOT_FOUND]: "replay.error.not_found",
    [REPLAY_ERROR.VERSION]: "replay.error.version",
    [REPLAY_ERROR.FAILED]: "replay.error.failed",
    [REPLAY_ERROR.MALFORMED]: "replay.error.malformed",
});

function errorText({ kind, line }) {
    const error = t(ERROR_KEYS[kind]);
    return line === undefined ? error : t("replay.error.with_line", { error, line: String(line) });
}

/**
 * Replace the page with a message and the ways back to the lobby, and the retries where they may help: the page again,
 * and `startOver` (the replay from its start) where reloading the position shown may fail the same way. It takes the
 * loading screen's layout, its status line the message and its link the ways out, so a load that waited on the replay
 * turns into its problem in place.
 */
function showProblem(text, { retry = false, startOver = null } = {}) {
    const links = $('<p class="replay-problem-links">').append(
        retry
            ? $("<a>").attr("href", window.location.href).text(t("replay.problem.try_again"))
            : null,
        startOver === null
            ? null
            : $("<a>").attr("href", startOver).text(t("replay.problem.start_over")),
        $("<a>").attr("href", HISTORY_URL).text(t("replay.problem.history")),
        $("<a>").attr("href", LOBBY_URL).text(t("replay.problem.lobby")),
    );
    $("body")
        .removeClass("board")
        .empty()
        .append(
            $('<main class="game-loading replay-problem">').append(
                $('<div class="loading-brand">').text("RONIN"),
                $('<div class="loading-mark" aria-hidden="true">').text("東"),
                $("<h1>").text(text),
                links,
            ),
        );
}

function showDamaged(line, ...logged) {
    console.error("[ronin] replay cannot be shown:", ...logged);
    showProblem(errorText({ kind: REPLAY_ERROR.MALFORMED, line }));
}

/**
 * A replay the model cannot play is damaged; any other failure to show one is the page's own, which a reload may fix.
 * A failure at a position past the first deal may be that position's alone, so the replay from its start, from the same
 * seat, is offered too. Either way the replay's keys stop: the page shows the problem instead.
 */
function showViewerFailure(error, gameId, replay) {
    unbindKeys();
    if (error instanceof UnplayableReplayError) {
        showDamaged(undefined, error, error.cause);
        return;
    }
    console.error("[ronin] replay cannot be shown:", error);
    const { seat, round, step } = readPosition(window.location.search, replay);
    const atStart = round === 0 && step === 0;
    showProblem(t("replay.error.cannot_show"), {
        retry: true,
        startOver: atStart ? null : replayPath(gameId, seat),
    });
}

/** The converted replay, or null once its problem is shown. */
async function readReplay(gameId) {
    const loaded = await loadReplay(gameId, {
        onWait: () => showLoadingStatus(t("replay.loading.waiting")),
    });
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
        showProblem(t("replay.error.no_rounds"));
        return null;
    }
    return replay;
}

/** Refit the table whenever the page's layout resizes the stage, the first layout included. */
function fitTableToStage(stage) {
    const fit = () => Majiang.UI.Util.fitToStage(stage);
    new ResizeObserver(fit).observe(stage[0]);
}

/**
 * The settings gear with its sound switch, whose setting the live game shares, and Escape closing its menu. The live
 * game's sound key stays off: the replay's keys are its own.
 */
class ReplaySettings extends Majiang.UI.GameCtl {
    set_sound_key() {}
}

/**
 * The board drawing the replay from `seat`, every hand open unless the viewer chose to hide opponents' hands, with the
 * sound setting; a sound the browser blocks before the first gesture is skipped.
 */
function buildBoard(replay, stage, prefs, seat) {
    const pai = Majiang.UI.pai($("#loaddata"));
    const audio = withoutBlockedPlayback(Majiang.UI.audio($("#loaddata")));
    const model = new Majiang.Board({
        title: "",
        player: [...replay.players],
        qijia: replay.qijia,
    });
    const root = $("> .board", stage);
    const view = new Majiang.UI.Board(root, pai, audio, model);
    view.viewpoint = seat;
    view.open_shoupai = !prefs.hideHands;
    const settings = new ReplaySettings(stage, GAME_PREF_KEY, view);
    $(".controller .sound", stage)
        .removeAttr("data-i18n-title")
        .attr("title", t("game.settings.sound"));
    $(".autoplay, .player-button, .timer", stage).remove();
    return { model, view, root, settings };
}

/**
 * The viewer at the seat and position the address bar names (by default the recorded first dealer's seat at the first
 * deal), paused, the address bar then following every move and change of seat.
 */
function startViewer(gameId, replay) {
    const stage = $("#board");
    const prefs = readReplayPrefs();
    const { seat, round, step } = readPosition(window.location.search, replay);
    const { model, view, root, settings } = buildBoard(replay, stage, prefs, seat);
    const positionUrl = new PositionUrl();
    const controls = new ReplayControls(replay, { closeSettings: () => settings.menu(false) });
    const links = new BoardLinks(replay, root, { onStandingsJump: () => controls.focusRounds() });
    $("#space").remove();
    $("body").addClass("replay").append(controls.element);
    const viewer = new ReplayViewer({
        replay,
        view,
        model,
        root,
        speed: prefs.speed,
        onChange: (state) => {
            controls.show(state);
            links.show(state);
            positionUrl.show(state);
        },
        onError: (error) => showViewerFailure(error, gameId, replay),
    });
    controls.bind(viewer);
    links.bind(viewer);
    bindKeys(viewer, controls);
    bindWheel(viewer, stage);
    viewer.start(round, step);
    if (viewer.failed) {
        return;
    }
    fitTableToStage(stage);
}

/**
 * Show a game's replay on the board at the position its address names, with its control strip, or say why it cannot be
 * shown. The replay loads while `tilesLoaded` (the tile images' decoding) runs; only the board waits for it, so a failed
 * decode is the board's failure alone, never an unhandled rejection on a page that shows a problem instead. Once both
 * are ready, with sound on, the loading screen waits for its OK, the user activation the board's sounds need (a wheel
 * step grants none); the board, its keys and its wheel start only then.
 */
export async function showReplay(gameId, tilesLoaded) {
    document.title = t("replay.page_title");
    tilesLoaded.catch(() => {});
    const replay = await readReplay(gameId);
    if (replay === null) {
        return;
    }
    await tilesLoaded;
    if (ReplaySettings.sound_on(GAME_PREF_KEY)) {
        await waitForStart(t("replay.loading.ready"));
    }
    try {
        startViewer(gameId, replay);
    } catch (error) {
        showViewerFailure(error, gameId, replay);
    }
}
