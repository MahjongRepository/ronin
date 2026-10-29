import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";
import Majiang from "../../vendor/majiang-core/index.js";
import Board from "../../vendor/majiang-ui/board.js";
import PAGE from "../../../index.html?raw";
import { setLocale } from "../../i18n/index.js";

beforeEach(() => setLocale("ja"));

const PLAYERS = ["Ronin", "Bot 1", "Bot 2", "Bot 3"];

function renderTile(p) {
    return $('<span class="pai">').attr("data-pai", p.slice(0, 2));
}

function silentAudio() {
    return { play() {}, currentTime: 0 };
}

function drawBoard({ shoupai = ["m123456789p1234", "", "", ""], openHands = false } = {}) {
    document.body.innerHTML = new DOMParser().parseFromString(PAGE, "text/html").body.innerHTML;
    const model = new Majiang.Board({ title: "", player: [...PLAYERS], qijia: 0 });
    model.qipai({
        zhuangfeng: 0,
        jushu: 1,
        changbang: 0,
        lizhibang: 0,
        defen: [32000, 18000, 25000, 25000],
        baopai: "m1",
        shoupai,
    });
    const board = new Board($("#board .board"), renderTile, silentAudio, model);
    board.open_shoupai = openHands;
    board.redraw();
    return { board, model };
}

function plate(seat) {
    return $(`#board .board > .player.${seat}`);
}

function handTiles(seat) {
    return $(`#board .board .shoupai.${seat} .bingpai .pai`)
        .map((i, tile) => $(tile).attr("data-pai"))
        .get()
        .join("");
}

afterEach(() => {
    vi.useRealTimers();
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
        expect(plate("duimian").find(".defen-diff").text()).toBe("-1,000");
    });

    it("give each other seat its score's lead over the viewpoint's, signed, all pinned by a click on any", () => {
        const { board } = drawBoard();
        board.pin_diffs_on_click();
        const table = $("#board .board");

        expect(plate("xiajia").find(".defen-diff").text()).toBe("+7,000");
        expect(plate("duimian").find(".defen-diff").text()).toBe("-7,000");
        expect(plate("shangjia").find(".defen-diff").text()).toBe("0");

        plate("main").trigger("click");
        expect(table.hasClass("diffs-pinned")).toBe(true);

        board.redraw();
        plate("xiajia").trigger("click");
        expect(table.hasClass("diffs-pinned")).toBe(false);
    });

    it("mark a dropped player's seat through a redraw until they reconnect, its meaning in text too", () => {
        const { board } = drawBoard();

        board.players([true, true, true, false]);
        board.redraw();
        expect(plate("shangjia").hasClass("disconnect")).toBe(true);
        expect(plate("shangjia").find(".seat-mark").text()).toBe("切断中");
        expect(plate("shangjia").find(".name").text()).toBe("Bot 3");

        board.players([true, true, true, true]);
        expect(plate("shangjia").hasClass("disconnect")).toBe(false);
        expect(plate("shangjia").find(".seat-mark")).toHaveLength(0);
    });
});

describe("Majiang.UI.Board hands", () => {
    const HANDS = ["m123456789p1234", "s1112345678999", "z11122233344m1", "p1122334455667"];

    it("show only the viewpoint's hand face up in the live game", () => {
        drawBoard({ shoupai: HANDS });

        expect(handTiles("main")).toBe("p1p1p2p2p3p3p4p4p5p5p6p6p7");
        expect(handTiles("xiajia")).toBe("_".repeat(13));
    });

    it("show every hand face up when all hands are open, through a draw's reveal of noten hands", () => {
        vi.useFakeTimers();
        const { board, model } = drawBoard({ shoupai: HANDS, openHands: true });
        const faceUp = {
            xiajia: handTiles("xiajia"),
            duimian: handTiles("duimian"),
            shangjia: handTiles("shangjia"),
            main: handTiles("main"),
        };
        expect(faceUp.xiajia).toBe("m1m2m3m4m5m6m7m8m9p1p2p3p4");
        expect(faceUp.duimian).toBe("s1s1s1s2s3s4s5s6s7s8s9s9s9");

        model.lunban = 0;
        board.update();
        board.update({
            pingju: {
                name: "荒牌平局",
                shoupai: ["", "", "", ""],
                fenpei: [0, 0, 0, 0],
                tenpai: [false, false, false, false],
                players: [],
            },
        });
        vi.runAllTimers();

        for (const [seat, tiles] of Object.entries(faceUp)) expect(handTiles(seat)).toBe(tiles);
    });
});

describe("Majiang.UI.Board rivers", () => {
    function endOnRiichiDiscard(name) {
        vi.useFakeTimers();
        const { board, model } = drawBoard();
        const dapai = { l: 0, p: "p4*" };
        model.dapai(dapai);
        board.update({ dapai });
        const pingju = { name, shoupai: ["", "", "", ""], fenpei: [0, 0, 0, 0] };
        model.pingju(pingju);
        board.update({ pingju });
        const river = $("#board .board > .he.xiajia");
        return {
            stick: !river.find(".chouma").hasClass("hide"),
            sideways: river.find(".lizhi .pai").length,
        };
    }

    it("lay a riichi discard voided by four winds sideways with no stick", () => {
        expect(endOnRiichiDiscard("四風連打")).toEqual({ stick: false, sideways: 1 });
    });

    it("show the stick of a riichi discard deposited by an exhaustive draw", () => {
        expect(endOnRiichiDiscard("荒牌平局")).toEqual({ stick: true, sideways: 1 });
    });
});
