import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";
import { CHAT_SHOWN_MS, showChat } from "../ronin/chat.js";

const SEAT = 2;

function renderTile(p) {
    return $('<span class="pai">').attr("data-pai", p.slice(0, 2));
}

function silentAudio() {
    return { play() {} };
}

function drawBoard() {
    const seats = ["main", "xiajia", "duimian", "shangjia"];
    const root = $('<div class="board">').append(
        seats.map((c) => $(`<div class="say ${c}">`)),
        seats.map((c) => $(`<div class="chat ${c} hide">`)),
        $('<div class="hule-dialog hide">'),
    );
    const model = new Majiang.Board({ title: "", player: ["a", "b", "c", "d"], qijia: 0 });
    model.qipai({
        zhuangfeng: 0,
        jushu: 0,
        changbang: 0,
        lizhibang: 0,
        defen: [25000, 25000, 25000, 25000],
        baopai: "s3",
        shoupai: ["", "", "", ""],
    });
    const board = new Majiang.UI.Board(root, renderTile, silentAudio, model).redraw();
    board.sound_on = false;
    return {
        board,
        model,
        root,
        call: $(".say.duimian", root),
        bubble: $(".chat.duimian", root),
    };
}

function isShown(node) {
    return !node.hasClass("hide") && !node.hasClass("fadeout");
}

describe("showChat", () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it("shows the line as text in the seat's chat bubble and fades it out later", () => {
        const { board, bubble } = drawBoard();

        expect(showChat(board, SEAT, "<b>gl</b> hf")).toBe(true);
        expect(isShown(bubble)).toBe(true);
        expect(bubble.text()).toBe("<b>gl</b> hf");
        expect(bubble.find("b")).toHaveLength(0);

        vi.advanceTimersByTime(CHAT_SHOWN_MS);
        expect(bubble.hasClass("fadeout")).toBe(true);
    });

    it("shows beside the seat's call bubble without touching it", () => {
        const { board, model, call, bubble } = drawBoard();
        model.lunban = SEAT;
        board.update();
        board.say("lizhi", SEAT);

        expect(showChat(board, SEAT, "ron")).toBe(true);
        expect(call.text()).toBe("リーチ");
        expect(bubble.text()).toBe("ron");
        expect(isShown(bubble)).toBe(true);
    });

    it("is cleared when a result opens while it shows", () => {
        const { board, bubble } = drawBoard();
        showChat(board, SEAT, "gg");

        board.hule({ l: SEAT });

        expect(bubble.hasClass("fadeout")).toBe(true);
    });

    it("is not shown while a result dialog covers the table", () => {
        const { board, root, bubble } = drawBoard();
        $(".hule-dialog", root).removeClass("hide");

        expect(showChat(board, SEAT, "gg")).toBe(false);
        expect(isShown(bubble)).toBe(false);
    });
});
