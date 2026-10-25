import $ from "jquery";
import { describe, expect, it } from "vitest";

import "../majiang.js";
import summary from "../../vendor/majiang-ui/summary.js";

const PLAYERS = ["Ronin", "Bot 1", "Bot 2", "Bot 3"];
const NO_PAYMENTS = [0, 0, 0, 0];

function renderSummary() {
    const cells = (tag, cls) => `<${tag} class="${cls}"></${tag}>`.repeat(4);
    return $(`<div class="summary"><table>
        <thead>
            <tr class="r_rank"><th colspan="3"></th>${cells("td", "rank")}</tr>
            <tr class="r_player">${cells("th", "player")}</tr>
        </thead>
        <tbody class="body"><tr class="r_diff">
            <th class="jushu"></th><th class="changbang"></th><th class="last"></th>
            ${'<td class="back"><span class="diff"></span><span class="lizhi"></span></td>'.repeat(4)}
        </tr></tbody>
        <tfoot>
            <tr class="r_defen"><th colspan="3"></th>${cells("td", "defen")}</tr>
            <tr class="r_point"><th colspan="3"></th>${cells("td", "point")}</tr>
        </tfoot>
    </table></div>`);
}

function round(jushu, events) {
    return [{ qipai: { zhuangfeng: 0, jushu, changbang: 0 } }, ...events];
}

function createPaipu(log, { defen, gongtuo }) {
    return {
        player: PLAYERS,
        qijia: 0,
        defen,
        point: [40, 5, -15, -30],
        rank: [1, 2, 3, 4],
        gongtuo,
        log,
    };
}

function rowTexts(root, selector) {
    return root
        .find(selector)
        .map((i, row) =>
            $(row)
                .children()
                .map((j, cell) => $(cell).text())
                .get()
                .join("|"),
        )
        .get();
}

describe("summary", () => {
    it("nets each riichi deposit into its round and puts the sticks left at the end on their own row, so every column adds up to its final score", () => {
        const log = [
            round(0, [
                { dapai: { l: 1, p: "z1*" } },
                { zimo: { l: 2 } },
                { hule: { l: 0, baojia: 2, fenpei: [9000, 0, -8000, 0] } },
            ]),
            round(1, [
                { dapai: { l: 0, p: "z1*" } },
                { zimo: { l: 1 } },
                { pingju: { name: "荒牌平局", fenpei: [1500, -1500, -1500, 1500] } },
            ]),
        ];
        const root = renderSummary();

        summary(
            root,
            createPaipu(log, { defen: [36500, 24500, 15500, 23500], gongtuo: [1000, 0, 0, 0] }),
            0,
        );

        expect(rowTexts(root, ".r_rank")).toEqual(["|1位|2位|3位|4位"]);
        expect(rowTexts(root, ".r_diff")).toEqual([
            "東一局|0本場|ロン|+9,000|-1,000リ|-8,000|",
            "東二局|0本場|流局|+1,500|+500リ|-1,500|-1,500",
        ]);
        expect(rowTexts(root, ".r_gongtuo")).toEqual(["残り供託|+1,000|||"]);
    });

    it("marks a draw that moved no points with each seat's tenpai, or ±0 when the draw does not judge tenpai", () => {
        const log = [
            round(0, [
                {
                    pingju: {
                        name: "荒牌平局",
                        fenpei: NO_PAYMENTS,
                        tenpai: [true, true, true, true],
                    },
                },
            ]),
            round(0, [{ pingju: { name: "九種九牌", fenpei: NO_PAYMENTS, tenpai: null } }]),
        ];
        const root = renderSummary();

        summary(
            root,
            createPaipu(log, { defen: [25000, 25000, 25000, 25000], gongtuo: NO_PAYMENTS }),
            0,
        );

        expect(rowTexts(root, ".r_diff")).toEqual([
            "東一局|0本場|流局|テンパイ|テンパイ|テンパイ|テンパイ",
            "東一局|0本場|流局|±0|±0|±0|±0",
        ]);
        expect(root.find(".r_gongtuo")).toHaveLength(0);
    });
});
