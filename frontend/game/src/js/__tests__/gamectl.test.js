import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import page from "../../../index.html?raw";
import GameCtl from "../../vendor/majiang-ui/gamectl.js";

const PREF_KEY = "Majiang.pref.test";

function renderController() {
    const board = new DOMParser().parseFromString(page, "text/html").querySelector("#board");
    const root = $('<div id="board">').append(board.querySelector(".controller"));
    $(document.body).append(root, '<div class="outside">');
    return root;
}

function pressKey(key) {
    window.dispatchEvent(new KeyboardEvent("keydown", { key }));
}

beforeEach(() => {
    localStorage.clear();
});

afterEach(() => {
    $(window).off();
    $(document).off();
    document.body.innerHTML = "";
});

describe("Majiang.UI.GameCtl", () => {
    it("restores the stored sound setting, drops the removed speed setting, and toggles sound from the menu's switch", () => {
        localStorage.setItem(PREF_KEY, JSON.stringify({ sound_on: false, speed: 3 }));
        const root = renderController();
        const view = { sound_on: true };

        new GameCtl(root, PREF_KEY, view);
        const sound = root.find(".sound");
        expect(sound.attr("aria-checked")).toBe("false");
        expect(sound.find(".state").text()).toBe("OFF");
        expect(view.sound_on).toBe(false);

        sound.trigger("click");

        expect(sound.attr("aria-checked")).toBe("true");
        expect(sound.find(".state").text()).toBe("ON");
        expect(view.sound_on).toBe(true);
        expect(JSON.parse(localStorage.getItem(PREF_KEY))).toEqual({ sound_on: true });
    });

    it("opens the menu from the gear and closes it on Escape, returning focus to the gear, without passing the Escape on to a prompt", () => {
        const root = renderController();
        new GameCtl(root, PREF_KEY);
        const toggle = root.find(".settings-toggle");
        const menu = root.find(".settings-menu");
        let promptEscapes = 0;
        $(window).on("keydown", () => promptEscapes++);

        toggle.trigger("click");
        expect(menu.hasClass("hide")).toBe(false);
        expect(toggle.attr("aria-expanded")).toBe("true");

        root.find(".sound").trigger("focus");
        pressKey("Escape");

        expect(menu.hasClass("hide")).toBe(true);
        expect(toggle.attr("aria-expanded")).toBe("false");
        expect(document.activeElement).toBe(toggle[0]);
        expect(promptEscapes).toBe(0);
    });

    it("keeps its clicks from the board and closes on a click outside", () => {
        const root = renderController();
        new GameCtl(root, PREF_KEY);
        let boardClicks = 0;
        root.on("click", () => boardClicks++);
        const menu = root.find(".settings-menu");

        root.find(".settings-toggle").trigger("click");
        root.find(".sound").trigger("click");
        expect(menu.hasClass("hide")).toBe(false);
        expect(boardClicks).toBe(0);

        $(".outside").trigger("click");
        expect(menu.hasClass("hide")).toBe(true);
    });
});
