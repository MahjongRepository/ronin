import $ from "jquery";
import { afterEach, describe, expect, it } from "vitest";

import "../majiang.js";
import HuleDialog from "../../vendor/majiang-ui/dialog.js";

const PLAYERS = ["Ronin", "Bot 1", "Bot 2", "Bot 3"];

function renderDialog() {
    return $(`<div class="hule-dialog">
        <div class="title"></div>
        <div class="hule">
            <div class="shan"><span class="baopai"></span><span class="fubaopai"></span></div>
            <div class="shoupai"><div class="bingpai"></div><div class="fulou"></div></div>
            <table class="hupai">
                <tr class="r-hupai"><td class="name"></td><td class="fanshu"></td></tr>
                <tr class="r-defen"><td class="defen"></td></tr>
            </table>
        </div>
        <div class="pingju"><div class="name"></div><div class="players"></div></div>
        <table class="fenpei"></table>
    </div>`);
}

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
            name: "荒牌平局",
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
            name: "九種九牌",
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
            hupai: [{ name: "国士無双十三面", fanshu: "**" }],
            fanshu: 26,
            fu: 0,
            damanguan: 2,
            defen: 64000,
            fenpei: [0, -64000, 0, 64000],
        });

        expect(root.find(".title").text()).toBe("Ronin ロン ← Bot 2");
        expect(root.find(".hupai .r-hupai .fanshu").text()).toBe("ダブル役満");
    });
});
