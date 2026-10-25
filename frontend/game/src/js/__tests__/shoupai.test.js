import $ from "jquery";
import { afterEach, describe, expect, it } from "vitest";

import "../majiang.js";
import Majiang from "../../vendor/majiang-core/index.js";
import Shoupai from "../../vendor/majiang-ui/shoupai.js";

const SIDE_ROW_WIDTH = 554;

function drawRow({ bingpai, fulou }) {
    const root = $(
        '<div class="shoupai"><div class="bingpai"></div><div class="fulou"></div></div>',
    );
    root.css("width", `${SIDE_ROW_WIDTH}px`);
    $(document.body).append(root);
    const view = new Shoupai(root, () => $("<span>"), Majiang.Shoupai.fromString(""));
    const resize = (widths) => {
        $(".bingpai", root).css("width", `${widths.bingpai}px`);
        $(".fulou", root).css("width", `${widths.fulou}px`);
    };
    resize({ bingpai, fulou });
    return { fulou: $(".fulou", root), resize, view };
}

afterEach(() => {
    document.body.innerHTML = "";
});

describe("Majiang.UI.Shoupai adjust", () => {
    it("shrinks melds that push the hand past its row to fit beside it, and restores them once it fits", () => {
        const fourKans = { bingpai: 63, fulou: 540 };
        const { fulou, resize, view } = drawRow(fourKans);

        view.adjust();

        const scale = Number(fulou[0].style.transform.match(/^scale\((.+)\)$/)[1]);
        const marginLeft = parseFloat(fulou[0].style.marginLeft);
        expect(fourKans.bingpai + fourKans.fulou * scale).toBeCloseTo(SIDE_ROW_WIDTH);
        expect(fourKans.bingpai + fourKans.fulou + marginLeft).toBeCloseTo(SIDE_ROW_WIDTH);

        resize({ bingpai: 243, fulou: 210 });
        view.adjust();

        expect(fulou[0].style.transform).toBe("");
        expect(fulou[0].style.marginLeft).toBe("");
    });

    it("leaves melds on their own line unscaled", () => {
        const { fulou, view } = drawRow({ bingpai: 370, fulou: SIDE_ROW_WIDTH });

        view.adjust();

        expect(fulou[0].style.transform).toBe("");
    });
});
