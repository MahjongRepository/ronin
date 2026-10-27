import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";
import PAGE from "../../../index.html?raw";
import { HOLD_DELAY_MS, HOLD_REPEAT_MS } from "../replay/controls.js";
import { showReplay } from "../replay/page.js";
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

beforeEach(() => {
    document.body.className = "board";
    document.body.innerHTML = new DOMParser().parseFromString(PAGE, "text/html").body.innerHTML;
    vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
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
            next: false,
            nextRound: false,
            last: false,
        });
        expect($(".replay-action").text()).toBe("Akagi deals");

        $(".replay-next").trigger("click");

        expect(label().step).toMatch(/^Step 2\u00a0[/]/);
        expect($(".replay-back").prop("disabled")).toBe(false);

        $(".replay-next-round").trigger("click");

        expect(label()).toMatchObject({
            round: "東二局 1本場",
            step: expect.stringMatching(/^Step 1\u00a0/),
        });
    });

    it("explains a replay it cannot load and links back, offering a retry after a failed load", async () => {
        stubFetch(new Response("", { status: 404 }));
        await showReplay("g-1", Promise.resolve());

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

    it("calls a replay it cannot draw damaged rather than failing the page", async () => {
        $("#loaddata").empty();

        await open(FULL_GAME);

        expect(problem().text).toBe("This replay file is damaged");
        expect(console.error).toHaveBeenCalled();
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
        expect(disabled()).toMatchObject({ next: true, nextRound: true, last: true });
        expect(document.activeElement).toBe($(".replay-back")[0]);
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
});
