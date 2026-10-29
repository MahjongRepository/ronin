import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";
import PAGE from "../../../index.html?raw";
import { GAME_PREF_KEY } from "../game-prefs.js";
import { finishLoading } from "../loading.js";
import { ROUNDS_IN_STRIP_MEDIA } from "../replay/rounds.js";
import { HOLD_DELAY_MS, HOLD_REPEAT_MS } from "../replay/hold.js";
import { parseReplay } from "../replay/load.js";
import { toReplay } from "../replay/paipu.js";
import wire from "../ronin/wire.js";
import { URL_WRITE_INTERVAL_MS, readPosition } from "../replay/position-url.js";
import { REPLAY_PREFS_KEY } from "../replay/prefs.js";
import { showReplay } from "../replay/page.js";
import {
    WHEEL_GESTURE_GAP_MS,
    WHEEL_START_PX,
    WHEEL_STEP_MS,
    WHEEL_STEP_PX,
} from "../replay/wheel.js";
import { withUnplayableDraw } from "./replay-edits.js";
import AI_REPLACEMENTS from "./fixtures/replays/ai_replacements.txt?raw";
import DOUBLE_RON from "./fixtures/replays/double_ron.txt?raw";
import EAGER_GAME from "./fixtures/replays/eager_game.txt?raw";
import FULL_GAME from "./fixtures/replays/full_game.txt?raw";
import RIICHI from "./fixtures/replays/riichi.txt?raw";
import TRUNCATED_AFTER_ROUND from "./fixtures/replays/truncated_after_round.txt?raw";
import { setLocale } from "../../i18n/index.js";

beforeEach(() => setLocale("en"));

function stubFetch(response) {
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

function label() {
    return {
        round: $(".replay-round").text(),
        step: $(".replay-step").text(),
        action: $(".replay-action").text(),
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

function toggleText() {
    return [$(".replay-options-view").text(), $(".replay-options-speed").text()];
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

const REPLAY_PATH = "/play/history/g-1";

function openAt(search) {
    window.history.replaceState(null, "", `${REPLAY_PATH}${search}`);
}

function addressQuery() {
    return window.location.search;
}

const START = "#game-loading .loading-start";

/** Turns of the microtask queue a load may take to offer its OK; waiting on timers would run earlier tests' leftovers. */
const LOAD_TURNS = 1000;

/** Start showing `text` as the replay, and wait until the loading screen offers its OK or the page settles without it. */
async function load(text) {
    stubFetch(new Response(text));
    let settled = false;
    const shown = showReplay("g-1", Promise.resolve()).finally(() => {
        settled = true;
    });
    for (let turns = 0; !settled && $(START).length === 0; turns += 1) {
        if (turns === LOAD_TURNS) {
            throw new Error(`the loading screen's OK: not offered after ${LOAD_TURNS} turns`);
        }
        await Promise.resolve();
    }
    return { shown };
}

/** Show `text` as the replay past its OK, the loading screen then gone as `main.js` removes it. */
async function open(text) {
    const { shown } = await load(text);
    $(START).trigger("click");
    await shown;
    finishLoading();
}

function stepNumber() {
    return Number(label().step.match(/^Step (\d+)/)[1]);
}

/** More tries than any replay has positions: a loop that reaches it has missed what it waits for. */
const MAX_TRIES = 1000;

/** Repeat `act` until `done`, failing with what it waited for once MAX_TRIES repeats have not got there. */
function repeatUntil(done, waitedFor, act) {
    for (let tries = 0; !done(); tries += 1) {
        if (tries === MAX_TRIES) {
            throw new Error(`${waitedFor}: not reached after ${MAX_TRIES} tries`);
        }
        act();
    }
}

function clickUntil(selector, done, waitedFor) {
    repeatUntil(done, waitedFor, () => $(selector).trigger("click"));
}

function clickNextUntilProblem() {
    clickUntil(".replay-next", () => problem().text !== "", "the replay's problem shown");
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

function press(key, init = {}, target = document.activeElement ?? document.body) {
    const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init });
    target.dispatchEvent(event);
    return event;
}

/** A key held down: its press, then `repeats` system repeats at the held button's pace. */
function hold(key, repeats) {
    press(key);
    for (let i = 0; i < repeats; i += 1) {
        vi.advanceTimersByTime(HOLD_REPEAT_MS);
        press(key, { repeat: true });
    }
}

function where() {
    return `${label().round} ${label().step}`;
}

const AT_LAST_STEP = /^Step (\d+)\u00a0\/\u00a0\1$/;

function isBusy() {
    return $(".replay-action").attr("aria-busy") === "true";
}

/** Whether the panel the toggle at `selector` opens is open. */
function isExpanded(selector) {
    return $(selector).attr("aria-expanded") === "true";
}

beforeEach(() => {
    openAt("");
    loadPage();
    vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
    localStorage.clear();
    $(window).trigger("pagehide").off();
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
            round: "East 1, 0 honba",
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
        expect($(".replay-action").text()).toBe("Dealer: Akagi");

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
            round: "East 2, 1 honba",
            step: expect.stringMatching(/^Step 1\u00a0/),
        });
    });

    it("holds a loaded replay behind the loading screen's focused OK, ignoring keys and the wheel, unless sound is off", async () => {
        openAt("?seat=1&round=2&step=5");
        const { shown } = await load(FULL_GAME);

        expect(document.activeElement).toBe($(START)[0]);
        expect($("#game-loading [role=status]").text()).toBe("Replay loaded");
        press("ArrowRight");
        $("#board")[0].dispatchEvent(
            new WheelEvent("wheel", {
                deltaY: 100,
                deltaMode: WheelEvent.DOM_DELTA_LINE,
                bubbles: true,
            }),
        );
        expect($(".replay-controls")).toHaveLength(0);
        expect(addressQuery()).toBe("?seat=1&round=2&step=5");

        $(START).trigger("click");
        await shown;

        loadPage();
        localStorage.setItem(GAME_PREF_KEY, JSON.stringify({ sound_on: false }));
        await (
            await load(FULL_GAME)
        ).shown;

        expect($(START)).toHaveLength(0);
        expect($(".replay-controls")).toHaveLength(1);
    });

    it("explains a replay it cannot load in the loading screen's layout and links back, offering a retry after a failed load", async () => {
        vi.useFakeTimers();
        stubFetch(new Response("", { status: 404 }));
        const shown = showReplay("g-1", Promise.reject(new Error("tile decode failed")));
        await vi.advanceTimersByTimeAsync(0);

        expect($("#game-loading [role=status]").text()).toBe("Waiting for the replay…");
        await vi.runAllTimersAsync();
        await shown;
        expect(problem()).toEqual({ text: "Replay not found", links: ["/history", "/"], board: 0 });
        finishLoading();
        expect($(".game-loading.replay-problem h1").text()).toBe("Replay not found");

        stubFetch(new Response("", { status: 500 }));
        await showReplay("g-1", Promise.resolve());

        expect(problem()).toMatchObject({
            text: "Couldn't load the replay",
            links: [window.location.href, "/history", "/"],
        });
    });

    it.each([
        ["a record of an unknown type", () => ({ t: 999 })],
        [
            "an exhaustive draw without its tenpai seats",
            (roundEnd) => ({ ...roundEnd, ts: undefined }),
        ],
    ])(
        "names the line of a replay the converter cannot read and logs why: %s",
        async (_, damage) => {
            const lines = FULL_GAME.split("\n");
            const index = lines.findIndex(
                (line) => line.trim() !== "" && JSON.parse(line).rt === wire.RT.EXHAUSTIVE,
            );
            lines[index] = JSON.stringify(damage(JSON.parse(lines[index])));

            await open(lines.join("\n"));

            expect(problem().text).toBe(`This replay file is damaged (line ${index + 1})`);
            const logged = console.error.mock.calls.flat();
            const damaged = logged.find((value) => value?.name === "MalformedReplayError");
            expect(logged).toContain(damaged.cause);
        },
    );

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

    it("offers the replay from its start beside a retry when a position past the first deal cannot be drawn", async () => {
        openAt("?seat=1&round=2&step=5");
        await open(FULL_GAME);
        vi.spyOn(Majiang.UI.Board.prototype, "update").mockImplementation(() => {
            throw new Error("the board cannot draw this");
        });

        $(".replay-next").trigger("click");

        expect(problem()).toMatchObject({
            text: "Couldn't show the replay",
            links: [window.location.href, `${REPLAY_PATH}?seat=1`, "/history", "/"],
        });
        expect(window.location.search).toBe("?seat=1&round=2&step=5");
    });

    it("calls a replay damaged once a later position cannot be played, and logs why", async () => {
        await open(withUnplayableDraw(FULL_GAME));

        clickNextUntilProblem();

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
        expect($(".controller .sound").attr("title")).toBe("Sound");
        press("Escape");
        expect($(".controller .settings-menu").hasClass("hide")).toBe(true);
    });

    it.each([
        [
            "a storage that refuses access",
            () => {
                const blocked = () => {
                    throw new DOMException("site data blocked", "SecurityError");
                };
                vi.spyOn(Storage.prototype, "getItem").mockImplementation(blocked);
                vi.spyOn(Storage.prototype, "setItem").mockImplementation(blocked);
            },
        ],
        ["a sound setting that is not JSON", () => localStorage.setItem(GAME_PREF_KEY, "{")],
    ])("shows the replay with the sound on despite %s", async (_, breakStorage) => {
        vi.spyOn(console, "warn").mockImplementation(() => {});
        breakStorage();

        await open(FULL_GAME);

        expect(problem().text).toBe("");
        expect(label().step).toMatch(/^Step 1\u00a0/);
        expect($(".controller .sound").attr("aria-checked")).toBe("true");
    });

    it("says a truncated game ended early at its last position, keeping the keyboard focus in the strip", async () => {
        await open(TRUNCATED_AFTER_ROUND);
        $(".replay-next").trigger("focus");

        clickUntil(".replay-next", () => $(".replay-next").prop("disabled"), "Next disabled");

        expect(label()).toMatchObject({
            round: "East 2, 1 honba",
            ended: "Ended early: the server stopped the game",
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

        $(".replay-next").trigger("pointerdown");
        expect(stepNumber()).toBe(2);
        expect(isBusy()).toBe(true);
        vi.advanceTimersByTime(HOLD_DELAY_MS + HOLD_REPEAT_MS);
        expect(stepNumber()).toBe(4);
        $(window).trigger("pointerup");
        $(".replay-next").trigger("click");
        vi.advanceTimersByTime(10 * HOLD_REPEAT_MS);
        expect(stepNumber()).toBe(4);
        expect(isBusy()).toBe(false);

        $(".replay-next").trigger("click");
        expect(stepNumber()).toBe(5);

        $(".replay-next-round").trigger("click");
        $(".replay-next").trigger("pointerdown");
        vi.advanceTimersByTime(1000 * HOLD_REPEAT_MS);

        expect(label()).toMatchObject({
            round: "East 2, 1 honba",
            step: "Step 142\u00a0/\u00a0142",
        });
        expect($(".replay-action").text()).toBe("Exhaustive draw: all noten (荒牌平局)");
        expect(isBusy()).toBe(false);
    });

    it("steps on a click with no press before it after a press that disabled its own button", async () => {
        await open(FULL_GAME);
        $(".replay-last").trigger("click");
        $(".replay-back").trigger("click");

        $(".replay-next").trigger("pointerdown");
        expect(label().action).toBe("Final standings");
        expect(disabled().next).toBe(true);
        $(window).trigger("pointerup");
        $(".replay-back").trigger("click");
        $(".replay-next").trigger("click");

        expect(label().action).toBe("Final standings");
    });

    it("names the last action in the page's language, each tile by its visible name", async () => {
        await open(RIICHI);

        clickUntil(".replay-next", () => stepNumber() === 13, "step 13");
        expect($(".replay-action").text()).toBe("Alice: riichi, tsumogiri Chun");
        expect($('.replay-action [lang="ja"]')).toHaveLength(0);
        $(".replay-next").trigger("click");
        expect($(".replay-action").text()).toBe("Charlie: pon Chun ← Alice");
    });

    it("warns of a low wall below 8 tiles while the round is in play", async () => {
        await open(FULL_GAME);
        const warning = () =>
            $(".replay-wall-low").hasClass("hide") ? "" : $(".replay-wall-low").text();

        clickUntil(".replay-next", () => warning() !== "", "the low-wall warning");
        expect(warning()).toBe("Wall low: 7 left");
        $(".replay-back").trigger("click");
        expect(warning()).toBe("");

        clickUntil(
            ".replay-next",
            () => $(".replay-action").text().startsWith("Exhaustive"),
            "the exhaustive draw",
        );
        expect(warning()).toBe("");
    });

    it("views the table from the picked seat or a nameplate at the same position, closing the options", async () => {
        await open(FULL_GAME);
        clickUntil(".replay-next", () => stepNumber() === 5, "step 5");
        const action = $(".replay-action").text();
        const toggle = $(".replay-options-toggle");

        expect(seatChoices()).toEqual([
            "Wanjirou (South)",
            "Ojisan (West)",
            "Ichihime (North)",
            "Akagi (East)",
        ]);
        expect($(".replay-seat").val()).toBe("3");
        expect(toggleText()).toEqual(["View: Akagi", "Normal"]);

        toggle.trigger("click");
        expect(isExpanded(".replay-options-toggle")).toBe(true);
        $(".replay-seat").trigger("focus").trigger("pointerdown");
        press("ArrowDown");
        $(".replay-seat").val("2").trigger("change");
        expect(document.activeElement).toBe($(".replay-seat")[0]);

        expect($("#board .player.main .name").text()).toBe("Ichihime");
        expect(stepNumber()).toBe(5);
        expect($(".replay-action").text()).toBe(action);
        expect(isExpanded(".replay-options-toggle")).toBe(false);
        expect(toggleText()).toEqual(["View: Ichihime", "Normal"]);

        expect($("#board .board > .player.shangjia").attr("title")).toBe("View from Ojisan");
        $("#board .board > .player.shangjia").trigger("click");

        expect($("#board .player.main .name").text()).toBe("Ojisan");
        expect($(".replay-seat").val()).toBe("1");
        expect(stepNumber()).toBe(5);

        $(".replay-speed").trigger("focus").trigger("pointerdown").val("fast").trigger("change");
        expect(document.activeElement).not.toBe($(".replay-speed")[0]);

        toggle.trigger("click");
        press("Escape");
        expect(isExpanded(".replay-options-toggle")).toBe(false);
        toggle.trigger("click");
        $(".replay-next-round").trigger("click");
        expect(isExpanded(".replay-options-toggle")).toBe(false);

        expect(seatChoices()).toEqual([
            "Wanjirou (East)",
            "Ojisan (South)",
            "Ichihime (West)",
            "Akagi (North)",
        ]);
        expect($("#board .player.main .name").text()).toBe("Ojisan");
    });

    it("jumps from the round list to the picked round's deal, pausing autoplay, and marks the round shown", async () => {
        await open(EAGER_GAME);
        const toggle = $(".replay-rounds-toggle");
        const entries = () => $(".replay-round-entry");
        const current = () => entries().index($('.replay-round-entry[aria-current="true"]'));

        expect(entries().length).toBe(9);
        expect(entries().eq(2).text()).toBe(
            "East 2, 1 honbaRon: Charlie from Alice 1,300 (+300 honba)",
        );
        expect(toggle.attr("aria-label")).toBe("Round list, East 1, 0 honba");
        toggle.trigger("click");
        expect(toggle.attr("aria-expanded")).toBe("true");
        expect(toggle.text()).toBe("East 1, 0 honba · Rounds▴");
        expect(document.activeElement).toBe(entries()[0]);

        $(".replay-play").trigger("click");
        entries().eq(3).trigger("click");

        expect(label()).toMatchObject({
            round: "East 3, 0 honba",
            step: expect.stringMatching(/^Step 1\u00a0/),
        });
        expect($(".replay-play").attr("aria-label")).toBe("Play");
        expect(toggle.attr("aria-expanded")).toBe("true");
        expect(current()).toBe(3);
        $(".replay-next-round").trigger("click");
        expect(current()).toBe(4);

        entries().eq(4).trigger("focus");
        press("Escape");
        expect(toggle.attr("aria-expanded")).toBe("false");
        expect(document.activeElement).toBe(toggle[0]);

        vi.useFakeTimers();
        $(".replay-last").trigger("click");
        vi.runAllTimers();
        $(".summary .replay-summary-round").eq(1).trigger("click");
        expect(label().round).toBe("East 2, 0 honba");
        expect(document.activeElement).toBe(toggle[0]);
    });

    it("closes the round list on a pick or a move where it takes the info's place", async () => {
        vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
            matches: query === ROUNDS_IN_STRIP_MEDIA,
            addEventListener: () => {},
        }));
        await open(EAGER_GAME);
        const toggle = $(".replay-rounds-toggle");

        toggle.trigger("click");
        $(".replay-round-entry").eq(2).trigger("click");
        expect(isExpanded(".replay-rounds-toggle")).toBe(false);
        expect(document.activeElement).toBe(toggle[0]);

        toggle.trigger("click");
        $(".replay-next").trigger("click");
        expect(isExpanded(".replay-rounds-toggle")).toBe(false);
    });

    it("opens the help over the gear's menu and the round list, Escape closing one layer at a time", async () => {
        await open(EAGER_GAME);
        const helpOpen = () => isExpanded(".replay-help-toggle");
        const gearOpen = () => !$(".controller .settings-menu").hasClass("hide");

        $(".replay-rounds-toggle").trigger("click");
        $(".controller .settings-toggle").trigger("click");
        press("?", { shiftKey: true });
        expect([helpOpen(), gearOpen(), isExpanded(".replay-rounds-toggle")]).toEqual([
            true,
            false,
            false,
        ]);
        expect(document.activeElement).toBe($(".replay-help-body")[0]);
        expect($(".replay-help dt").first().text()).toBe("← →");
        expect($(".replay-help").text()).toContain("Round list:");

        press("Escape", { repeat: true });
        expect(helpOpen()).toBe(true);
        press("Escape");
        expect(helpOpen()).toBe(false);
        expect(document.activeElement).toBe($(".replay-rounds-toggle")[0]);

        $(".replay-help-toggle").trigger("click");
        $(".controller .settings-toggle").trigger("click");
        press("Escape");
        expect([helpOpen(), gearOpen()]).toEqual([true, false]);
        press("Escape");
        expect(helpOpen()).toBe(false);

        $(".replay-help-toggle").trigger("click");
        $("#board .board")[0].dispatchEvent(new Event("pointerdown", { bubbles: true }));
        expect(helpOpen()).toBe(false);
        $(".replay-help-toggle").trigger("click");
        $(".controller .settings-toggle").trigger("focus");
        expect(helpOpen()).toBe(false);
    });

    it("hides opponents' hands behind tile backs, and a result still reveals every winner's", async () => {
        await open(RIICHI);
        expect(hiddenHands()).toEqual([]);

        $(".replay-hide-hands").prop("checked", true).trigger("change");
        expect(hiddenHands()).toEqual(["xiajia", "duimian", "shangjia"]);
        const viewpoint = $("#board .player.main .name").text();
        clickUntil(".replay-next", () => /: draws/.test($(".replay-action").text()), "a draw");
        expect($(".replay-action").text()).toMatch(new RegExp(`^${viewpoint}: draws \\S`));
        $(".replay-next").trigger("click");
        clickUntil(".replay-next", () => /: draws/.test($(".replay-action").text()), "a draw");
        expect($(".replay-action").text()).toMatch(/^\S+: draws$/);

        vi.useFakeTimers();
        $(".replay-last").trigger("click");
        vi.runAllTimers();

        expect($(".replay-action").text()).toBe("Tsumo: Alice 8,000 (2,000/4,000)");
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

describe("BoardLinks", () => {
    it.each([
        ["no page", "", "/history", "Back to history"],
        ["the game history", "/history?page=2", "/history?page=2", "Back to history"],
        [
            "the finished game's page, which 牌譜を見る replaced",
            "/play/g-1",
            "/history",
            "Back to history",
        ],
        ["a game client page no route names", "/play/a/b", "/history", "Back to history"],
        ["another lobby page", "/rooms", "/rooms", "Back"],
    ])(
        "leaves the final standings for the lobby page the replay was opened from: %s",
        async (_, referrer, exit, text) => {
            const origin = window.location.origin;
            vi.spyOn(document, "referrer", "get").mockReturnValue(
                referrer === "" ? "" : `${origin}${referrer}`,
            );
            const assign = vi.spyOn(window.location, "assign").mockImplementation(() => {});
            await open(FULL_GAME);
            $(".replay-last").trigger("click");

            expect($("#board .summary .exit").text()).toBe(text);
            $("#board .summary .exit").trigger("click");
            expect(assign).toHaveBeenCalledWith(exit === "/history" ? exit : `${origin}${exit}`);
        },
    );

    it("titles each nameplate with the view it offers, and an AI-held seat's with what its mark means", async () => {
        await open(AI_REPLACEMENTS);
        const title = (place) => $(`#board .board > .player.${place}`).attr("title");

        expect(["main", "xiajia", "duimian", "shangjia"].map(title)).toEqual([
            "Diana",
            "View from Alice",
            "View from Charlie",
            "View from Bob (AI plays this seat)",
        ]);
        $("#board .board > .player.shangjia").trigger("click");
        expect(title("main")).toBe("Bob (AI plays this seat)");
    });
});

describe("bindKeys", () => {
    it("steps, jumps, plays and turns the table from the keyboard", async () => {
        await open(FULL_GAME);
        vi.useFakeTimers();

        press("ArrowRight");
        expect(stepNumber()).toBe(2);
        press("ArrowLeft");
        expect(stepNumber()).toBe(1);

        press("ArrowDown");
        press("PageDown");
        expect(where()).toMatch(/^East 3, \d honba Step 1\u00a0/);
        press("ArrowUp");
        expect(where()).toMatch(/^East 2, 1 honba Step 1\u00a0/);
        press("End");
        expect(label().action).toBe("Final standings");
        press("Home");
        expect(where()).toMatch(/^East 1, 0 honba Step 1\u00a0/);

        press(" ");
        expect($(".replay-play").attr("aria-label")).toBe("Pause");
        press(" ");
        expect($(".replay-play").attr("aria-label")).toBe("Play");

        press("v");
        expect($(".replay-seat").val()).toBe("0");
        press("м", { code: "KeyV" });
        expect($(".replay-seat").val()).toBe("1");
        press("H");
        expect(hiddenHands()).toEqual(["xiajia", "duimian", "shangjia"]);
    });

    it("repeats a held arrow at the held button's pace, stopping at a result until pressed afresh", async () => {
        await open(FULL_GAME);
        vi.useFakeTimers();

        press("ArrowRight");
        press("ArrowRight", { repeat: true });
        expect(stepNumber()).toBe(2);
        hold("ArrowRight", 3);
        expect(stepNumber()).toBe(6);
        expect(isBusy()).toBe(true);

        hold("ArrowRight", 1000);
        expect(label()).toMatchObject({ round: "East 1, 0 honba", step: AT_LAST_STEP });
        expect(isBusy()).toBe(false);
        press("ArrowRight");
        expect(where()).toMatch(/^East 2, 1 honba Step 1\u00a0/);

        press("ArrowRight");
        press("ArrowRight");
        hold("ArrowLeft", 50);
        expect(label()).toMatchObject({ round: "East 1, 0 honba", step: AT_LAST_STEP });
    });

    it("leaves keys to form fields, focused buttons and switches, modified presses and the round list", async () => {
        await open(EAGER_GAME);
        vi.useFakeTimers();

        const seat = $(".replay-seat").val();
        $(".replay-seat").trigger("focus");
        press("ArrowRight");
        press("v");
        expect(stepNumber()).toBe(1);
        expect($(".replay-seat").val()).toBe(seat);
        $(".replay-seat").trigger("blur");

        for (const modifier of ["ctrlKey", "altKey", "metaKey", "shiftKey"]) {
            expect(press("ArrowRight", { [modifier]: true }, document.body).defaultPrevented).toBe(
                false,
            );
        }
        expect(stepNumber()).toBe(1);

        $(".replay-next").trigger("focus");
        expect(press(" ").defaultPrevented).toBe(false);
        expect($(".replay-play").attr("aria-label")).toBe("Play");

        $(".replay-hide-hands").trigger("focus");
        expect(press(" ").defaultPrevented).toBe(false);
        press("ArrowRight");
        expect(stepNumber()).toBe(2);

        $(".replay-rounds-toggle").trigger("click");
        press("ArrowDown");
        press("ArrowDown");
        expect(document.activeElement).toBe($(".replay-round-entry")[2]);
        press("End");
        expect(document.activeElement).toBe($(".replay-round-entry").last()[0]);
        press("PageUp");
        expect(stepNumber()).toBe(2);
        press("ArrowRight");
        expect(stepNumber()).toBe(3);
    });

    it("lets the keys go once the replay fails, leaving the problem page alone", async () => {
        await open(withUnplayableDraw(FULL_GAME));
        clickNextUntilProblem();

        expect(press("h", {}, document.body).defaultPrevented).toBe(false);
        expect(press(" ", {}, document.body).defaultPrevented).toBe(false);
        expect(localStorage.getItem(REPLAY_PREFS_KEY)).toBeNull();
    });
});

describe("bindWheel", () => {
    function wheelOver(element, deltaY, { deltaMode = 0, ctrlKey = false } = {}) {
        const event = new WheelEvent("wheel", {
            deltaY,
            deltaMode,
            bubbles: true,
            cancelable: true,
        });
        Object.defineProperty(event, "ctrlKey", { value: ctrlKey });
        element.dispatchEvent(event);
        return event;
    }

    const wheel = (deltaY, init) => wheelOver($("#board .board")[0], deltaY, init);

    it("steps once per notch over the board, not on a graze, a continuous scroll stopping at a result", async () => {
        await open(FULL_GAME);
        vi.useFakeTimers();

        expect(wheel(WHEEL_START_PX / 2).defaultPrevented).toBe(true);
        expect(stepNumber()).toBe(1);
        wheel(WHEEL_START_PX / 2);
        expect(stepNumber()).toBe(2);

        vi.advanceTimersByTime(WHEEL_GESTURE_GAP_MS);
        wheel(WHEEL_STEP_PX);
        expect(stepNumber()).toBe(3);
        wheel(WHEEL_STEP_PX);
        expect(stepNumber()).toBe(3);
        vi.advanceTimersByTime(WHEEL_STEP_MS);
        wheel(WHEEL_STEP_PX / 2);
        expect(stepNumber()).toBe(3);
        wheel(WHEEL_STEP_PX / 2);
        expect(stepNumber()).toBe(4);

        vi.advanceTimersByTime(WHEEL_GESTURE_GAP_MS);
        wheel(-1, { deltaMode: WheelEvent.DOM_DELTA_LINE });
        expect(stepNumber()).toBe(3);
        vi.advanceTimersByTime(WHEEL_STEP_MS);
        wheel(-1, { deltaMode: WheelEvent.DOM_DELTA_LINE });
        expect(stepNumber()).toBe(2);

        vi.advanceTimersByTime(WHEEL_GESTURE_GAP_MS);
        repeatUntil(
            () => AT_LAST_STEP.test(label().step),
            "the round's last step",
            () => {
                vi.advanceTimersByTime(WHEEL_STEP_MS);
                wheel(WHEEL_STEP_PX);
            },
        );
        for (let i = 0; i < 10; i += 1) {
            vi.advanceTimersByTime(WHEEL_STEP_MS);
            wheel(WHEEL_STEP_PX);
        }
        expect(label().round).toBe("East 1, 0 honba");
        vi.advanceTimersByTime(WHEEL_GESTURE_GAP_MS);
        wheel(WHEEL_STEP_PX);
        expect(label().round).toBe("East 2, 1 honba");
    });

    it("leaves a pinch, a box that scrolls and the help's own scrolling to the browser", async () => {
        await open(FULL_GAME);
        vi.useFakeTimers();

        expect(wheel(WHEEL_STEP_PX, { ctrlKey: true }).defaultPrevented).toBe(false);
        expect(stepNumber()).toBe(1);

        $(".replay-help-toggle").trigger("click");
        expect(wheelOver($(".replay-help-body")[0], WHEEL_STEP_PX).defaultPrevented).toBe(false);
        expect(stepNumber()).toBe(1);

        $(".replay-last").trigger("click");
        vi.runAllTimers();
        const standings = $("#board .summary").css("overflow-y", "auto")[0];
        let contentHeight = 1000;
        Object.defineProperty(standings, "scrollHeight", { get: () => contentHeight });
        Object.defineProperty(standings, "clientHeight", { value: 100 });
        expect(wheelOver($(".row-diff", standings)[0], -WHEEL_STEP_PX).defaultPrevented).toBe(
            false,
        );
        expect(label().action).toBe("Final standings");

        contentHeight = 102;
        vi.advanceTimersByTime(WHEEL_GESTURE_GAP_MS);
        expect(wheelOver($(".row-diff", standings)[0], -WHEEL_STEP_PX).defaultPrevented).toBe(true);
        expect(label().action).not.toBe("Final standings");
    });
});

describe("readPosition", () => {
    const replay = toReplay(parseReplay(FULL_GAME));
    const dealer = replay.qijia;

    it.each([
        ["a valid position", "?seat=1&round=2&step=5", { seat: 1, round: 2, step: 5 }],
        ["a seat off the table", "?seat=4&round=1&step=2", { seat: dealer, round: 1, step: 2 }],
        ["a repeated seat", "?seat=1&seat=2&round=1&step=2", { seat: dealer, round: 1, step: 2 }],
        ["no round, ignoring the step", "?step=3", { seat: dealer, round: 0, step: 0 }],
        ["a round not a whole number", "?round=1.0&step=3", { seat: dealer, round: 0, step: 0 }],
        ["a round past the game", "?round=99&step=3", { seat: dealer, round: 0, step: 0 }],
        ["a step past the round", "?round=1&step=999", { seat: dealer, round: 1, step: 0 }],
    ])("falls back part by part: %s", (_, search, position) => {
        expect(readPosition(search, replay)).toEqual(position);
    });
});

describe("PositionUrl", () => {
    it("opens paused at the URL's seat and position, the standings at the last round's last step, marked as a table", async () => {
        openAt("?seat=1&round=2&step=5");
        await open(FULL_GAME);

        expect($("#board .player.main .name").text()).toBe("Ojisan");
        expect(label()).toMatchObject({
            round: "East 3, 2 honba",
            step: expect.stringMatching(/^Step 6\u00a0/),
        });
        expect($(".replay-play").attr("aria-label")).toBe("Play");
        expect(addressQuery()).toBe("?seat=1&round=2&step=5");

        const { rounds } = toReplay(parseReplay(FULL_GAME));
        const lastRound = rounds.length - 1;
        loadPage();
        openAt(`?round=${lastRound}&step=${rounds[lastRound].positions.length - 1}`);
        await open(FULL_GAME);

        expect(label()).toMatchObject({ action: "Final standings", step: "" });
        expect($(".replay-step").hasClass("hide")).toBe(true);
        const roles = (row) =>
            $(row)
                .children()
                .map((_, cell) => cell.getAttribute("role"))
                .get();
        expect(roles("#board .summary .row-player")).toEqual(Array(4).fill("columnheader"));
        expect(roles($("#board .summary .row-diff").last())).toEqual([
            ...Array(3).fill("rowheader"),
            ...Array(4).fill("cell"),
        ]);
        expect($("#board .summary .row-rank .title").attr("aria-rowspan")).toBe("2");
    });

    it("writes a bad query's fallback into the address bar, dropping anything else", async () => {
        openAt("?seat=9&round=1&step=999&x=1");
        await open(FULL_GAME);

        expect(addressQuery()).toBe("?seat=3&round=1&step=0");
    });

    it("replaces the URL on each move and seat change, at most once per interval, keeping the position on a seat change", async () => {
        vi.useFakeTimers();
        await open(FULL_GAME);
        const historyLength = window.history.length;
        expect(addressQuery()).toBe("?seat=3&round=0&step=0");

        $(".replay-next").trigger("click");
        $(".replay-next").trigger("click");
        expect(addressQuery()).toBe("?seat=3&round=0&step=0");
        vi.advanceTimersByTime(URL_WRITE_INTERVAL_MS);
        expect(addressQuery()).toBe("?seat=3&round=0&step=2");

        vi.advanceTimersByTime(URL_WRITE_INTERVAL_MS);
        $(".replay-seat").val("1").trigger("change");
        expect(addressQuery()).toBe("?seat=1&round=0&step=2");

        $(".replay-next-round").trigger("click");
        vi.spyOn(document, "hidden", "get").mockReturnValue(true);
        document.dispatchEvent(new Event("visibilitychange"));
        expect(addressQuery()).toBe("?seat=1&round=1&step=0");
        expect(window.history.length).toBe(historyLength);
    });
});
