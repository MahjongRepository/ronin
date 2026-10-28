import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";
import { setLocale } from "../../i18n/index.js";
import PAGE from "../../../index.html?raw";
import { finishLoading, loadTileImages, showLoadingError } from "../loading.js";
import startGame from "../ronin.js";
import { encode } from "../ronin/codec.js";
import wire from "../ronin/wire.js";
import { STORYBOOK_PAGE, storybookPath } from "../routes.js";
import { showStorybook } from "../storybook.js";

const PLAYERS = [0, 1, 2, 3].map((s) => ({ s, nm: `Player ${s}`, ai: s !== 0, sc: 250 }));
const TIMER_SETTINGS = { tb: 5, bk: 20, rb: 10, mb: 60, md: 5, ra: 5, gp: 3 };

beforeEach(() => {
    setLocale("ja");
    const page = new DOMParser().parseFromString(PAGE, "text/html");
    document.documentElement.innerHTML = page.documentElement.innerHTML;
    document.documentElement.className = page.documentElement.className;
});

afterEach(() => {
    window.dispatchEvent(new Event("pagehide"));
    $(window).off("resize");
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
    finishLoading();
    document.head.innerHTML = "";
    document.body.innerHTML = "";
});

describe("loading screen", () => {
    it("keeps the storybook preview visible after startup finishes with navigation available", () => {
        const markup = document.querySelector("#game-loading").innerHTML;
        showStorybook(STORYBOOK_PAGE.LOADING);
        finishLoading();
        expect(document.querySelector(".storybook-loading-preview .game-loading").innerHTML).toBe(
            markup,
        );
        expect(document.querySelector("#game-loading")).toBeNull();
        expect(document.querySelector("#board")).toBeNull();
        expect(document.querySelector(".storybook-nav .active").getAttribute("href")).toBe(
            storybookPath(STORYBOOK_PAGE.LOADING),
        );
        expect(
            document.querySelector(
                `.storybook-nav a[href="${storybookPath(STORYBOOK_PAGE.BOARD)}"]`,
            ),
        ).not.toBeNull();
        expect(document.documentElement.classList.contains("loading")).toBe(false);
    });

    it("hides preload tiles and the unfinished board before external styles arrive", () => {
        expect(getComputedStyle(document.querySelector("#loaddata")).display).toBe("none");
        expect(getComputedStyle(document.querySelector("#board")).visibility).toBe("hidden");
        const status = document.querySelector("#game-loading [role=status]");
        const shown = [...status.children].filter(
            (line) => getComputedStyle(line).display !== "none",
        );
        expect(shown.map((line) => [line.lang, line.textContent])).toEqual([["ja", "読み込み中…"]]);

        finishLoading();
        expect(document.querySelector("#game-loading")).toBeNull();
        expect(getComputedStyle(document.querySelector("#board")).visibility).not.toBe("hidden");
        expect(document.querySelectorAll("#loaddata img").length).toBeGreaterThan(0);
        expect(getComputedStyle(document.querySelector("#loaddata")).display).toBe("none");
    });

    it("waits for every tile to decode before allowing the page to start", async () => {
        const pending = Promise.withResolvers();
        const images = [...document.querySelectorAll("#loaddata img")];
        for (const image of images) {
            vi.spyOn(image, "decode").mockResolvedValue();
        }
        vi.mocked(images.at(-1).decode).mockReturnValue(pending.promise);
        const loaded = vi.fn();
        const loading = loadTileImages().then(loaded);
        await Promise.resolve();
        expect(loaded).not.toHaveBeenCalled();

        pending.resolve();
        await loading;
        expect(loaded).toHaveBeenCalledOnce();
    });

    it("shows an error instead of revealing an incomplete board when a tile fails", async () => {
        for (const image of document.querySelectorAll("#loaddata img")) {
            vi.spyOn(image, "decode").mockRejectedValue(new Error("Image unavailable"));
        }
        await expect(loadTileImages()).rejects.toThrow("Image unavailable");

        showLoadingError();
        expect(document.querySelector("#game-loading [role=status]").textContent).toBe(
            "読み込めませんでした。ページを再読み込みしてください。",
        );
        expect(document.querySelector("#game-loading .loading-dots")).toBeNull();
        expect(document.querySelector("#game-loading a").getAttribute("href")).toBe("/");
        expect(getComputedStyle(document.querySelector("#board")).visibility).toBe("hidden");
    });
});

function connectGame() {
    const sockets = [];
    vi.stubGlobal(
        "WebSocket",
        class {
            constructor() {
                sockets.push(this);
            }
            close() {}
        },
    );
    startGame("game", { wsUrl: "ws://localhost/game", gameTicket: "ticket" });
    return (message) => sockets[0].onmessage({ data: encode(message) });
}

describe("live game loading", () => {
    it("keeps loading until the server has supplied the game start screen", () => {
        const receive = connectGame();
        expect(document.querySelector("#game-loading")).not.toBeNull();

        receive({
            t: wire.E.GAME_STARTED,
            gid: "game",
            s: 0,
            dl: 0,
            gt: 0,
            p: PLAYERS,
            tm: TIMER_SETTINGS,
        });
        expect(document.querySelector("#game-loading")).toBeNull();
        expect($("#board .kaiju .player .main").text()).toBe("Player 0");
    });

    it("dismisses loading after restoring an existing game from a reconnect snapshot", () => {
        vi.useFakeTimers();
        const receive = connectGame();
        expect(document.querySelector("#game-loading")).not.toBeNull();

        receive({
            type: wire.SESSION.GAME_RECONNECTED,
            tm: TIMER_SETTINGS,
            rh: [],
            pst: PLAYERS,
            tr: 70,
            cp: 0,
            gid: "game",
            s: 0,
            dl: 0,
            gt: 0,
            p: PLAYERS,
            w: 0,
            n: 0,
            h: 0,
            r: 0,
            dd: [
                [1, 1],
                [1, 1],
            ],
            mt: [0, 4, 8, 36, 40, 44, 72, 76, 80, 108, 109, 112, 113],
            di: [132],
        });
        expect(document.querySelector("#game-loading")).toBeNull();
        expect($("#board .shoupai.main .bingpai img")).toHaveLength(13);
    });
});
