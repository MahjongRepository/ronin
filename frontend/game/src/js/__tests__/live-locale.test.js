import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";
import PAGE from "../../../index.html?raw";
import { applyStaticText, setLocale } from "../../i18n/index.js";
import { bindLanguageMenu } from "../language-menu.js";
import { switchLiveLocale } from "../live-locale.js";
import { NO_OFFER } from "../ronin/offer.js";
import RoninPlayer from "../ronin/player.js";
import RONIN_RULE from "../ronin/rules.js";
import { DECISION_VARIANTS, dealDecision } from "../storybook/in-round.js";

const PLAYERS = ["Ronin", "Bot 1", "Bot 2", "Bot 3"];
const CALL_SECONDS = 10;
const SELECTOR_SETTLE_MS = 500;

function silentAudio() {
    return { play() {}, currentTime: 0 };
}

/** The live table of index.html in Japanese with a decision of the storybook's `variant` open, as the ronin layer opens it. */
function openDecision(key, onAnswer = vi.fn()) {
    const page = new DOMParser().parseFromString(PAGE, "text/html");
    page.head.querySelectorAll("script").forEach((script) => script.remove());
    document.head.innerHTML = page.head.innerHTML;
    document.body.innerHTML = page.body.innerHTML;
    setLocale("ja");
    applyStaticText(document);
    const { hand, events, offer } = DECISION_VARIANTS.find((variant) => variant.key === key);
    const pai = Majiang.UI.pai($("#loaddata"));
    const player = new RoninPlayer($("#board"), pai, silentAudio);
    player.action({
        kaiju: { id: 0, title: "", rule: RONIN_RULE, player: [...PLAYERS], qijia: 0 },
    });
    player.action({ qipai: dealDecision(hand) });
    for (const event of events.slice(0, -1)) {
        player.action(event);
    }
    player.view = new Majiang.UI.Board($("#board .board"), pai, silentAudio, player.model);
    player.view.redraw();
    player.offer = { ...NO_OFFER, ...offer };
    player.action(events.at(-1), onAnswer);
    return { player, board: player._view, onAnswer };
}

function visibleButtons() {
    return $("#board .player-button .button")
        .not(".hide")
        .map((i, button) => button.className)
        .get();
}

beforeEach(() => vi.useFakeTimers());

afterEach(() => {
    vi.useRealTimers();
    $(window).off();
    document.head.innerHTML = "";
    document.body.innerHTML = "";
});

describe("switchLiveLocale", () => {
    it("relabels an open call prompt in place, its buttons, countdown and focus kept", () => {
        const { player, board } = openDecision("ron");
        player.countdown([CALL_SECONDS, 0]);
        vi.advanceTimersByTime(1000);
        const focused = document.activeElement;
        const buttons = visibleButtons();
        const timer = $("#board .timer");
        expect(focused.classList.contains("rong")).toBe(true);
        expect(timer.text()).toBe(String(CALL_SECONDS - 1));

        switchLiveLocale(board, "en");

        expect(document.activeElement).toBe(focused);
        expect(visibleButtons()).toEqual(buttons);
        expect($("#board .player-button .rong").text()).toBe("Ron");
        expect($("#board .player-button .peng").text()).toBe("Pon");
        expect($("#board .player-button .cansel").attr("aria-label")).toBe("Skip");
        expect(timer.text()).toBe(String(CALL_SECONDS - 1));
        vi.advanceTimersByTime(2000);
        expect(timer.text()).toBe(String(CALL_SECONDS - 3));
        expect($("#board .score .jushu").text()).toBe("East 1");
        expect($("#board .shoupai.main .bingpai .pai").first().attr("alt")).toMatch(/ of /);
        expect(document.documentElement.lang).toBe("en");
        expect(document.title).toBe("Ronin - Game");
    });

    it("keeps a riichi discard selection and its Back answering after the switch", () => {
        const { board, onAnswer } = openDecision("riichi");
        $("#board .player-button .lizhi").trigger("click");
        vi.advanceTimersByTime(SELECTOR_SETTLE_MS);
        const selectable = $("#board .shoupai.main .bingpai .pai.blink").get();
        expect(selectable).toHaveLength(2);

        switchLiveLocale(board, "ru");

        const back = $("#board .select-mianzi .back");
        expect(back.text()).toBe("Назад");
        expect(back.attr("title")).toBe("Назад [Esc]");
        expect($("#board .shoupai.main .bingpai .pai.blink").get()).toEqual(selectable);
        back.trigger("click");
        expect(visibleButtons()).toContain("button lizhi");
        expect($("#board .player-button .lizhi").text()).toBe("Риичи");
        $("#board .player-button .lizhi").trigger("click");
        $(selectable[0]).trigger("click");
        expect(onAnswer).toHaveBeenCalledWith({ dapai: "p2*" });
    });

    it("leaves an open result dialog in its language, tagged with it, until it shows again", () => {
        const { board, player } = openDecision("ron");
        const win = {
            l: 0,
            shoupai: "m234p456s678s99z11z1",
            baojia: 3,
            hupai: [{ yi: 17, fanshu: 1 }],
            fanshu: 1,
            fu: 40,
            damanguan: 0,
            defen: 1300,
            fenpei: [1300, 0, 0, -1300],
            fubaopai: null,
        };
        player.model.hule(win);
        board.update({ hule: win });
        vi.advanceTimersByTime(SELECTOR_SETTLE_MS);
        const dialog = $("#board .hule-dialog");
        const title = dialog.find(".title").text();
        expect(title).toBe("Ronin ロン ← Bot 3");

        switchLiveLocale(board, "en");

        expect(dialog.attr("lang")).toBe("ja");
        expect(dialog.find(".title").text()).toBe(title);
        expect(dialog.find(".next [data-i18n]").text()).toBe("次へ");
        board.update({ hule: win });
        vi.advanceTimersByTime(SELECTOR_SETTLE_MS);
        expect(dialog.attr("lang")).toBeUndefined();
        expect(dialog.find(".title").text()).toBe("Ronin: Ron ← Bot 3");
        expect(dialog.find(".next [data-i18n]").text()).toBe("Next");
    });
});

describe("bindLanguageMenu", () => {
    it("offers each language by its native name, writes the chosen one to the lang cookie and applies it", () => {
        const { board } = openDecision("ron");
        const apply = vi.fn((next) => switchLiveLocale(board, next));
        bindLanguageMenu(document.getElementById("board"), apply);
        const options = () =>
            $("#board .settings-menu .language-option")
                .map(
                    (i, option) =>
                        `${option.lang}:${option.textContent}:${option.getAttribute("aria-checked")}`,
                )
                .get();
        expect(options()).toEqual(["en:English:false", "ja:日本語:true", "ru:Русский:false"]);

        $('#board .language-option[lang="ru"]').trigger("click");

        expect(apply).toHaveBeenCalledWith("ru");
        expect(document.cookie).toContain("lang=ru");
        expect(options()).toEqual(["en:English:false", "ja:日本語:false", "ru:Русский:true"]);
        expect($("#board .settings-menu .language-label").text()).toBe("Язык");
        document.cookie = "lang=; Path=/; Max-Age=0";
    });
});
