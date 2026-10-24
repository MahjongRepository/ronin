import $ from "jquery";
import { afterEach, describe, expect, it } from "vitest";

import HuleDialog from "../../vendor/majiang-ui/dialog.js";

const SCORE_LINE =
    '<span class="feng"></span>: <span class="player"></span><span class="defen"></span><span class="diff"></span>';

function renderDialog() {
    const lines = ["main", "xiajia", "duimian", "shangjia"]
        .map((seat) => `<div class="${seat}">${SCORE_LINE}</div>`)
        .join("");
    return $(`<div class="hule-dialog">
        <div class="hule"><table class="hupai"><tr class="r_hupai"></tr><tr class="r_defen"></tr></table></div>
        <div class="pingju"></div>
        <div class="fenpei">${lines}</div>
    </div>`);
}

afterEach(() => {
    document.body.innerHTML = "";
});

describe("Majiang.UI.HuleDialog", () => {
    it("fills the score lines inside the dialog and leaves .diff cells elsewhere alone", () => {
        const standings = $(
            '<table class="summary"><tr><td class="main"><span class="defen">40,400</span><span class="diff plus">+7,000</span></td></tr></table>',
        );
        const root = renderDialog();
        $(document.body).append(standings, root);
        const model = {
            player_id: [0, 1, 2, 3],
            player: ["Ronin", "Bot 1", "Bot 2", "Bot 3"],
            defen: [31000, 21000, 20000, 28000],
        };

        new HuleDialog(root, null, model).pingju({ name: "荒牌平局", fenpei: [1500, -1500, 0, 0] });

        const main = root.find(".fenpei .main");
        expect(main.find(".feng").text()).toBe("東");
        expect(main.find(".defen").text()).toBe("31,000");
        expect(main.find(".diff").text()).toBe("+1,500");
        expect(main.find(".diff").hasClass("plus")).toBe(true);
        expect(root.find(".fenpei .xiajia .diff").hasClass("minus")).toBe(true);
        expect(standings.find(".defen").text()).toBe("40,400");
        expect(standings.find(".diff").text()).toBe("+7,000");
        expect(standings.find(".diff").hasClass("plus")).toBe(true);
    });
});
