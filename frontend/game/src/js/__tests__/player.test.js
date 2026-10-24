import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";

const SELECTOR_HIDE_MS = 400;
const CHI_OPTIONS = ["m345-", "m45-6", "m5-67"];

function renderTile(p) {
    return $('<span class="pai">').attr("data-pai", p.slice(0, 2));
}

function createPlayer() {
    const root = $("<div>").append(
        '<div class="timer">',
        '<div class="player-button">',
        '<div class="select-mianzi">',
        '<div class="shoupai main"><div class="bingpai"></div></div>',
    );
    const player = new Majiang.UI.Player(root, renderTile, () => ({ play() {} }));
    return { player, selector: $(".select-mianzi", root) };
}

describe("Majiang.UI.Player", () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it("keeps a meld selector opened while an earlier clear's hide is pending", () => {
        const { player, selector } = createPlayer();
        player.clear_handler();

        player.select_mianzi(CHI_OPTIONS);
        vi.advanceTimersByTime(SELECTOR_HIDE_MS);
        expect(selector.hasClass("hide")).toBe(false);
        expect(selector.find(".mianzi")).toHaveLength(CHI_OPTIONS.length);

        player.clear_handler();
        vi.advanceTimersByTime(SELECTOR_HIDE_MS);
        expect(selector.hasClass("hide")).toBe(true);
    });
});
