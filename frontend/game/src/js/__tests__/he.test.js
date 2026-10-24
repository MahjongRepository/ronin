import $ from "jquery";
import { describe, expect, it } from "vitest";

import Majiang from "../../vendor/majiang-core/index.js";
import He from "../../vendor/majiang-ui/he.js";

function renderTile(p) {
    return $('<span class="pai">').attr("data-pai", p.slice(0, 2));
}

describe("Majiang.UI.He", () => {
    it("dims a tsumogiri discard on redraw but not a discard from the hand", () => {
        const river = new Majiang.He();
        river.dapai("m1");
        river.dapai("z4_");
        const node = $('<div class="he">').append('<div class="chouma">', '<div class="dapai">');

        new He(node, renderTile, river).redraw();

        const tiles = node.find(".pai");
        expect(tiles.eq(0).attr("data-pai")).toBe("m1");
        expect(tiles.eq(0).hasClass("mopai")).toBe(false);
        expect(tiles.eq(1).attr("data-pai")).toBe("z4");
        expect(tiles.eq(1).hasClass("mopai")).toBe(true);
    });
});
