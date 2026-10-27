import $ from "jquery";
import { afterEach, describe, expect, it } from "vitest";

import "../majiang.js";
import Majiang from "../../vendor/majiang-core/index.js";
import Board from "../../vendor/majiang-ui/board.js";
import PAGE from "../../../index.html?raw";

const PLAYERS = ["Ronin", "Bot 1", "Bot 2", "Bot 3"];

function renderTile(p) {
    return $('<span class="pai">').attr("data-pai", p.slice(0, 2));
}

function silentAudio() {
    return { play() {}, currentTime: 0 };
}

function drawBoard() {
    document.body.innerHTML = new DOMParser().parseFromString(PAGE, "text/html").body.innerHTML;
    const model = new Majiang.Board({ title: "", player: [...PLAYERS], qijia: 0 });
    model.qipai({
        zhuangfeng: 0,
        jushu: 1,
        changbang: 0,
        lizhibang: 0,
        defen: [32000, 18000, 25000, 25000],
        baopai: "m1",
        shoupai: ["m123456789p1234", "", "", ""],
    });
    const board = new Board($("#board .board"), renderTile, silentAudio, model);
    board.redraw();
    return { board, model };
}

function plate(seat) {
    return $(`#board .board > .player.${seat}`);
}

afterEach(() => {
    document.body.innerHTML = "";
});

describe("Majiang.UI.Board nameplates", () => {
    it("give each seat its wind, name and score and mark only the dealer with 親", () => {
        drawBoard();

        expect(plate("xiajia").find(".feng").text()).toBe("東");
        expect(plate("xiajia").find(".name").text()).toBe("Bot 1");
        expect(plate("xiajia").find(".name").attr("title")).toBe("Bot 1");
        expect(plate("xiajia").find(".defen").text()).toBe("32,000");
        expect(plate("xiajia").find(".badge").text()).toBe("親");
        expect(plate("main").find(".feng").text()).toBe("北");
        expect(plate("main").find(".name").text()).toBe("Ronin");
        expect(plate("main").find(".defen").text()).toBe("25,000");
        expect(plate("main").find(".badge")).toHaveLength(0);
    });

    it("move the turn highlight to the seat on turn and refresh a score the round changed", () => {
        const { board, model } = drawBoard();
        expect(plate("xiajia").hasClass("lunban")).toBe(true);

        model.lunban = 1;
        model.defen[2] = 24000;
        board.update();

        expect(plate("xiajia").hasClass("lunban")).toBe(false);
        expect(plate("duimian").hasClass("lunban")).toBe(true);
        expect(plate("duimian").find(".defen").text()).toBe("24,000");
    });

    it("keep a dropped player's 切断中 through a redraw until they reconnect", () => {
        const { board } = drawBoard();

        board.players([true, true, true, false]);
        board.redraw();
        expect(plate("shangjia").hasClass("disconnect")).toBe(true);
        expect(plate("shangjia").find(".badge.offline").text()).toBe("切断中");
        expect(plate("shangjia").find(".name").text()).toBe("Bot 3");

        board.players([true, true, true, true]);
        expect(plate("shangjia").hasClass("disconnect")).toBe(false);
        expect(plate("shangjia").find(".badge.offline")).toHaveLength(0);
    });
});
