import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";
import Majiang from "../../vendor/majiang-core/index.js";
import Board from "../../vendor/majiang-ui/board.js";
import PAGE from "../../../index.html?raw";
import { parseReplay } from "../replay/load.js";
import { POSITION, toReplay } from "../replay/paipu.js";
import { OUTCOME } from "../replay/round-end.js";
import { AUTOPLAY_SPEED, AUTOPLAY_SPEEDS } from "../replay/speeds.js";
import {
    AUTOPLAY_DEAL_MS,
    AUTOPLAY_DIALOG_POLL_MS,
    CALLOUT_MS,
    ReplayViewer,
} from "../replay/viewer.js";
import { withUnplayableDraw } from "./replay-edits.js";
import CHANKAN_ADDED from "./fixtures/replays/chankan_added.txt?raw";
import DOUBLE_RON_HEAD_BUMP from "./fixtures/replays/double_ron_head_bump.txt?raw";
import DOUBLE_RON_ON_HONBA from "./fixtures/replays/double_ron_on_honba.txt?raw";
import EAGER_GAME from "./fixtures/replays/eager_game.txt?raw";
import EXHAUSTIVE_TENPAI from "./fixtures/replays/exhaustive_tenpai.txt?raw";
import FOUR_KANS from "./fixtures/replays/four_kans.txt?raw";
import FULL_GAME from "./fixtures/replays/full_game.txt?raw";
import KANS from "./fixtures/replays/kans.txt?raw";
import PAO from "./fixtures/replays/pao.txt?raw";
import RIICHI from "./fixtures/replays/riichi.txt?raw";
import RON_RIICHI_DISCARD from "./fixtures/replays/ron_riichi_discard.txt?raw";
import TRUNCATED_AFTER_ROUND from "./fixtures/replays/truncated_after_round.txt?raw";
import TRUNCATED_MID_ROUND from "./fixtures/replays/truncated_mid_round.txt?raw";

/** The board's own delay before a win's dialog opens, shorter than a result's callouts. */
const BOARD_HULE_MS = 400;
/** The double ron of double_ron_on_honba.txt, the third round's result. */
const DOUBLE_RON_ROUND = 2;

function renderTile(p) {
    return $('<span class="pai">').attr("data-pai", p);
}

function recordingAudio(played = []) {
    return (name) => ({ play: () => played.push(name), currentTime: 0 });
}

function openViewer(text, { at = { round: 0, step: 0 }, audio = recordingAudio() } = {}) {
    document.body.innerHTML = new DOMParser().parseFromString(PAGE, "text/html").body.innerHTML;
    const replay = toReplay(parseReplay(text));
    const model = new Majiang.Board({
        title: "",
        player: [...replay.players],
        qijia: replay.qijia,
    });
    const root = $("#board .board");
    const view = new Board(root, renderTile, audio, model);
    view.open_shoupai = true;
    const viewer = new ReplayViewer({ replay, view, model, root });
    viewer.start(at.round, at.step);
    return { viewer, model, replay };
}

function texts(selector) {
    return $(selector)
        .map((i, node) => $(node).text())
        .get();
}

function tileLists(selector) {
    return $(selector)
        .map((i, node) => [
            $(".pai:not(.deleted)", node)
                .map((j, tile) => $(tile).attr("data-pai"))
                .get(),
        ])
        .get();
}

function tiles(selector) {
    return tileLists(selector).map((list) => list.join(""));
}

/** Each hand's tiles in any order: a hand stepped through shows its last draw apart until its turn passes. */
function handTiles(selector) {
    return tileLists(selector).map((list) => list.toSorted().join(""));
}

/** Each river's riichi stick, and where its last-discard mark and sideways tile sit (-1: none). */
function riverMarks() {
    return $("#board .board > .he")
        .map((i, he) => {
            const tiles = $(".dapai .pai", he);
            return [
                [
                    !$(".chouma", he).hasClass("hide"),
                    tiles.index($(".pai.dapai", he)),
                    tiles.index($(".lizhi .pai", he)),
                ],
            ];
        })
        .get();
}

function shown(selector) {
    return !$(selector).hasClass("hide");
}

/** What the table shows once its timers have run, from the model and from the board's DOM. */
function settledTable(model) {
    vi.runAllTimers();
    return {
        hands: model.shoupai.map((shoupai) => shoupai.toString()),
        rivers: model.he.map((he) => he._pai.join("")),
        defen: [...model.defen],
        sticks: [model.changbang, model.lizhibang],
        wall: [model.shan.paishu, ...model.shan.baopai],
        turn: model.lunban,
        score: texts("#board .score > *"),
        plates: texts("#board .board > .player"),
        handTiles: handTiles("#board .board > .shoupai"),
        riverTiles: tiles("#board .board > .he"),
        riverMarks: riverMarks(),
        dialog: shown("#board .hule-dialog") && [
            $("#board .hule-dialog").text(),
            ...tiles("#board .hule-dialog .shoupai, #board .hule-dialog .shan"),
        ],
        summary: shown("#board .summary") && $("#board .summary").text(),
    };
}

function resultStep(replay, round) {
    return replay.rounds[round].positions.findIndex(
        (position) => position.kind === POSITION.RESULT,
    );
}

function dialogFigures() {
    return {
        scores: texts("#board .hule-dialog .fenpei .defen"),
        honba: Number($("#board .hule-dialog .jicun .changbang").text()),
        sticks: Number($("#board .hule-dialog .jicun .lizhibang").text()),
    };
}

function pressDialogNext() {
    $("#board .hule-dialog .next").trigger("click");
    vi.runAllTimers();
}

const WHOLE_GAME = () => ({ from: { round: 0, step: 0 }, until: null });

/** From just before the first won round's result to a few positions into the next round. */
function acrossTheFirstWin(replay) {
    const round = replay.rounds.findIndex(
        ({ outcome }, index) =>
            [OUTCOME.TSUMO, OUTCOME.RON].includes(outcome?.kind) &&
            index + 1 < replay.rounds.length,
    );
    return {
        from: { round, step: resultStep(replay, round) - 2 },
        until: { round: round + 1, step: 4 },
    };
}

function acrossTheDoubleRon(replay) {
    const round = DOUBLE_RON_ROUND;
    return {
        from: { round, step: resultStep(replay, round) - 2 },
        until: { round: round + 1, step: 4 },
    };
}

function reached(state, until) {
    return until !== null && state.round === until.round && state.step === until.step;
}

const DOUBLE_RON_FIRST_WIN = {
    scores: ["26,700", "25,300", "21,800", "26,200"],
    honba: 2,
    sticks: 0,
};
const DOUBLE_RON_SECOND_WIN = {
    scores: ["26,700", "27,500", "19,600", "26,200"],
    honba: 2,
    sticks: 0,
};

beforeEach(() => {
    vi.useFakeTimers();
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    document.body.innerHTML = "";
});

describe("ReplayViewer", () => {
    it.each([
        ["riichi.txt", RIICHI, WHOLE_GAME],
        ["kans.txt", KANS, WHOLE_GAME],
        ["four_kans.txt", FOUR_KANS, WHOLE_GAME],
        ["chankan_added.txt", CHANKAN_ADDED, WHOLE_GAME],
        ["double_ron_head_bump.txt", DOUBLE_RON_HEAD_BUMP, WHOLE_GAME],
        ["exhaustive_tenpai.txt", EXHAUSTIVE_TENPAI, WHOLE_GAME],
        ["eager_game.txt", EAGER_GAME, acrossTheFirstWin],
        ["double_ron_on_honba.txt", DOUBLE_RON_ON_HONBA, acrossTheDoubleRon],
    ])(
        "lands on the same table stepping forward then back as seeking there: %s",
        (_, text, span) => {
            const { from, until } = span(toReplay(parseReplay(text)));
            const { viewer, model } = openViewer(text, { at: from });
            const stepped = [{ at: viewer.state, table: settledTable(model) }];
            while (viewer.canNext && !reached(viewer.state, until)) {
                viewer.next();
                stepped.push({ at: viewer.state, table: settledTable(model) });
            }

            for (const { at, table } of stepped.toReversed().slice(1)) {
                viewer.back();
                expect(viewer.state).toEqual(at);
                expect(settledTable(model), `back to ${at.round}/${at.step}`).toEqual(table);
            }

            stepped.slice(0, -1).forEach(({ at }, index) => {
                const opened = openViewer(text, { at });
                for (let page = 0; page < at.page; page++) {
                    settledTable(opened.model);
                    opened.viewer.next();
                }
                settledTable(opened.model);
                opened.viewer.next();
                const after = stepped[index + 1];
                expect(settledTable(opened.model), `next from ${at.round}/${at.step}`).toEqual(
                    after.table,
                );
            });
        },
    );

    it("reopens the previous round's result when backing out of a deal", () => {
        const { viewer, replay } = openViewer(FULL_GAME, { at: { round: 1, step: 0 } });

        viewer.back();

        const step = resultStep(replay, 0);
        expect(viewer.state).toMatchObject({ round: 0, step, kind: POSITION.RESULT });
        vi.runAllTimers();
        expect(shown("#board .hule-dialog")).toBe(true);
        expect(shown("#board .hule-dialog .next")).toBe(true);
        expect($("#board .score .jushu").text()).toBe("東一局");
    });

    it("jumps between rounds' deals and turns the table, keeping the position", () => {
        const { viewer, replay } = openViewer(FULL_GAME, { at: { round: 0, step: 5 } });
        const changes = [];
        viewer.onChange = (state) => changes.push(state);

        viewer.nextRound();
        expect(viewer.state).toMatchObject({ round: 1, step: 0 });
        viewer.next();
        viewer.prevRound();
        expect(viewer.state).toMatchObject({ round: 1, step: 0 });
        viewer.prevRound();
        expect(viewer.state).toMatchObject({ round: 0, step: 0, canBack: false });

        viewer.seek(1, 3);
        viewer.setViewpoint(2);
        expect(changes.at(-1)).toMatchObject({ round: 1, step: 3, seat: 2 });
        expect($("#board .board > .player.main .name").text()).toBe(replay.players[2]);
        expect(() => viewer.setViewpoint(4)).toThrow(RangeError);
    });

    it("pages a double ron's wins on 次へ and Next before leaving the result", () => {
        const { viewer, replay } = openViewer(DOUBLE_RON_ON_HONBA);
        const step = resultStep(replay, DOUBLE_RON_ROUND);
        const changes = [];
        viewer.onChange = (state) => changes.push(state);

        viewer.seek(DOUBLE_RON_ROUND, step - 1);
        viewer.next();
        vi.runAllTimers();
        expect(dialogFigures()).toEqual(DOUBLE_RON_FIRST_WIN);

        $("#board .hule-dialog .next").trigger("click").trigger("click");
        vi.runAllTimers();
        expect(dialogFigures()).toEqual(DOUBLE_RON_SECOND_WIN);
        expect(viewer.state).toMatchObject({ round: DOUBLE_RON_ROUND, step });
        expect(changes).toHaveLength(3);

        pressDialogNext();
        expect(viewer.state).toMatchObject({
            round: DOUBLE_RON_ROUND + 1,
            step: 0,
            kind: POSITION.DEAL,
        });

        viewer.back();
        vi.runAllTimers();
        expect(viewer.state).toMatchObject({ round: DOUBLE_RON_ROUND, step, page: 1 });
        expect(dialogFigures()).toEqual(DOUBLE_RON_SECOND_WIN);
        viewer.back();
        vi.runAllTimers();
        expect(viewer.state).toMatchObject({ round: DOUBLE_RON_ROUND, step, page: 0 });
        expect(dialogFigures()).toEqual(DOUBLE_RON_FIRST_WIN);

        viewer.next();
        vi.runAllTimers();
        expect(viewer.state).toMatchObject({ round: DOUBLE_RON_ROUND, step, page: 1 });
        expect(dialogFigures()).toEqual(DOUBLE_RON_SECOND_WIN);
        viewer.next();
        expect(viewer.state).toMatchObject({ round: DOUBLE_RON_ROUND + 1, step: 0 });
    });

    it("keeps a double ron's page when the hands close or the table turns", () => {
        const { viewer, replay } = openViewer(DOUBLE_RON_ON_HONBA);
        const step = resultStep(replay, DOUBLE_RON_ROUND);
        viewer.seek(DOUBLE_RON_ROUND, step);
        vi.runAllTimers();
        pressDialogNext();

        viewer.setOpenHands(false);
        vi.runAllTimers();
        expect(viewer.state).toMatchObject({ step, page: 1, openHands: false });
        expect(tiles("#board .board > .shoupai.duimian")[0]).toMatch(/^_+$/);
        expect(dialogFigures()).toEqual(DOUBLE_RON_SECOND_WIN);
        viewer.setViewpoint(1);
        vi.runAllTimers();
        expect(viewer.state).toMatchObject({ step, page: 1, seat: 1 });

        pressDialogNext();
        expect(viewer.state).toMatchObject({ round: DOUBLE_RON_ROUND + 1, step: 0 });
    });

    it("opens a double ron's win at once on Next while it is on its way, skipping none", () => {
        const { viewer, replay } = openViewer(DOUBLE_RON_ON_HONBA);
        const step = resultStep(replay, DOUBLE_RON_ROUND);
        viewer.seek(DOUBLE_RON_ROUND, step - 1);

        viewer.next();
        viewer.next();
        expect(viewer.state).toMatchObject({ step, page: 0 });
        expect(shown("#board .hule-dialog")).toBe(true);
        expect(dialogFigures()).toEqual(DOUBLE_RON_FIRST_WIN);

        viewer.next();
        vi.advanceTimersByTime(BOARD_HULE_MS);
        viewer.next();
        expect(viewer.state).toMatchObject({ step, page: 1 });
        expect(shown("#board .hule-dialog")).toBe(true);
        expect(dialogFigures()).toEqual(DOUBLE_RON_SECOND_WIN);

        viewer.next();
        expect(viewer.state).toMatchObject({ round: DOUBLE_RON_ROUND + 1, step: 0 });
    });

    it("keeps the cursor on the last position it played when the next one cannot be played, and stops", () => {
        const { viewer } = openViewer(withUnplayableDraw(FULL_GAME));
        const errors = [];
        viewer.onError = (error) => errors.push(error);

        let before;
        while (errors.length === 0 && viewer.canNext) {
            before = viewer.state;
            viewer.next();
        }

        expect(errors.map((error) => error.name)).toEqual(["UnplayableReplayError"]);
        expect(viewer.state).toMatchObject({
            round: before.round,
            step: before.step,
            canBack: false,
            canNext: false,
        });
        viewer.back();
        expect(viewer.state.step).toBe(before.step);
    });

    it("opens no stale result after moving while it is about to open", () => {
        const { viewer, replay } = openViewer(DOUBLE_RON_ON_HONBA);
        const step = resultStep(replay, DOUBLE_RON_ROUND);

        viewer.seek(DOUBLE_RON_ROUND, step - 1);
        viewer.next();
        viewer.back();
        vi.runAllTimers();
        expect(shown("#board .hule-dialog")).toBe(false);

        viewer.seek(DOUBLE_RON_ROUND, step - 1);
        viewer.next();
        viewer.nextRound();
        vi.runAllTimers();
        expect(shown("#board .hule-dialog")).toBe(false);

        viewer.seek(DOUBLE_RON_ROUND, step);
        vi.advanceTimersByTime(BOARD_HULE_MS);
        viewer.back();
        vi.runAllTimers();
        expect(shown("#board .hule-dialog")).toBe(false);
    });

    it("sounds callouts stepping forward but not seeking", () => {
        const played = [];
        const ron = openViewer(RON_RIICHI_DISCARD, { audio: recordingAudio(played) });
        const ronResult = resultStep(ron.replay, 0);
        ron.viewer.seek(0, ronResult - 1);
        ron.viewer.seek(0, ronResult);
        const { viewer, replay } = openViewer(PAO, { audio: recordingAudio(played) });
        const steps = replay.rounds[0].positions;
        const pon = steps.findLastIndex((position) => position.say[0]?.name === "peng");
        const result = resultStep(replay, 0);

        viewer.seek(0, pon - 1);
        viewer.seek(0, pon);
        viewer.seek(0, result);
        vi.runAllTimers();
        expect(played).toEqual([]);

        viewer.seek(0, pon - 1);
        viewer.next();
        viewer.seek(0, result - 1);
        viewer.next();
        vi.runAllTimers();
        expect(played).toEqual(["peng", "zimo", "gong"]);
    });

    it("fades a position's callouts after a moment, a move in between starting the moment afresh", () => {
        const { viewer, replay } = openViewer(PAO);
        const pon = replay.rounds[0].positions.findLastIndex(
            (position) => position.say[0]?.name === "peng",
        );
        const callouts = () =>
            $("#board .say").filter(
                (i, say) => !$(say).hasClass("hide") && !$(say).hasClass("fadeout"),
            ).length;

        viewer.seek(0, pon);
        vi.advanceTimersByTime(CALLOUT_MS / 2);
        viewer.seek(0, pon);
        vi.advanceTimersByTime(CALLOUT_MS / 2);
        expect(callouts()).toBe(1);
        vi.advanceTimersByTime(CALLOUT_MS / 2);
        expect(callouts()).toBe(0);

        viewer.back();
        viewer.next();
        expect(callouts()).toBe(1);
        vi.advanceTimersByTime(CALLOUT_MS);
        expect(callouts()).toBe(0);
    });

    it.each([
        ["truncated_mid_round.txt", TRUNCATED_MID_ROUND],
        ["truncated_after_round.txt", TRUNCATED_AFTER_ROUND],
    ])(
        "stops at the last recorded position of a truncated game, its result offering no 次へ: %s",
        (_, text) => {
            const { viewer, replay } = openViewer(text);

            viewer.last();
            const last = viewer.state;
            viewer.next();
            vi.runAllTimers();

            expect(last).toMatchObject({
                round: replay.rounds.length - 1,
                step: replay.rounds.at(-1).positions.length - 1,
                endedEarly: true,
                canNext: false,
            });
            expect(viewer.state).toEqual(last);
            expect(shown("#board .summary")).toBe(false);
            expect(shown("#board .hule-dialog .next")).toBe(false);
        },
    );

    it("shows the final standings after the last result and leaves them for where the replay was opened or a round's deal", () => {
        const { viewer, replay } = openViewer(FULL_GAME);
        const round = replay.rounds.length - 1;
        viewer.seek(round, resultStep(replay, round));
        const assign = vi.spyOn(window.location, "assign").mockImplementation(() => {});

        viewer.next();
        vi.runAllTimers();

        expect(viewer.state).toMatchObject({
            kind: POSITION.SUMMARY,
            endedEarly: false,
            canNext: false,
        });
        expect(shown("#board .summary")).toBe(true);
        const top = replay.standings.rank.indexOf(1);
        const column = (top - viewer.state.seat + 4) % 4;
        expect(texts("#board .summary .row-rank .rank")[column]).toBe("1位");
        expect(texts("#board .summary .row-defen .defen")[column]).toBe(
            replay.standings.defen[top].toLocaleString("en-US"),
        );

        expect($("#board .summary .exit").text()).toBe("履歴へ戻る");
        $("#board .summary .exit").trigger("click");
        expect(assign).toHaveBeenLastCalledWith("/history");
        vi.spyOn(document, "referrer", "get").mockReturnValue(
            `${window.location.origin}/history?page=2`,
        );
        $("#board .summary .exit").trigger("click");
        expect(assign).toHaveBeenLastCalledWith(`${window.location.origin}/history?page=2`);

        $("#board .summary .body .row-diff").eq(2).find(".replay-summary-round").trigger("click");
        expect(viewer.state).toMatchObject({ round: 2, step: 0 });
        expect(shown("#board .summary")).toBe(false);
    });

    it("autoplay steps at once on Play, then at the chosen speed, a draw at half of it and a deal for 1.5 s at least", () => {
        const { viewer, replay } = openViewer(FULL_GAME);
        const positions = replay.rounds[0].positions;
        const draw = positions.findIndex(
            (position, index) =>
                position.kind === POSITION.DRAW &&
                position.say.length === 0 &&
                positions[index + 1].say.length === 0,
        );
        viewer.seek(0, draw - 1);
        viewer.setSpeed(AUTOPLAY_SPEED.SLOW);

        viewer.play();
        expect(viewer.state).toMatchObject({ step: draw, playing: true });
        vi.advanceTimersByTime(AUTOPLAY_SPEEDS.slow / 2 - 1);
        expect(viewer.state.step).toBe(draw);
        vi.advanceTimersByTime(1);
        expect(viewer.state.step).toBe(draw + 1);
        viewer.setSpeed(AUTOPLAY_SPEED.FAST);
        vi.advanceTimersByTime(AUTOPLAY_SPEEDS.fast);
        expect(viewer.state.step).toBe(draw + 2);

        viewer.seek(0, resultStep(replay, 0));
        vi.runAllTimers();
        viewer.play();
        expect(viewer.state).toMatchObject({ round: 1, step: 0, playing: true });
        vi.advanceTimersByTime(AUTOPLAY_DEAL_MS - 1);
        expect(viewer.state.step).toBe(0);
        vi.advanceTimersByTime(1);
        expect(viewer.state.step).toBe(1);
    });

    it("autoplay holds a position with callouts for as long as they show, at any speed", () => {
        const { viewer, replay } = openViewer(PAO);
        const pon = replay.rounds[0].positions.findLastIndex(
            (position) => position.say[0]?.name === "peng",
        );
        viewer.seek(0, pon - 1);
        viewer.setSpeed(AUTOPLAY_SPEED.FAST);

        viewer.play();
        vi.advanceTimersByTime(CALLOUT_MS - 1);
        expect(viewer.state.step).toBe(pon);
        vi.advanceTimersByTime(1);
        expect(viewer.state.step).toBe(pon + 1);
    });

    it("autoplay leaves a result only once its dialog is fully shown, never cutting the win's callouts short", () => {
        const { viewer, replay } = openViewer(EAGER_GAME);
        const { round } = acrossTheFirstWin(replay).from;
        const result = resultStep(replay, round);
        viewer.seek(round, result - 1);
        viewer.setSpeed(AUTOPLAY_SPEED.FAST);
        const dialogShown = () =>
            shown("#board .hule-dialog") && !$("#board .hule-dialog").hasClass("fadeout");

        viewer.next();
        viewer.play();
        vi.advanceTimersByTime(AUTOPLAY_SPEEDS.fast);
        expect(viewer.state).toMatchObject({ round, step: result, playing: true });
        expect(dialogShown()).toBe(false);
        expect($("#board .say").not(".hide, .fadeout").length).toBeGreaterThan(0);

        while (!dialogShown()) {
            vi.advanceTimersByTime(AUTOPLAY_DIALOG_POLL_MS);
        }
        expect(viewer.state).toMatchObject({ round, step: result });
        vi.advanceTimersByTime(AUTOPLAY_DIALOG_POLL_MS + AUTOPLAY_SPEEDS.fast);
        expect(viewer.state).toMatchObject({ round: round + 1, step: 0, playing: true });
    });

    it("autoplay pauses at each win of a double ron, Play paging to the next and 次へ playing on", () => {
        const { viewer, replay } = openViewer(DOUBLE_RON_ON_HONBA);
        const step = resultStep(replay, DOUBLE_RON_ROUND);
        viewer.seek(DOUBLE_RON_ROUND, step - 1);

        viewer.play();
        vi.runAllTimers();
        expect(viewer.state).toMatchObject({ step, page: 0, playing: false });
        expect(dialogFigures()).toEqual(DOUBLE_RON_FIRST_WIN);

        viewer.play();
        vi.runAllTimers();
        expect(viewer.state).toMatchObject({ step, page: 1, playing: false });
        expect(dialogFigures()).toEqual(DOUBLE_RON_SECOND_WIN);

        $("#board .hule-dialog .next").trigger("click");
        expect(viewer.state).toMatchObject({
            round: DOUBLE_RON_ROUND + 1,
            step: 0,
            playing: true,
        });
    });

    it("autoplay plays on through a change of viewpoint or of the hands shown", () => {
        const { viewer } = openViewer(FULL_GAME, { at: { round: 0, step: 1 } });

        viewer.play();
        viewer.setViewpoint(2);
        viewer.setOpenHands(false);
        expect(viewer.state).toMatchObject({ step: 2, seat: 2, openHands: false, playing: true });
        vi.advanceTimersByTime(AUTOPLAY_SPEEDS.normal);
        expect(viewer.state).toMatchObject({ step: 3, playing: true });
    });

    it("autoplay pauses when the page is hidden", () => {
        const { viewer } = openViewer(FULL_GAME);
        viewer.play();

        vi.spyOn(document, "hidden", "get").mockReturnValue(true);
        document.dispatchEvent(new Event("visibilitychange"));
        const { step } = viewer.state;
        vi.runAllTimers();

        expect(viewer.state).toMatchObject({ step, playing: false });
    });

    it.each([
        ["full_game.txt", FULL_GAME, POSITION.SUMMARY],
        ["truncated_mid_round.txt", TRUNCATED_MID_ROUND, POSITION.DRAW],
    ])("autoplay pauses at the game's end: %s", (_, text, kind) => {
        const { viewer, replay } = openViewer(text);
        const round = replay.rounds.length - 1;
        viewer.seek(round, replay.rounds[round].positions.length - 2);
        vi.runAllTimers();

        viewer.play();
        vi.runAllTimers();
        viewer.play();

        expect(viewer.state).toMatchObject({ kind, canNext: false, playing: false });
    });
});
