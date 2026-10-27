import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";
import PAGE from "../../../index.html?raw";
import { GAME_PREF_KEY } from "../game-prefs.js";
import { HOLD_DELAY_MS, HOLD_REPEAT_MS } from "../replay/controls.js";
import { REPLAY_PREFS_KEY } from "../replay/prefs.js";
import { showReplay } from "../replay/page.js";
import { withUnplayableDraw } from "./replay-edits.js";
import DOUBLE_RON from "./fixtures/replays/double_ron.txt?raw";
import FULL_GAME from "./fixtures/replays/full_game.txt?raw";
import RIICHI from "./fixtures/replays/riichi.txt?raw";
import TRUNCATED_AFTER_ROUND from "./fixtures/replays/truncated_after_round.txt?raw";

function stubFetch(response) {
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

function label() {
    return {
        round: $(".replay-round").text(),
        step: $(".replay-step").text(),
        ended: $(".replay-ended").text(),
    };
}

function disabled() {
    const buttons = {
        first: ".replay-first",
        prevRound: ".replay-prev-round",
        back: ".replay-back",
        play: ".replay-play",
        next: ".replay-next",
        nextRound: ".replay-next-round",
        last: ".replay-last",
    };
    return Object.fromEntries(
        Object.entries(buttons).map(([name, selector]) => [name, $(selector).prop("disabled")]),
    );
}

function problem() {
    return {
        text: $(".replay-problem h1").text(),
        links: $(".replay-problem a")
            .map((i, link) => $(link).attr("href"))
            .get(),
        board: $("#board").length,
    };
}

function open(text) {
    stubFetch(new Response(text));
    return showReplay("g-1", Promise.resolve());
}

function stepNumber() {
    return Number(label().step.match(/^Step (\d+)/)[1]);
}

function clickUntil(selector, done) {
    while (!done()) {
        $(selector).trigger("click");
    }
}

/** The board's hands drawn as tile backs, by their place at the table. */
function hiddenHands() {
    return ["main", "xiajia", "duimian", "shangjia"].filter(
        (place) => $(`#board .board > .shoupai.${place} .bingpai .pai[data-pai="_"]`).length > 0,
    );
}

function seatChoices() {
    return $(".replay-seat option")
        .map((i, option) => $(option).text())
        .get();
}

function loadPage() {
    $(window).off();
    $(document).off();
    document.body.className = "board";
    document.body.innerHTML = new DOMParser().parseFromString(PAGE, "text/html").body.innerHTML;
}

beforeEach(() => {
    loadPage();
    vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
    localStorage.clear();
    $(window).off();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
});

describe("showReplay", () => {
    it("shows the board at the deal of a loaded replay, from the first dealer's seat", async () => {
        await open(FULL_GAME);

        expect($("#board .player.main .name").text()).toBe("Akagi");
        expect(
            $("#board .board > .shoupai .bingpai")
                .map((i, hand) => $('.pai:not([data-pai="_"])', hand).length)
                .get(),
        ).toEqual([13, 13, 13, 13]);
        expect(label()).toMatchObject({
            round: "東一局 0本場",
            step: expect.stringMatching(/^Step 1\u00a0\/\u00a0\d+$/),
        });
        expect(disabled()).toEqual({
            first: true,
            prevRound: true,
            back: true,
            play: false,
            next: false,
            nextRound: false,
            last: false,
        });
        expect($(".replay-action").text()).toBe("Akagi deals");

        $(".replay-play").trigger("click");
        expect(label().step).toMatch(/^Step 2\u00a0[/]/);
        expect($(".replay-play").attr("aria-label")).toBe("Pause");
        expect($(".replay-action").attr("aria-busy")).toBe("true");
        $(".replay-next").trigger("click");

        expect($(".replay-play").attr("aria-label")).toBe("Play");
        expect($(".replay-action").attr("aria-busy")).toBeUndefined();
        expect(label().step).toMatch(/^Step 3\u00a0[/]/);
        expect($(".replay-back").prop("disabled")).toBe(false);

        $(".replay-next-round").trigger("click");

        expect(label()).toMatchObject({
            round: "東二局 1本場",
            step: expect.stringMatching(/^Step 1\u00a0/),
        });
    });

    it("explains a replay it cannot load and links back, offering a retry after a failed load", async () => {
        stubFetch(new Response("", { status: 404 }));
        await showReplay("g-1", Promise.reject(new Error("tile decode failed")));

        expect(problem()).toEqual({ text: "Replay not found", links: ["/history", "/"], board: 0 });

        stubFetch(new Response("", { status: 500 }));
        await showReplay("g-1", Promise.resolve());

        expect(problem()).toMatchObject({
            text: "Couldn't load the replay",
            links: [window.location.href, "/history", "/"],
        });
    });

    it("names the line of a replay the converter cannot read and logs why", async () => {
        const lines = FULL_GAME.split("\n");
        lines[4] = '{"t": 999}';

        await open(lines.join("\n"));

        expect(problem().text).toBe("This replay file is damaged (line 5)");
        const logged = console.error.mock.calls.flat();
        const damaged = logged.find((value) => value?.name === "MalformedReplayError");
        expect(logged).toContain(damaged.cause);
    });

    it("explains a game that ended before its first deal", async () => {
        await open(FULL_GAME.split("\n").slice(0, 2).join("\n"));

        expect(problem().text).toMatch(/before its first deal/);
    });

    it("says a replay it cannot draw couldn't be shown, offering a retry, rather than calling it damaged", async () => {
        $("#loaddata").empty();
        const observe = vi.spyOn(ResizeObserver.prototype, "observe");

        await open(FULL_GAME);

        expect(problem()).toMatchObject({
            text: "Couldn't show the replay",
            links: [window.location.href, "/history", "/"],
        });
        expect(console.error).toHaveBeenCalled();
        expect(observe).not.toHaveBeenCalled();
    });

    it("calls a replay damaged once a later position cannot be played, and logs why", async () => {
        await open(withUnplayableDraw(FULL_GAME));

        while (problem().text === "" && !$(".replay-next").prop("disabled")) {
            $(".replay-next").trigger("click");
        }

        expect(problem().text).toBe("This replay file is damaged");
        const logged = console.error.mock.calls.flat();
        const unplayable = logged.find((value) => value?.name === "UnplayableReplayError");
        expect(logged).toContain(unplayable.cause);
    });

    it("switches the sound shared with the live game from its gear, whose menu Escape closes, without the sound key", async () => {
        localStorage.setItem(GAME_PREF_KEY, JSON.stringify({ sound_on: true }));
        await open(FULL_GAME);

        window.dispatchEvent(new KeyboardEvent("keyup", { key: "a" }));
        expect(JSON.parse(localStorage.getItem(GAME_PREF_KEY))).toEqual({ sound_on: true });

        $(".controller .settings-toggle").trigger("click");
        $(".controller .sound").trigger("click");
        expect(JSON.parse(localStorage.getItem(GAME_PREF_KEY))).toEqual({ sound_on: false });
        expect($(".controller .sound").attr("title")).toBe("音声");
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
        expect($(".controller .settings-menu").hasClass("hide")).toBe(true);
    });

    it("says a truncated game ended early at its last position, keeping the keyboard focus in the strip", async () => {
        await open(TRUNCATED_AFTER_ROUND);
        $(".replay-next").trigger("focus");

        while (!$(".replay-next").prop("disabled")) {
            $(".replay-next").trigger("click");
        }

        expect(label()).toMatchObject({
            round: "東二局 1本場",
            ended: "The game ended here: the server stopped it",
        });
        expect(label().step).toMatch(/^Step (\d+)\u00a0\/\u00a0\1$/);
        expect(disabled()).toMatchObject({ play: true, next: true, nextRound: true, last: true });
        expect(document.activeElement).toBe($(".replay-back")[0]);
    });

    it("remembers the hidden-hands choice and the speed across a sound toggle, apart from the sound setting", async () => {
        await open(FULL_GAME);
        $(".replay-hide-hands").prop("checked", true).trigger("change");
        $(".replay-speed").val("fast").trigger("change");
        $(".controller .settings-toggle").trigger("click");
        $(".controller .sound").trigger("click");

        loadPage();
        await open(FULL_GAME);

        expect($(".replay-hide-hands").prop("checked")).toBe(true);
        expect($(".replay-speed").val()).toBe("fast");
        expect(hiddenHands()).toEqual(["xiajia", "duimian", "shangjia"]);
        expect(JSON.parse(localStorage.getItem(GAME_PREF_KEY))).toEqual({ sound_on: false });
        expect(JSON.parse(localStorage.getItem(REPLAY_PREFS_KEY))).toEqual({
            hideHands: true,
            speed: "fast",
        });
    });
});

describe("ReplayControls", () => {
    it("repeats next while held, stops at a result and steps once per click", async () => {
        await open(FULL_GAME);
        vi.useFakeTimers();
        const busy = () => $(".replay-action").attr("aria-busy") === "true";

        $(".replay-next").trigger("pointerdown");
        expect(stepNumber()).toBe(2);
        expect(busy()).toBe(true);
        vi.advanceTimersByTime(HOLD_DELAY_MS + HOLD_REPEAT_MS);
        expect(stepNumber()).toBe(4);
        $(window).trigger("pointerup");
        $(".replay-next").trigger("click");
        vi.advanceTimersByTime(10 * HOLD_REPEAT_MS);
        expect(stepNumber()).toBe(4);
        expect(busy()).toBe(false);

        $(".replay-next").trigger("click");
        expect(stepNumber()).toBe(5);

        $(".replay-next-round").trigger("click");
        $(".replay-next").trigger("pointerdown");
        vi.advanceTimersByTime(1000 * HOLD_REPEAT_MS);

        expect(label()).toMatchObject({
            round: "東二局 1本場",
            step: "Step 142\u00a0/\u00a0142",
        });
        expect($(".replay-action").text()).toBe("Exhaustive draw (荒牌平局)");
        expect(busy()).toBe(false);
    });

    it("names the last action, its Japanese marked as such", async () => {
        await open(RIICHI);

        clickUntil(".replay-next", () => stepNumber() === 13);
        expect($(".replay-action").text()).toBe("Alice: riichi, tsumogiri 中");
        expect($('.replay-action [lang="ja"]').text()).toBe("中");
        $(".replay-next").trigger("click");
        expect($(".replay-action").text()).toBe("Charlie: pon 中 ← Alice");
    });

    it("warns of a low wall below 8 tiles while the round is in play", async () => {
        await open(FULL_GAME);
        const warning = () =>
            $(".replay-wall-low").hasClass("hide") ? "" : $(".replay-wall-low").text();

        clickUntil(".replay-next", () => warning() !== "");
        expect(warning()).toBe("Wall low: 7 left");
        $(".replay-back").trigger("click");
        expect(warning()).toBe("");

        clickUntil(".replay-next", () => $(".replay-action").text().startsWith("Exhaustive"));
        expect(warning()).toBe("");
    });

    it("views the table from the picked seat or a nameplate at the same position, closing the options", async () => {
        await open(FULL_GAME);
        clickUntil(".replay-next", () => stepNumber() === 5);
        const action = $(".replay-action").text();
        const toggle = $(".replay-options-toggle");
        const optionsOpen = () => toggle.attr("aria-expanded") === "true";

        expect(seatChoices()).toEqual(["南 Wanjirou", "西 Ojisan", "北 Ichihime", "東 Akagi"]);
        expect($(".replay-seat").val()).toBe("3");
        expect(toggle.text()).toBe("View: Akagi · Normal▾");

        toggle.trigger("click");
        expect(optionsOpen()).toBe(true);
        $(".replay-seat").val("2").trigger("change");

        expect($("#board .player.main .name").text()).toBe("Ichihime");
        expect(stepNumber()).toBe(5);
        expect($(".replay-action").text()).toBe(action);
        expect(optionsOpen()).toBe(false);
        expect(toggle.text()).toBe("View: Ichihime · Normal▾");

        expect($("#board .board > .player.shangjia").attr("title")).toBe("View from Ojisan");
        $("#board .board > .player.shangjia").trigger("click");

        expect($("#board .player.main .name").text()).toBe("Ojisan");
        expect($(".replay-seat").val()).toBe("1");
        expect(stepNumber()).toBe(5);

        toggle.trigger("click");
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
        expect(optionsOpen()).toBe(false);
        toggle.trigger("click");
        $(".replay-next-round").trigger("click");
        expect(optionsOpen()).toBe(false);

        expect(seatChoices()).toEqual(["東 Wanjirou", "南 Ojisan", "西 Ichihime", "北 Akagi"]);
        expect($("#board .player.main .name").text()).toBe("Ojisan");
    });

    it("hides opponents' hands behind tile backs, and a result still reveals every winner's", async () => {
        await open(RIICHI);
        expect(hiddenHands()).toEqual([]);

        $(".replay-hide-hands").prop("checked", true).trigger("change");
        expect(hiddenHands()).toEqual(["xiajia", "duimian", "shangjia"]);
        const viewpoint = $("#board .player.main .name").text();
        clickUntil(".replay-next", () => /: draws/.test($(".replay-action").text()));
        expect($(".replay-action").text()).toMatch(new RegExp(`^${viewpoint}: draws \\S`));
        $(".replay-next").trigger("click");
        clickUntil(".replay-next", () => /: draws/.test($(".replay-action").text()));
        expect($(".replay-action").text()).toMatch(/^\S+: draws$/);

        vi.useFakeTimers();
        $(".replay-last").trigger("click");
        vi.runAllTimers();

        expect($(".replay-action").text()).toBe("Alice: tsumo 8,000");
        expect($("#board .player.xiajia .name").text()).toBe("Alice");
        expect(hiddenHands()).toEqual(["duimian", "shangjia"]);

        vi.useRealTimers();
        loadPage();
        await open(DOUBLE_RON);
        vi.useFakeTimers();
        $(".replay-last").trigger("click");
        vi.runAllTimers();

        expect(
            ["xiajia", "duimian"].map((place) => $(`#board .player.${place} .name`).text()),
        ).toEqual(["Alice", "Charlie"]);
        expect(hiddenHands()).toEqual(["shangjia"]);
    });
});
