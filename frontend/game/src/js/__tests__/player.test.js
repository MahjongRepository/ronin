import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";
import RoninPlayer from "../ronin/player.js";

const SELECTOR_HIDE_MS = 400;
const DIALOG_READY_MS = 800;
const CHI_OPTIONS = ["m345-", "m45-6", "m5-67"];
const BUTTONS =
    '<span class="button cansel">×</span><span class="button chi">チー</span><span class="button gang">カン</span>' +
    '<span class="button rong">ロン</span><span class="button zimo">ツモ</span><span class="button pingju">流局</span>';

function renderTile(p) {
    return $('<span class="pai">').attr("data-pai", p.slice(0, 2));
}

function createPlayer(Player = Majiang.UI.Player) {
    const root = $("<div>").append(
        '<div class="timer">',
        `<div class="player-button">${BUTTONS}</div>`,
        '<div class="select-mianzi">',
        '<div class="shoupai main"><div class="bingpai"></div></div>',
        '<div class="hule-dialog"><button class="next" type="button">次へ</button></div>',
        '<div class="summary"><table></table><button class="exit" type="button">ロビーへ戻る</button></div>',
    );
    const player = new Player(root, renderTile, () => ({ play() {} }));
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

    it("starts a prompt's keyboard focus on its ツモ or ロン, else on ×, so Enter wins when it can and never calls", () => {
        const { player } = createPlayer();
        offerCallPrompt(player);
        pressKey("Enter");
        expect(player._callback).toHaveBeenLastCalledWith(undefined);

        player.set_button("gang", () => player.callback({ gang: "m1111" }));
        player.set_button("zimo", () => player.callback({ hule: "-" }));
        player.set_button("pingju", () => player.callback({ daopai: "-" }));
        player.show_button(() => player.select_dapai());
        pressKey("Enter");
        expect(player._callback).toHaveBeenLastCalledWith({ hule: "-" });

        player.set_button("chi", () => player.select_mianzi(CHI_OPTIONS));
        player.set_button("rong", () => player.callback({ hule: "-" }));
        player.show_button(() => player.callback());
        pressKey("Enter");
        expect(player._callback).toHaveBeenCalledTimes(3);
        expect(player._callback).toHaveBeenLastCalledWith({ hule: "-" });
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

    it("counts a turn's base time down beside its bank, then the bank alone", () => {
        const { player, root } = createPlayer();
        const timer = $(".timer", root);

        player.set_timer(5, 30);
        expect([timer.text(), timer.hasClass("bank")]).toEqual(["5+30", false]);
        vi.advanceTimersByTime(2000);
        expect(timer.text()).toBe("3+30");
        vi.advanceTimersByTime(3200);
        expect([timer.text(), timer.hasClass("bank")]).toEqual(["30", true]);

        player.set_timer(5, 0.2);
        expect([timer.text(), timer.hasClass("bank")]).toEqual(["5", false]);
    });

    it("hands a round result's keyboard focus to its 次へ button, which continues once", () => {
        const { player, root } = createPlayer();
        $(document.body).append(root);
        const next = $(".hule-dialog .next", root);

        player.action_hule();
        vi.advanceTimersByTime(DIALOG_READY_MS);
        expect(document.activeElement).toBe(next[0]);

        next.trigger("click");
        expect(player._callback).toHaveBeenCalledExactlyOnceWith(undefined);
        root.remove();
    });

    it("leaves the final standings only through its ロビーへ戻る button, which takes the focus and leaves once", () => {
        const { player, root } = createPlayer();
        $(document.body).append(root);
        const exit = $(".summary .exit", root);

        player.action_jieju();
        vi.advanceTimersByTime(DIALOG_READY_MS);
        expect(document.activeElement).toBe(exit[0]);

        $(".summary table", root).trigger("click");
        expect(player._callback).not.toHaveBeenCalled();
        exit.trigger("click");
        exit.trigger("click");
        expect(player._callback).toHaveBeenCalledExactlyOnceWith(undefined);
        root.remove();
    });
});

describe("RoninPlayer", () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it("stops a countdown that runs out at 0 and leaves the decision open, answering nothing, not even the riichi discard it would default to", () => {
        const { player, root } = createPlayer(RoninPlayer);
        $(".shoupai.main .bingpai", root).append(renderTile("m1"));
        player.countdown([1, 0]);
        player.select_dapai(["m1"]);

        vi.advanceTimersByTime(1200);
        expect(player._callback).not.toHaveBeenCalled();
        expect($(".timer", root).text()).toBe("0");
        $(".shoupai.main .pai", root).trigger("click");
        expect(player._callback).toHaveBeenCalledExactlyOnceWith({ dapai: "m1*" });
    });
});
