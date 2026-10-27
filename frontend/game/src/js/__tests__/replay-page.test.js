import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";
import PAGE from "../../../index.html?raw";
import { showReplay } from "../replay/page.js";
import FULL_GAME from "./fixtures/replays/full_game.txt?raw";
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

describe("showReplay", () => {
    beforeEach(() => {
        document.body.className = "board";
        document.body.innerHTML = new DOMParser().parseFromString(PAGE, "text/html").body.innerHTML;
        vi.spyOn(console, "error").mockImplementation(() => {});
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

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
            step: expect.stringMatching(/^1\u00a0\/\u00a0\d+$/),
        });
        expect($(".replay-back").prop("disabled")).toBe(true);

        $(".replay-next").trigger("click");

        expect(label().step).toMatch(/^2\u00a0[/]/);
        expect($(".replay-back").prop("disabled")).toBe(false);
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
        expect(label().step).toMatch(/^(\d+)\u00a0\/\u00a0\1$/);
        expect(document.activeElement).toBe($(".replay-back")[0]);
    });
});
