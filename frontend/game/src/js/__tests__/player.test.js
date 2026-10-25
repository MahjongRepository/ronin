import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";

const SELECTOR_HIDE_MS = 400;
const CHI_OPTIONS = ["m345-", "m45-6", "m5-67"];
const BUTTONS =
    '<span class="button cansel">×</span><span class="button chi">チー</span><span class="button gang">カン</span>';

function renderTile(p) {
    return $('<span class="pai">').attr("data-pai", p.slice(0, 2));
}

function createPlayer() {
    const root = $("<div>").append(
        '<div class="timer">',
        `<div class="player-button">${BUTTONS}</div>`,
        '<div class="select-mianzi">',
        '<div class="shoupai main"><div class="bingpai"></div></div>',
    );
    const player = new Majiang.UI.Player(root, renderTile, () => ({ play() {} }));
    player._callback = vi.fn();
    return { player, root, selector: $(".select-mianzi", root) };
}

function offerCallPrompt(player) {
    player.set_button("chi", () => player.select_mianzi(CHI_OPTIONS));
    player.set_button("gang", () => player.callback({ fulou: "m5555-" }));
    player.show_button(() => player.callback());
}

function visibleButtons(root) {
    return $(".player-button .button", root)
        .not(".hide")
        .map((i, button) => $(button).text())
        .get();
}

function pressKey(key) {
    $(window).trigger($.Event("keyup", { key }));
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

    it("starts a call prompt's keyboard focus on × so Enter passes rather than calls", () => {
        const { player } = createPlayer();
        offerCallPrompt(player);

        pressKey("Enter");

        expect(player._callback).toHaveBeenCalledExactlyOnceWith(undefined);
    });

    it("backs out of a meld selector to the same call prompt, whose timeout then passes", () => {
        const { player, root, selector } = createPlayer();
        player.set_timer(1);
        offerCallPrompt(player);

        $(".player-button .chi", root).trigger("click");
        expect(visibleButtons(root)).toEqual([]);
        $(".back", selector).trigger("click");
        expect(visibleButtons(root)).toEqual(["×", "チー", "カン"]);

        $(".player-button .chi", root).trigger("click");
        pressKey("Escape");
        expect(visibleButtons(root)).toEqual(["×", "チー", "カン"]);

        vi.advanceTimersByTime(1200);
        expect(player._callback).toHaveBeenCalledExactlyOnceWith(undefined);
    });
});
