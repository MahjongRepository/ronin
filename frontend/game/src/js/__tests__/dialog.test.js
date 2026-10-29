import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import "../majiang.js";
import HuleDialog from "../../vendor/majiang-ui/dialog.js";
import { huleMessage } from "../ronin/results.js";
import { setLocale } from "../../i18n/index.js";

beforeEach(() => setLocale("ja"));

const PLAYERS = ["Ronin", "Bot 1", "Bot 2", "Bot 3"];

function renderDialog() {
    return $(`<div class="hule-dialog">
        <div class="title"></div>
        <div class="hule">
            <div class="note"></div>
            <div class="shan"><span class="baopai"></span><span class="fubaopai"></span></div>
            <div class="shoupai"><div class="bingpai"></div><div class="fulou"></div></div>
            <table class="hupai">
                <tr class="row-hupai"><td class="name"></td><td class="fanshu"></td></tr>
                <tr class="row-defen"><td class="defen"></td></tr>
            </table>
        </div>
        <div class="pingju"><div class="name"></div><div class="players"></div></div>
        <table class="fenpei"></table>
    </div>`);
}

const DAISANGEN_WIN = Object.freeze({
    l: 1,
    baojia: null,
    shoupai: "m23p55m4,z555+,z666-,z777=",
    hupai: [{ yi: 103, fanshu: "*" }],
    fanshu: 13,
    fu: 0,
    damanguan: 1,
    defen: 32000,
    fenpei: [-16000, 32000, -8000, -8000],
});

function renderTile(p) {
    return $('<span class="pai">').attr("data-pai", p);
}

function createModel(defen) {
    return {
        player_id: [1, 2, 3, 0],
        player: PLAYERS,
        defen,
        shan: { baopai: ["m1"], fubaopai: null },
    };
}

function scoreRows(root) {
    return root
        .find(".fenpei tr")
        .map((i, row) =>
            $(row)
                .children()
                .map((j, cell) => $(cell).text())
                .get()
                .join(" "),
        )
        .get();
}

afterEach(() => {
    document.body.innerHTML = "";
});

describe("Majiang.UI.HuleDialog", () => {
    it("lists each player's tenpai, settled score and change on an exhaustive draw, inside the dialog only", () => {
        const standings = $(
            '<table class="summary"><tr><td class="main"><span class="defen">40,400</span><span class="diff plus">+7,000</span></td></tr></table>',
        );
        const root = renderDialog();
        $(document.body).append(standings, root);
        const model = createModel([31000, 21000, 20000, 28000]);

        new HuleDialog(root, renderTile, model).pingju({
            code: "exhaustive",
            shoupai: [null, null, null, null],
            fenpei: [1500, -1500, -1500, 1500],
            tenpai: [true, false, false, true],
            players: [],
        });

        expect(scoreRows(root)).toEqual([
            "東 Bot 1 テンパイ 22,500 +1,500",
            "南 Bot 2 ノーテン 18,500 -1,500",
            "西 Bot 3 ノーテン 26,500 -1,500",
            "北 Ronin テンパイ 32,500 +1,500",
        ]);
        expect(root.find(".fenpei tr.main .player").text()).toBe("Ronin");
        expect(root.find(".pingju .players").text()).toBe("");
        expect(standings.find(".defen").text()).toBe("40,400");
        expect(standings.find(".diff").text()).toBe("+7,000");
    });

    it("names who declared nine terminals", () => {
        const root = renderDialog();
        const model = createModel([25000, 25000, 25000, 25000]);

        new HuleDialog(root, renderTile, model).pingju({
            code: "nine_terminals",
            shoupai: [null, null, null, null],
            fenpei: [0, 0, 0, 0],
            tenpai: null,
            players: [2],
        });

        expect(root.find(".pingju .players").text()).toBe("宣言: Bot 3");
        expect(root.find(".fenpei .tenpai")).toHaveLength(0);
    });

    it("heads a ron with its winner and loser, and labels a double yakuman by name", () => {
        const root = renderDialog();
        const model = createModel([25000, 25000, 25000, 25000]);

        new HuleDialog(root, renderTile, model).hule({
            l: 3,
            baojia: 1,
            shoupai: "m19p19s19z1234567m1",
            hupai: [{ yi: 112, fanshu: "**" }],
            fanshu: 26,
            fu: 0,
            damanguan: 2,
            defen: 64000,
            fenpei: [0, -64000, 0, 64000],
        });

        expect(root.find(".title").text()).toBe("Ronin ロン ← Bot 2");
        expect(root.find(".hupai .row-hupai .fanshu").text()).toBe("ダブル役満");
    });

    it("names the liable player of a pao win, and no one on the next win", () => {
        const root = renderDialog();
        const dialog = new HuleDialog(root, renderTile, createModel([25000, 25000, 25000, 25000]));

        dialog.hule({ ...DAISANGEN_WIN, fenpei: [0, 32000, -32000, 0], pao: 2 });
        expect(root.find(".hule .note").text()).toBe("パオ: Bot 3");

        dialog.hule(DAISANGEN_WIN);
        expect(root.find(".hule .note").text()).toBe("");
    });

    it("numbers a double ron's win in its title and names the head-bumped callers", () => {
        const root = renderDialog();
        const model = createModel([25000, 25000, 25000, 25000]);

        new HuleDialog(root, renderTile, model).hule({
            ...DAISANGEN_WIN,
            baojia: 0,
            fenpei: [-32000, 32000, 0, 0],
            headBumped: [2, 3],
            page: { number: 1, count: 2 },
        });

        expect(root.find(".title").text()).toBe("Bot 2 ロン ← Bot 1 (1/2)");
        expect(root.find(".hule .note").text()).toBe("頭ハネ: Bot 3・Ronin のロン無効");
    });

    it("names an English win's yaku by their server ids and its value in fu, han and points", () => {
        setLocale("en");
        const root = renderDialog();
        const { hule } = huleMessage({
            l: 1,
            shoupai: "m123p456s789m22p78p9",
            baojia: 0,
            hr: {
                han: 4,
                fu: 30,
                pt: 80,
                yk: [
                    { yi: 1, han: 1 },
                    { yi: 12, han: 1 },
                    { yi: 13, han: 1 },
                    { yi: 122, han: 1 },
                ],
            },
            fenpei: [-8000, 8000, 0, 0],
            fubaopai: ["m1"],
        });

        new HuleDialog(root, renderTile, createModel([25000, 25000, 25000, 25000])).hule(hule);

        expect(root.find(".title").text()).toBe("Bot 2: Ron ← Bot 1");
        expect(
            root
                .find(".hupai .row-hupai .name")
                .map((i, cell) => $(cell).text())
                .get(),
        ).toEqual(["Riichi", "Pinfu", "Tanyao", "Ura Dora"]);
        expect(root.find(".hupai .row-defen").text()).toBe("30 fu 4 han Mangan 8,000 points");
    });

    it("names a daisharin by the suit it is made in", () => {
        const root = renderDialog();
        const dialog = new HuleDialog(root, renderTile, createModel([25000, 25000, 25000, 25000]));
        const daisharin = (shoupai) =>
            huleMessage({
                l: 1,
                shoupai,
                baojia: null,
                hr: { han: 13, fu: 0, pt: 320, yk: [{ yi: 109, han: 13 }] },
                fenpei: [-16000, 32000, -8000, -8000],
                fubaopai: null,
            }).hule;
        const yakuOf = (shoupai) => {
            dialog.hule(daisharin(shoupai));
            return root.find(".hupai .row-hupai .name").text();
        };

        expect(yakuOf("p2233445566778p8")).toBe("大車輪");
        expect(yakuOf("m2233445566778m8")).toBe("大数隣");
        expect(yakuOf("s2233445566778s8")).toBe("大竹林");
    });
});
