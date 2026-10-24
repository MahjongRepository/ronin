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
    const root = $('<div class="board">').append(
        ["main", "xiajia", "duimian", "shangjia"].map((c) => $(`<div class="say ${c}">`)),
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
    return { board, model, bubble: $(".say.duimian", root) };
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

    it("shows the line in the seat's bubble, which the board hides, and fades it out later", () => {
        const { board, bubble } = drawBoard();

        expect(showChat(board, SEAT, "gl hf")).toBe(true);
        expect(isShown(bubble)).toBe(true);
        expect(bubble.text()).toBe("gl hf");

        vi.advanceTimersByTime(CHAT_SHOWN_MS);
        expect(bubble.hasClass("fadeout")).toBe(true);
    });

    it("leaves the seat's call bubbles to the board", () => {
        const { board, model, bubble } = drawBoard();
        model.lunban = SEAT;
        board.update();
        board.say("lizhi", SEAT);

        expect(showChat(board, SEAT, "nice")).toBe(false);
        expect(bubble.text()).toBe("リーチ");

        model.lunban = SEAT + 1;
        board.update();
        expect(showChat(board, SEAT, "gl hf")).toBe(true);
        bubble.trigger("transitionend");
        expect(isShown(bubble)).toBe(true);
        board.say("chi", SEAT);
        vi.advanceTimersByTime(CHAT_SHOWN_MS);
        expect(isShown(bubble)).toBe(true);
        expect(bubble.text()).toBe("チー");
    });
});
