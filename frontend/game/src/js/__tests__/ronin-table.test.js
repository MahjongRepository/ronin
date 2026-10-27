import $ from "jquery";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import "../majiang.js";
import Majiang from "../../vendor/majiang-core/index.js";
import summary from "../../vendor/majiang-ui/summary.js";

import RoninPlayer from "../ronin/player.js";
import Reply from "../ronin/reply.js";
import Shadow from "../ronin/shadow.js";
import Translate from "../ronin/translate.js";
import Autoplay from "../ronin/autoplay.js";
import { NO_OFFER } from "../ronin/offer.js";
import Board from "../../vendor/majiang-ui/board.js";
import PAGE from "../../../index.html?raw";
import { renderSummary, rowTexts } from "./summary-table.js";

const DECISIONS = [
    "kaiju",
    "qipai",
    "zimo",
    "dapai",
    "fulou",
    "gang",
    "hule",
    "pingju",
    "jieju",
    "chankan",
];

class TablePlayer extends Majiang.Player {
    constructor() {
        super();
        this.offer = NO_OFFER;
        this.shown = [];
        this.countdowns = [];
        this.screenCountdowns = [];
        for (const name of DECISIONS) {
            this[`action_${name}`] = (data) => this.shown.push({ name, data });
        }
    }

    clear_handler() {}

    countdown(timer) {
        this.countdowns.push(timer);
    }

    clear_timer() {}

    screenCountdown(screen, seconds) {
        this.screenCountdowns.push([screen, seconds]);
    }

    clearScreenCountdown() {}

    show_button(callback) {
        callback();
    }

    select_dapai() {
        this.shown.push({ name: "select_dapai" });
    }

    get lastShown() {
        return this.shown.at(-1).name;
    }
}

const BASE_HAND = [16, 17, 0, 4, 9, 36, 40, 44, 72, 76, 80, 108, 112];
const TIMER_SETTINGS = { tb: 5, bk: 20, rb: 10, mb: 60, md: 5, ra: 5, gp: 3 };

function startTable(
    myTiles = BASE_HAND,
    round = {},
    game = {},
    player = new TablePlayer(),
    autoplay = undefined,
) {
    const shadow = new Shadow();
    const translate = new Translate(player, shadow, autoplay);
    const sent = [];
    const reply = new Reply(
        shadow,
        (message) => sent.push(message),
        () => sent.push("lobby"),
    );
    translate.onDecision = (kind, answer) => reply.decide(kind, answer);
    translate.onGameError = vi.fn();
    const receive = (message) => translate.handle(message);
    receive({
        t: 8,
        s: 0,
        gid: "g",
        dl: 0,
        dd: [
            [1, 1],
            [1, 1],
        ],
        p: [0, 1, 2, 3].map((s) => ({ s, nm: `p${s}`, ai: s !== 0 })),
        gt: 0,
        tm: TIMER_SETTINGS,
        ...game,
    });
    receive({
        t: 9,
        s: 0,
        w: 0,
        n: 0,
        dl: 0,
        cp: 0,
        di: [132],
        h: 0,
        r: 0,
        mt: myTiles,
        p: [0, 1, 2, 3].map((s) => ({ s, sc: 250 })),
        dc: [1, 1],
        ...round,
    });
    return {
        player,
        translate,
        sent,
        receive,
        decide: (answer) => player._callback(answer),
    };
}

const draw = (seat, tile, extra = {}) => ({ t: 1, d: seat * 136 + tile, ...extra });
const discard = (seat, tile) => ({ t: 2, d: seat * 136 + tile });
const riichiDiscard = (seat, tile) => ({ t: 2, d: 2 * 544 + seat * 136 + tile });
const WIN_CALL_MS = 500;
const DOUBLE_RON = {
    t: 4,
    rt: 2,
    ls: 0,
    wt: 2,
    wn: [
        {
            ws: 1,
            hr: {
                han: 5,
                fu: 30,
                yk: [
                    { yi: 1, han: 1 },
                    { yi: 13, han: 1 },
                    { yi: 120, han: 3 },
                ],
                pt: 80,
            },
            sch: { 0: -86, 1: 96, 2: 0, 3: 0 },
            rc: 1,
            ct: [5, 10, 14, 37, 41, 45, 73, 77, 81, 113, 114, 118, 119],
            ml: [],
            ud: [8],
        },
        {
            ws: 2,
            hr: { han: 13, fu: 30, yk: [{ yi: 103, han: 13 }], pt: 320 },
            sch: { 0: -160, 1: -166, 2: 326, 3: 0 },
            rc: 0,
            ct: [3, 20, 24, 28],
            ml: [20706, 20846, 20998],
            ps: 1,
        },
    ],
    sch: { 0: -246, 1: -70, 2: 326, 3: 0 },
};
const DIALOG_READY_MS = 800;
const RESULT_SHOWN_MS = 500;

function createUIPlayer() {
    const root = $("<div>").append(
        '<div class="hule-dialog"><button class="next" type="button">次へ</button></div>',
        '<div class="summary"><button class="exit" type="button">ロビーへ戻る</button></div>',
    );
    return new RoninPlayer(
        root,
        () => $("<span>"),
        () => ({ play() {} }),
    );
}

function startTableOnPage() {
    vi.useFakeTimers();
    document.body.innerHTML = new DOMParser().parseFromString(PAGE, "text/html").body.innerHTML;
    const renderTile = (p) => $('<span class="pai">').attr("data-pai", p.slice(0, 2));
    const silent = () => ({ play() {}, currentTime: 0 });
    const player = new RoninPlayer($("#board"), renderTile, silent);
    player.view = new Board($("#board .board"), renderTile, silent, player.model);
    return {
        table: startTable(BASE_HAND, {}, {}, player, new Autoplay($("#board .autoplay"))),
        hand: $("#board .shoupai.main .bingpai"),
    };
}

const flipSwitch = (name) => $(`#board .autoplay .${name}`).trigger("click");
const switchesOn = () =>
    $("#board .autoplay [aria-checked=true]")
        .map((_, button) => button.className)
        .get();

const shownOf = (table, name) => table.player.shown.filter((shown) => shown.name === name);

const renderedTotals = (table, fenpei) => {
    const model = table.player.model;
    return [0, 1, 2, 3].map((l) => model.defen[model.player_id[l]] + fenpei[l]);
};

function snapshot(fields) {
    return {
        gid: "g",
        p: [0, 1, 2, 3].map((s) => ({ s, nm: `p${s}`, ai: s !== 0 })),
        dl: 0,
        dd: [
            [1, 1],
            [1, 1],
        ],
        s: 0,
        w: 0,
        n: 0,
        di: [132],
        h: 0,
        r: 0,
        mt: BASE_HAND,
        dc: [1, 1],
        f: false,
        rh: [],
        wi: 7,
        tm: TIMER_SETTINGS,
        ...fields,
    };
}

describe("the ronin table (Translate and Reply)", () => {
    let consoleError;

    beforeEach(() => {
        consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    });

    afterEach(() => {
        const loggedErrors = [...consoleError.mock.calls];
        vi.restoreAllMocks();
        vi.useRealTimers();
        document.body.innerHTML = "";
        expect(loggedErrors).toEqual([]);
    });

    it("echoes the wait id of the server message that opened each decision", () => {
        const table = startTable();

        table.receive(draw(0, 120, { wi: 5 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive({ t: 3, clt: 0, ti: 124, frs: 1, cs: 0, wi: 6 });
        table.decide({});

        expect(table.sent).toEqual([
            { t: 3, a: 0, ti: 120, wi: 5 },
            { t: 3, a: 8, wi: 6 },
        ]);
    });

    it("offers a pon using a red five and discards after it, blocking the turn event's kuikae type, under its wait id", () => {
        const table = startTable();
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));
        table.receive(discard(3, 18));

        table.receive({ t: 3, clt: 1, ti: 18, frs: 3, cs: 0, ac: [{ clt: 0 }], wi: 2 });
        expect(table.player.offer.peng).toEqual(["m505-"]);
        table.decide({ fulou: "m505-" });
        const shownBeforeMeld = table.player.shown.length;
        table.receive({ t: 0, m: 16844 });
        expect(table.player.shown).toHaveLength(shownBeforeMeld);
        table.receive({ t: 12, kt: [4], wi: 3 });
        expect(table.player.lastShown).toBe("select_dapai");
        expect(table.player.offer.kuikae).toEqual(["m5"]);
        table.decide({ dapai: "m1" });

        expect(table.player.shoupai._fulou).toEqual(["m505-"]);
        expect(table.sent.slice(1)).toEqual([
            { t: 3, a: 4, ti: 18, wi: 2 },
            { t: 3, a: 0, ti: 0, wi: 3 },
        ]);
    });

    it.each([
        ["pon", 18, { clt: 0 }, "peng", "m505-", { a: 4 }],
        ["chi", 8, { clt: 1, opt: [[0, 4]] }, "chi", "m123-", { a: 5, sequence_tiles: [0, 4] }],
    ])(
        "offers a ron prompt's %s beside its ron and sends it when the player takes it instead",
        (_, tile, call, kind, meld, action) => {
            const table = startTable();
            table.receive(draw(0, 120, { wi: 1 }));
            table.decide({ dapai: "z4_" });
            table.receive(discard(0, 120));
            table.receive(discard(1, 124));
            table.receive(discard(2, 128));
            table.receive(discard(3, tile));

            table.receive({ t: 3, clt: 0, ti: tile, frs: 3, cs: 0, ac: [call], wi: 2 });
            expect(table.player.offer.ron).toBe(true);
            expect(table.player.offer[kind]).toEqual([meld]);
            table.decide({ fulou: meld });

            expect(table.sent.at(-1)).toEqual({ t: 3, ti: tile, ...action, wi: 2 });
        },
    );

    it("drops a call prompt left unanswered when the seat's own draw follows it, so it sends no pass under the draw's wait id", () => {
        const table = startTable();
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));
        table.receive(discard(3, 18));
        table.receive({ t: 3, clt: 1, ti: 18, frs: 3, cs: 0, ac: [{ clt: 0 }], wi: 2 });

        table.receive(draw(0, 121, { wi: 3 }));
        table.decide({});

        expect(table.sent).toEqual([{ t: 3, a: 0, ti: 120, wi: 1 }]);
    });

    it("sends the hand tiles of the chosen chi option", () => {
        const table = startTable();
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));
        table.receive(discard(3, 8));

        table.receive({
            t: 3,
            clt: 1,
            ti: 8,
            frs: 3,
            cs: 0,
            ac: [{ clt: 1, opt: [[0, 4]] }],
            wi: 2,
        });
        table.decide({ fulou: table.player.offer.chi[0] });

        expect(table.sent.at(-1)).toEqual({ t: 3, a: 5, ti: 8, sequence_tiles: [0, 4], wi: 2 });
    });

    it("counts the seat's turns down from the game's timer settings, with the bank they drain topped up each round, until a draw names the server's bank", () => {
        vi.useFakeTimers();
        const table = startTable();

        table.receive(draw(0, 120, { wi: 1 }));
        vi.advanceTimersByTime(8000);
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));
        table.receive(discard(3, 18));
        table.receive({ t: 3, clt: 1, ti: 18, frs: 3, cs: 0, ac: [{ clt: 0 }], wi: 2 });
        vi.advanceTimersByTime(2000);
        table.decide({ fulou: "m505-" });
        table.receive({ t: 0, m: 16844 });
        table.receive({ t: 12, kt: [4], wi: 3 });
        vi.advanceTimersByTime(10000);
        table.receive(discard(0, 0));
        table.receive({
            t: 9,
            s: 0,
            w: 0,
            n: 1,
            dl: 1,
            cp: 1,
            di: [132],
            h: 0,
            r: 0,
            mt: BASE_HAND,
            p: [],
            dc: [1, 1],
        });
        table.receive(draw(0, 120, { wi: 4 }));
        table.receive(discard(0, 120));
        table.receive(draw(0, 124, { wi: 5, bk: 12 }));

        expect(table.player.countdowns).toEqual([
            [5, 30],
            [5, 0],
            [5, 27],
            [5, 32],
            [5, 12],
        ]);
    });

    it("plays other seats' kans with their hidden draws and keeps the live wall count", () => {
        const table = startTable();
        table.receive(draw(0, 116, { wi: 1 }));
        table.decide({ dapai: "z3_" });
        table.receive(discard(0, 116));
        table.receive(discard(1, 101));
        table.receive({ t: 0, m: 23878 });
        table.receive(discard(2, 124));
        table.receive(discard(3, 128));
        table.receive(draw(0, 117, { wi: 2 }));
        table.receive(discard(0, 117));
        table.receive({ t: 0, m: 24409 });

        const model = table.player.model;
        expect(model.shoupai[2]._fulou).toEqual(["s8888-"]);
        expect(model.shoupai[1]._fulou).toEqual(["z4444"]);
        expect(model.shan.paishu).toBe(63);
    });

    it("turns the draw's available actions into tsumo, riichi with its discards, closed kan and kyuushu", () => {
        const table = startTable([52, 53, 54, 0, 4, 8, 36, 40, 44, 72, 76, 80, 108]);

        table.receive(
            draw(0, 55, {
                wi: 4,
                aa: [{ a: 2 }, { a: 1, tl: [108, 55] }, { a: 3, tl: [13] }, { a: 5 }],
            }),
        );
        expect(table.player.offer).toMatchObject({
            tsumo: true,
            riichi: ["z1", "p5_"],
            kyuushu: true,
        });
        table.decide({ hule: "-" });
        table.decide({ dapai: "z1*" });
        table.decide({ gang: table.player.offer.gang[0] });
        table.decide({ daopai: "-" });

        expect(table.sent).toEqual([
            { t: 3, a: 2, wi: 4 },
            { t: 3, a: 1, ti: 108, wi: 4 },
            { t: 3, a: 6, ti: 52, kan_type: "closed", wi: 4 },
            { t: 3, a: 7, wi: 4 },
        ]);
    });

    it("extends its pon into an added kan and takes the replacement draw, its turn's clock held through the chankan window", () => {
        vi.useFakeTimers();
        const table = startTable([108, 109, 0, 4, 8, 36, 40, 44, 72, 76, 80, 112, 116]);
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 110));
        table.receive({ t: 0, m: 20152 });
        table.receive({ t: 12, kt: [27], wi: 2 });
        table.decide({ dapai: "z3" });
        table.receive(discard(0, 116));
        table.receive(discard(1, 125));
        table.receive(discard(2, 126));
        table.receive(discard(3, 127));

        table.receive(draw(0, 111, { wi: 3, aa: [{ a: 4, tl: [27] }] }));
        vi.advanceTimersByTime(7000);
        table.decide({ gang: table.player.offer.gang[0] });
        vi.advanceTimersByTime(5000);
        table.receive({ t: 0, m: 22348 });
        table.receive(draw(0, 128, { wi: 4 }));

        expect(table.player.countdowns.at(-1)).toEqual([5, 28]);
        expect(table.sent.at(-1)).toEqual({ t: 3, a: 6, ti: 111, kan_type: "added", wi: 3 });
        expect(table.player.shoupai._fulou).toEqual(["z111=1"]);
        expect(table.player.shoupai._zimo).toBe("z6");
    });

    it("shows the added kan a chankan prompt offers to rob, answers it with ron, and plays it no second time at the round end", () => {
        vi.useFakeTimers();
        const table = startTable([0, 4, 8, 36, 40, 44, 56, 72, 76, 80, 108, 109, 112]);
        const say = vi.fn();
        table.player.view = { kaiju() {}, redraw() {}, update() {}, say };
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 125));
        table.receive(discard(2, 126));
        table.receive(discard(3, 64));
        table.receive({ t: 0, m: 18545 });
        table.receive(discard(1, 127));
        table.receive(discard(2, 128));
        table.receive(discard(3, 129));
        table.receive(draw(0, 60, { wi: 2 }));
        table.decide({ dapai: "z2" });
        table.receive(discard(0, 112));
        say.mockClear();

        table.receive({ t: 3, clt: 2, ti: 67, frs: 1, cs: 0, wi: 3 });
        const declarer = table.player.model.shoupai[1];
        expect(declarer._fulou).toEqual(["p888=8"]);
        expect(declarer._bingpai._).toBe(10);
        expect(say.mock.calls).toEqual([["gang", 1]]);
        expect(table.player.lastShown).toBe("chankan");
        table.decide({ hule: "-" });
        expect(table.sent.at(-1)).toEqual({ t: 3, a: 3, wi: 3 });

        table.receive({
            t: 4,
            rt: 1,
            ws: 0,
            ls: 1,
            wt: 67,
            hr: { han: 1, fu: 30, yk: [{ yi: 4, han: 1 }], pt: 15 },
            sch: { 0: 15, 1: -15, 2: 0, 3: 0 },
            rc: 0,
            ct: [0, 4, 8, 36, 40, 44, 56, 60, 72, 76, 80, 108, 109],
            ml: [],
            rk: { s: 1, ti: 67, kty: "added" },
            wi: 4,
        });
        expect(declarer._fulou).toEqual(["p888=8"]);
        expect(declarer._bingpai._).toBe(10);
        expect(say.mock.calls).toEqual([
            ["gang", 1],
            ["rong", 0],
        ]);
    });

    it("shows the closed kan a kokushi chankan prompt offers to rob, and plays its meld event no second time once declined", () => {
        const table = startTable([0, 1, 32, 36, 68, 72, 104, 108, 112, 120, 124, 128, 133]);
        const say = vi.fn();
        table.player.view = { kaiju() {}, redraw() {}, update() {}, say };
        table.receive(draw(0, 129, { wi: 1 }));
        table.decide({ dapai: "z6_" });
        table.receive(discard(0, 129));

        table.receive({ t: 3, clt: 2, ti: 119, frs: 1, cs: 0, wi: 2 });
        const declarer = table.player.model.shoupai[1];
        expect(declarer._fulou).toEqual(["z3333"]);
        expect(declarer._bingpai._).toBe(10);
        table.decide({});
        expect(table.sent.at(-1)).toEqual({ t: 3, a: 8, wi: 2 });

        table.receive({ t: 0, m: 24405 });
        expect(declarer._fulou).toEqual(["z3333"]);
        expect(declarer._bingpai._).toBe(10);
        expect(say.mock.calls).toEqual([["gang", 1]]);
        expect(table.player.model.shan.paishu).toBe(67);
    });

    it("sends no pass for a meld prompt the server timed out when a chankan prompt follows it, so the chankan stays the seat's to answer", () => {
        const table = startTable(
            [0, 4, 8, 36, 40, 44, 56, 72, 76, 80, 108, 109, 112],
            {},
            {},
            createUIPlayer(),
        );
        table.receive(draw(0, 124, { wi: 1 }));
        table.decide({ dapai: "z5_" });
        table.receive(discard(0, 124));
        table.receive(discard(1, 64));
        table.receive({ t: 0, m: 18550 });
        table.receive(discard(2, 125));
        table.receive(discard(3, 126));
        table.receive(draw(0, 60, { wi: 2 }));
        table.decide({ dapai: "z2" });
        table.receive(discard(0, 112));
        table.receive(discard(1, 110));
        table.receive({ t: 3, clt: 1, ti: 110, frs: 1, cs: 0, ac: [{ clt: 0 }], wi: 3 });

        table.receive({ t: 3, clt: 2, ti: 67, frs: 2, cs: 0, wi: 4 });
        expect(table.sent).toEqual([
            { t: 3, a: 0, ti: 124, wi: 1 },
            { t: 3, a: 0, ti: 112, wi: 2 },
        ]);
        table.decide({ hule: "-" });
        expect(table.sent.at(-1)).toEqual({ t: 3, a: 3, wi: 4 });
    });

    it("closes a call prompt whose countdown runs out, or that arrives with its time already run, sending nothing", () => {
        const { table } = startTableOnPage();
        const shownButtons = () => $("#board .player-button .button").not(".hide").length;
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));
        table.receive(discard(3, 18));

        table.receive({ t: 3, clt: 1, ti: 18, frs: 3, cs: 0, ac: [{ clt: 0 }], wi: 2 });
        expect(shownButtons()).toBe(2);
        vi.advanceTimersByTime(5000);
        expect(shownButtons()).toBe(0);

        table.receive({ t: 3, clt: 1, ti: 18, frs: 3, cs: 0, ac: [{ clt: 0 }], wi: 3, el: 5 });
        expect(shownButtons()).toBe(0);
        expect(table.sent).toEqual([{ t: 3, a: 0, ti: 120, wi: 1 }]);
    });

    it("closes an open call prompt when the socket drops, sending nothing for it", () => {
        const { table } = startTableOnPage();
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));
        table.receive(discard(3, 18));
        table.receive({ t: 3, clt: 1, ti: 18, frs: 3, cs: 0, ac: [{ clt: 0 }], wi: 2 });
        const buttons = () => $("#board .player-button .button").not(".hide");
        expect(buttons()).toHaveLength(2);

        table.translate.disconnected();
        $("#board").trigger($.Event("mouseup", { button: 2 }));

        expect(buttons()).toHaveLength(0);
        expect(table.sent).toEqual([{ t: 3, a: 0, ti: 120, wi: 1 }]);
    });

    it("passes a call prompt without ron on 鳴きなし and leaves one with ron to the player, also once 自動和了 is turned on during it", () => {
        const { table } = startTableOnPage();
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));
        table.receive(discard(3, 18));

        flipSwitch("no-call");
        table.receive({ t: 3, clt: 1, ti: 18, frs: 3, cs: 0, ac: [{ clt: 0 }], wi: 2 });
        table.receive(draw(0, 121, { wi: 3 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 121));
        table.receive(discard(1, 19));
        table.receive({ t: 3, clt: 0, ti: 19, frs: 1, cs: 0, ac: [{ clt: 0 }], wi: 4 });
        flipSwitch("win");
        vi.advanceTimersByTime(1000);
        table.decide({});

        expect(table.sent).toEqual([
            { t: 3, a: 0, ti: 120, wi: 1 },
            { t: 3, a: 8, wi: 2 },
            { t: 3, a: 0, ti: 121, wi: 3 },
            { t: 3, a: 8, wi: 4 },
        ]);
    });

    it("holds a 自動和了 ron a second with the buttons hidden, showing the prompt again instead if the switch is turned off meanwhile", () => {
        const { table } = startTableOnPage();
        const shownButtons = () => $("#board .player-button .button").not(".hide").length;
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));
        table.receive(discard(3, 18));

        flipSwitch("win");
        table.receive({ t: 3, clt: 0, ti: 18, frs: 3, cs: 0, wi: 2 });
        vi.advanceTimersByTime(500);
        expect(shownButtons()).toBe(0);
        flipSwitch("win");
        vi.advanceTimersByTime(500);
        expect(shownButtons()).toBe(2);
        table.decide({});
        table.receive(draw(0, 121, { wi: 3 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 121));
        flipSwitch("win");
        table.receive(discard(1, 19));
        table.receive({ t: 3, clt: 0, ti: 19, frs: 1, cs: 0, wi: 4 });
        vi.advanceTimersByTime(999);
        expect(table.sent).toHaveLength(3);
        vi.advanceTimersByTime(1);

        expect(table.sent.slice(1)).toEqual([
            { t: 3, a: 8, wi: 2 },
            { t: 3, a: 0, ti: 121, wi: 3 },
            { t: 3, a: 3, wi: 4 },
        ]);
    });

    it("drops a held 自動和了 ron when the server ends its prompt first, never sending it under the next wait", () => {
        const { table } = startTableOnPage();
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));

        flipSwitch("win");
        table.receive(discard(3, 18));
        table.receive({ t: 3, clt: 0, ti: 18, frs: 3, cs: 0, wi: 2 });
        vi.advanceTimersByTime(500);
        table.receive(draw(0, 121, { wi: 3 }));
        vi.advanceTimersByTime(1000);

        expect(table.sent).toEqual([{ t: 3, a: 0, ti: 120, wi: 1 }]);
    });

    it("calls a 自動和了 ron at once on a prompt re-sent with less than its hold left, before the prompt's countdown closes it", () => {
        const { table } = startTableOnPage();
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));
        table.receive(discard(3, 18));

        flipSwitch("win");
        table.receive({ t: 3, clt: 0, ti: 18, frs: 3, cs: 0, wi: 2, el: 4.5 });

        expect(table.sent.at(-1)).toEqual({ t: 3, a: 3, wi: 2 });
    });

    it("leaves the turn after its own pon to the player on ツモ切り after a reconnect, discarding no tile as drawn", () => {
        const { table } = startTableOnPage();
        flipSwitch("tsumogiri");
        table.translate.reconnect(
            snapshot({
                cp: 0,
                tr: 66,
                mt: [0, 4, 9, 36, 40, 44, 72, 76, 80, 108, 112],
                pst: [0, 1, 2, 3].map((s) => ({
                    s,
                    sc: 250,
                    dsc: [[{ ti: 120 }], [{ ti: 124 }], [{ ti: 128 }], [{ ti: 18 }]][s],
                    ml: s === 0 ? [16844] : [],
                    ri: false,
                    tc: s === 0 ? 11 : 13,
                })),
            }),
        );

        table.receive({ t: 12, kt: [4], wi: 8 });

        expect(table.sent).toEqual([]);
    });

    it("discards a drawn tile on ツモ切り only when its turn offers nothing else, once in riichi, and declares tsumo on 自動和了", () => {
        const { table } = startTableOnPage();
        const othersDiscard = (...tiles) =>
            tiles.forEach((tile, i) => table.receive(discard(i + 1, tile)));

        flipSwitch("tsumogiri");
        table.receive(draw(0, 120, { wi: 1 }));
        table.receive(discard(0, 120));
        othersDiscard(124, 128, 132);
        table.receive(draw(0, 121, { wi: 2, aa: [{ a: 1, tl: [121] }] }));
        expect(table.sent).toHaveLength(1);
        table.decide({ dapai: "z4_*" });
        table.receive(riichiDiscard(0, 121));
        othersDiscard(125, 129, 133);
        table.receive(draw(0, 122, { wi: 3 }));
        table.receive(discard(0, 122));
        othersDiscard(126, 130, 134);
        flipSwitch("win");
        table.receive(draw(0, 123, { wi: 4, aa: [{ a: 2 }] }));

        expect(table.sent).toEqual([
            { t: 3, a: 0, ti: 120, wi: 1 },
            { t: 3, a: 1, ti: 121, wi: 2 },
            { t: 3, a: 0, ti: 122, wi: 3 },
            { t: 3, a: 2, wi: 4 },
        ]);
    });

    it("keeps the auto switches through a reconnect within the round and clears them at the round end or a reconnect into another round", () => {
        const { table } = startTableOnPage();
        flipSwitch("win");
        flipSwitch("no-call");

        table.translate.reconnect(snapshot({ cp: 0, tr: 70 }));
        expect(switchesOn()).toEqual(["win", "no-call"]);
        table.receive({ t: 4, rt: 3, ts: [], ns: [0, 1, 2, 3], th: [], scs: {}, sch: {} });
        expect(switchesOn()).toEqual([]);
        flipSwitch("tsumogiri");
        table.translate.reconnect(snapshot({ cp: 0, tr: 70, n: 1, dl: 1 }));

        expect(switchesOn()).toEqual([]);
    });

    it("drops the tile the server discards for the seat, not a tile clicked after the server's timeout", () => {
        const { table, hand } = startTableOnPage();

        table.receive(draw(0, 120, { wi: 1 }));
        hand.find('> .pai[data-pai="m1"]').trigger("click");
        table.receive({ t: 7, cd: "stale_action", msg: "late" });
        table.receive(discard(0, 120));

        expect(hand.find('.pai[data-pai="m1"]').hasClass("deleted")).toBe(false);
        expect(hand.find('.pai[data-pai="z4"]').hasClass("deleted")).toBe(true);
    });

    it("shows the countdown of the turn its own pon opens, also when a refused discard reopens it", () => {
        const { table, hand } = startTableOnPage();
        const timer = $("#board .timer");
        table.receive(draw(0, 120, { wi: 1 }));
        hand.find('.zimo .pai[data-pai="z4"]').trigger("click");
        table.receive(discard(0, 120));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));
        table.receive(discard(3, 18));
        table.receive({ t: 3, clt: 1, ti: 18, frs: 3, cs: 0, ac: [{ clt: 0 }], wi: 2 });
        table.decide({ fulou: "m505-" });
        table.receive({ t: 0, m: 16844 });

        table.receive({ t: 12, kt: [4], wi: 3 });
        expect(timer.hasClass("hide")).toBe(false);
        hand.find('> .pai[data-pai="m1"]').trigger("click");
        expect(timer.hasClass("hide")).toBe(true);
        table.receive({ t: 7, cd: "invalid_discard", msg: "no" });
        expect(timer.hasClass("hide")).toBe(false);
    });

    it("drops only the discarded tile after a refused click, whose mark is still on the hand", () => {
        const { table, hand } = startTableOnPage();

        table.receive(draw(0, 120, { wi: 1 }));
        hand.find('.zimo .pai[data-pai="z4"]').trigger("click");
        table.receive({ t: 7, cd: "invalid_discard", msg: "no" });
        hand.find('> .pai[data-pai="m1"]').trigger("click");
        table.receive(discard(0, 0));

        expect(hand.find('.pai[data-pai="m1"]').hasClass("deleted")).toBe(true);
        expect(hand.find('.pai[data-pai="z4"]').hasClass("deleted")).toBe(false);
    });

    it("reopens a refused kan with what is left of its turn, charging the time it was held, but not after a stale action", () => {
        vi.useFakeTimers();
        const table = startTable([108, 109, 110, 0, 4, 9, 36, 40, 44, 72, 76, 80, 112]);
        table.receive(draw(0, 111, { wi: 1, aa: [{ a: 3, tl: [27] }] }));
        vi.advanceTimersByTime(7000);
        table.decide({ gang: table.player.offer.gang[0] });
        vi.advanceTimersByTime(3000);
        const shownBeforeErrors = table.player.shown.length;

        table.receive({ t: 7, cd: "invalid_kan", msg: "no" });
        expect(table.player.shown.length).toBe(shownBeforeErrors + 1);
        expect(table.player.countdowns.at(-1)).toEqual([0, 25]);
        table.receive({ t: 7, cd: "stale_action", msg: "late" });

        expect(table.player.shown.length).toBe(shownBeforeErrors + 1);
        expect(table.player.lastShown).toBe("zimo");
        expect(table.translate.onGameError).toHaveBeenCalledTimes(2);

        vi.advanceTimersByTime(10000);
        table.receive(discard(0, 111));
        table.receive(discard(1, 124));
        table.receive(discard(2, 128));
        table.receive(discard(3, 132));
        table.receive(draw(0, 121, { wi: 2 }));
        expect(table.player.countdowns.at(-1)).toEqual([5, 15]);
    });

    it("confirms a round end that opens a wait and holds the final standings until the last result is dismissed", () => {
        vi.useFakeTimers();
        const table = startTable();
        const tsumo = {
            t: 4,
            rt: 0,
            ws: 0,
            hr: {
                han: 3,
                fu: 30,
                yk: [
                    { yi: 13, han: 1 },
                    { yi: 120, han: 2 },
                ],
                pt: 39,
            },
            sch: { 0: 39, 1: -13, 2: -13, 3: -13 },
            ct: [16, 17, 0, 4, 9, 36, 40, 44, 72, 76, 80, 108, 109, 18],
            ml: [],
            wt: 18,
        };

        table.receive({ ...tsumo, wi: 9 });
        vi.advanceTimersByTime(WIN_CALL_MS);
        expect(table.player.shown.at(-1).data).toMatchObject({
            fanshu: 3,
            damanguan: 0,
            defen: 3900,
            fubaopai: null,
            hupai: [
                { name: "断幺九", fanshu: 1 },
                { name: "ドラ", fanshu: 2 },
            ],
        });
        table.decide({});
        table.receive(tsumo);
        table.receive({
            t: 10,
            ws: 0,
            st: [
                { s: 0, sc: 289, fs: 39 },
                { s: 1, sc: 237, fs: 3 },
                { s: 2, sc: 237, fs: -16 },
                { s: 3, sc: 237, fs: -26 },
            ],
            lb: 0,
        });
        vi.advanceTimersByTime(WIN_CALL_MS);
        expect(table.player.lastShown).toBe("hule");
        table.decide({});
        expect(table.player.lastShown).toBe("jieju");
        expect(table.player.shown.at(-1).data.point).toEqual([39, 3, -16, -26]);
        table.decide({});

        expect(table.sent).toEqual([{ t: 3, a: 9, wi: 9 }, "lobby"]);
        expect(table.player.screenCountdowns).toEqual([
            ["kaiju", 3],
            ["result", 4.5],
        ]);
    });

    it("credits the game end's leftover riichi bonus to the winner's gongtuo row", () => {
        const table = startTable();
        table.receive({
            t: 10,
            ws: 2,
            st: [
                { s: 2, sc: 325, fs: 51 },
                { s: 1, sc: 255, fs: 4 },
                { s: 0, sc: 215, fs: -17 },
                { s: 3, sc: 205, fs: -38 },
            ],
            lb: 20,
        });

        expect(table.player.lastShown).toBe("jieju");
        expect(table.player.shown.at(-1).data).toMatchObject({
            defen: [21500, 25500, 32500, 20500],
            rank: [3, 2, 1, 4],
            gongtuo: [0, 0, 2000, 0],
        });
    });

    it("shows each double ron win in turn with its own hand value and payments, honba to both and the sticks to the first, and confirms after the last", () => {
        vi.useFakeTimers();
        const table = startTable(BASE_HAND, { h: 2, r: 1 });

        table.receive({ ...DOUBLE_RON, wi: 9 });
        vi.advanceTimersByTime(WIN_CALL_MS);

        expect(shownOf(table, "hule")).toHaveLength(1);
        expect(shownOf(table, "hule")[0].data).toMatchObject({
            l: 1,
            defen: 8000,
            fenpei: [-8600, 9600, 0, 0],
            fubaopai: ["m3"],
        });
        expect(table.player.model).toMatchObject({ changbang: 2, lizhibang: 1 });
        table.decide({});
        expect(table.sent).toEqual([]);

        expect(shownOf(table, "hule")[1].data).toMatchObject({
            l: 2,
            defen: 32000,
            fenpei: [-16000, -16600, 32600, 0],
        });
        expect(table.player.model).toMatchObject({
            changbang: 2,
            lizhibang: 0,
            defen: [16400, 34600, 25000, 25000],
        });
        table.decide({});
        expect(table.sent).toEqual([{ t: 3, a: 9, wi: 9 }]);
    });

    it("keeps a final double ron's second result dismissable when the first is dismissed before its keyboard setup, then leads to the standings", () => {
        vi.useFakeTimers();
        const player = createUIPlayer();
        const table = startTable(BASE_HAND, { h: 2, r: 1 }, {}, player);
        const next = $(".hule-dialog .next", player._node.root);

        table.receive(DOUBLE_RON);
        table.receive({
            t: 10,
            ws: 2,
            st: [
                { s: 2, sc: 576, fs: 88 },
                { s: 3, sc: 250, fs: 0 },
                { s: 1, sc: 183, fs: -12 },
                { s: 0, sc: 1, fs: -76 },
            ],
            lb: 0,
        });
        vi.advanceTimersByTime(WIN_CALL_MS + RESULT_SHOWN_MS);
        next.trigger("click");
        vi.advanceTimersByTime(DIALOG_READY_MS);
        next.trigger("click");
        $(".summary .exit", player._node.root).trigger("click");

        expect(table.sent).toEqual(["lobby"]);
    });

    it("counts the game start pause down on the start screen until the deal", () => {
        vi.useFakeTimers();
        document.body.innerHTML = new DOMParser().parseFromString(PAGE, "text/html").body.innerHTML;
        const silent = () => ({ play() {}, currentTime: 0 });
        const player = new RoninPlayer($("#board"), () => $("<span>"), silent);
        player.view = new Board($("#board .board"), () => $("<span>"), silent, player.model);
        const translate = new Translate(player, new Shadow());
        const countdown = $("#board .kaiju .countdown");

        translate.handle({
            t: 8,
            s: 0,
            gid: "g",
            dl: 0,
            dd: [
                [1, 1],
                [1, 1],
            ],
            p: [0, 1, 2, 3].map((s) => ({ s, nm: `p${s}`, ai: s !== 0 })),
            gt: 0,
            tm: TIMER_SETTINGS,
        });
        expect(countdown.text()).toBe("3");
        vi.advanceTimersByTime(1000);
        expect(countdown.text()).toBe("2");
        vi.advanceTimersByTime(5000);
        expect(countdown.text()).toBe("0");

        translate.handle({
            t: 9,
            s: 0,
            w: 0,
            n: 0,
            dl: 0,
            cp: 0,
            di: [132],
            h: 0,
            r: 0,
            mt: BASE_HAND,
            p: [0, 1, 2, 3].map((s) => ({ s, sc: 250 })),
            dc: [1, 1],
        });
        expect(countdown.text()).toBe("");
    });

    it("counts each result of a double ron down to its share of the round advance timeout, moving on from the first by itself and leaving the last to the server", () => {
        const { table } = startTableOnPage();
        const countdown = $("#board .hule-dialog .next .countdown");
        const title = $("#board .hule-dialog .title");

        table.receive({ ...DOUBLE_RON, wi: 9 });
        vi.advanceTimersByTime(WIN_CALL_MS + RESULT_SHOWN_MS);
        expect(countdown.text()).toBe("5");
        expect(title.text()).toContain("p1");

        vi.advanceTimersByTime(4_000 + RESULT_SHOWN_MS);
        expect(countdown.text()).toBe("5");
        expect(title.text()).toContain("p2");
        expect(table.sent).toEqual([]);

        vi.advanceTimersByTime(5_000);
        expect(countdown.text()).toBe("0");
        expect(table.sent).toEqual([]);
        table.receive({
            t: 9,
            s: 0,
            w: 0,
            n: 1,
            dl: 1,
            cp: 1,
            di: [132],
            h: 0,
            r: 0,
            mt: BASE_HAND,
            p: [0, 1, 2, 3].map((s) => ({ s, sc: 250 })),
            dc: [1, 1],
        });
        expect(countdown.text()).toBe("");
    });

    it("confirms a round result only from its 次へ button, not from a click elsewhere on the dialog", () => {
        const { table } = startTableOnPage();
        table.receive(draw(0, 120, { wi: 8 }));
        table.receive(discard(0, 120));

        table.receive({
            t: 4,
            rt: 3,
            ts: [0],
            th: [],
            sch: { 0: 30, 1: -10, 2: -10, 3: -10 },
            wi: 9,
        });
        vi.advanceTimersByTime(DIALOG_READY_MS);
        $("#board .hule-dialog .fenpei").trigger("click");
        expect(table.sent).toEqual([]);
        $("#board .hule-dialog .next").trigger("click");

        expect(table.sent).toEqual([{ t: 3, a: 9, wi: 9 }]);
    });

    it("gives a nagashi mangan's result each seat's tenpai and its achievers, in dealer-relative order", () => {
        const table = startTable(BASE_HAND, { dl: 1 });

        table.receive({
            t: 4,
            rt: 5,
            qs: [2],
            ts: [1, 3],
            ns: [0, 2],
            th: [],
            sch: { 0: -20, 1: -40, 2: 80, 3: -20 },
            wi: 9,
        });

        expect(shownOf(table, "pingju")[0].data).toMatchObject({
            name: "流し満貫",
            fenpei: [-4000, 8000, -2000, -2000],
            tenpai: [true, false, true, false],
            players: [1],
        });
    });

    it("names the seat that declared nine terminals in its result", () => {
        const table = startTable(BASE_HAND, { dl: 1 });

        table.receive({
            t: 4,
            rt: 4,
            rn: "nine_terminals",
            s: 0,
            sch: { 0: 0, 1: 0, 2: 0, 3: 0 },
            wi: 9,
        });

        expect(shownOf(table, "pingju")[0].data).toMatchObject({ tenpai: null, players: [3] });
    });

    it("takes no riichi deposit for a riichi discard that ends the round in four winds, in its result or the final standings", () => {
        const table = startTable();
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z1" });
        table.receive(discard(0, 108));
        table.receive(discard(1, 109));
        table.receive(discard(2, 110));
        table.receive(riichiDiscard(3, 111));

        table.receive({ t: 4, rt: 4, rn: "four_winds", sch: { 0: 0, 1: 0, 2: 0, 3: 0 } });
        expect(table.player.lastShown).toBe("pingju");
        expect(table.player.model.defen).toEqual([25000, 25000, 25000, 25000]);
        expect(table.player.model.lizhibang).toBe(0);

        table.receive({
            t: 10,
            ws: 0,
            st: [0, 1, 2, 3].map((s) => ({ s, sc: 250, fs: 0 })),
            lb: 0,
        });
        table.decide({});
        const root = renderSummary();
        summary(root, table.player.shown.at(-1).data, 0);
        expect(rowTexts(root, ".row-diff")).toEqual(["東一局|0本場|流局|±0|±0|±0|±0"]);
    });

    it("drops a win's pending result when the next round starts before it shows", () => {
        vi.useFakeTimers();
        const table = startTable();

        table.receive({
            t: 4,
            rt: 0,
            ws: 0,
            hr: { han: 1, fu: 30, yk: [{ yi: 1, han: 1 }], pt: 15 },
            sch: { 0: 15, 1: -5, 2: -5, 3: -5 },
            ct: BASE_HAND,
            ml: [],
            wt: 120,
            wi: 9,
        });
        table.receive({
            t: 9,
            s: 0,
            w: 0,
            n: 1,
            dl: 1,
            cp: 1,
            di: [132],
            h: 0,
            r: 0,
            mt: BASE_HAND,
            p: [0, 1, 2, 3].map((s) => ({ s, sc: 250 })),
            dc: [1, 1],
        });
        table.receive(draw(0, 120, { wi: 10 }));
        vi.advanceTimersByTime(WIN_CALL_MS);

        expect(shownOf(table, "hule")).toHaveLength(0);
        expect(table.player.lastShown).toBe("zimo");
        expect(table.translate.roundDialogOpen).toBe(false);
        table.decide({ dapai: "z4_" });
        expect(table.sent).toEqual([{ t: 3, a: 0, ti: 120, wi: 10 }]);
    });

    it("shows the game start from the seat game_started names before any deal, and not again with a deal", () => {
        const player = new TablePlayer();
        const translate = new Translate(player, new Shadow());
        translate.handle({
            t: 8,
            s: 2,
            gid: "g",
            dl: 0,
            dd: [
                [1, 1],
                [1, 1],
            ],
            p: [0, 1, 2, 3].map((s) => ({ s, nm: `p${s}`, ai: s !== 2 })),
            gt: 0,
            tm: TIMER_SETTINGS,
        });
        expect(player.shown.map((shown) => shown.name)).toEqual(["kaiju"]);
        expect(player.shown[0].data.id).toBe(2);

        for (const n of [0, 1]) {
            translate.handle({
                t: 9,
                s: 2,
                w: 0,
                n,
                dl: n,
                cp: n,
                di: [132],
                h: 0,
                r: 0,
                mt: BASE_HAND,
                p: [0, 1, 2, 3].map((s) => ({ s, sc: 250 })),
                dc: [1, 1],
            });
        }
        expect(player.shown.map((shown) => shown.name)).toEqual(["kaiju", "qipai", "qipai"]);
    });

    it("titles the game start with the game's length and local start time, not the game id", () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date(2026, 9, 25, 14, 30));
        const table = startTable(BASE_HAND, {}, { gid: "3f2b6c1e", gt: 1 });

        expect(shownOf(table, "kaiju")[0].data.title).toBe("東風戦\n2026/10/25 14:30");
    });

    it("calls out a riichi as it is discarded and a win before its result", () => {
        vi.useFakeTimers();
        const table = startTable();
        const say = vi.fn();
        table.player.view = { kaiju() {}, redraw() {}, update() {}, say };

        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));
        table.receive(riichiDiscard(1, 124));
        expect(say).toHaveBeenLastCalledWith("lizhi", 1);

        table.receive({
            t: 4,
            rt: 0,
            ws: 1,
            hr: { han: 1, fu: 30, yk: [{ yi: 1, han: 1 }] },
            rc: 1,
            sch: { 0: -5, 1: 21, 2: -3, 3: -3 },
            ct: [5, 10, 14, 37, 41, 45, 73, 77, 81, 113, 114, 118, 119],
            ml: [],
            wt: 2,
            wi: 2,
        });
        expect(say).toHaveBeenLastCalledWith("zimo", 1);
        expect(table.player.lastShown).not.toBe("hule");
        vi.advanceTimersByTime(WIN_CALL_MS);
        expect(table.player.lastShown).toBe("hule");
    });

    it("calls out ron for every seat that declared a triple ron before its abortive draw result", () => {
        vi.useFakeTimers();
        const table = startTable();
        const say = vi.fn();
        table.player.view = { kaiju() {}, redraw() {}, update() {}, say };
        table.receive(draw(0, 120, { wi: 1 }));
        table.decide({ dapai: "z4_" });
        table.receive(discard(0, 120));

        table.receive({
            t: 4,
            rt: 4,
            rn: "triple_ron",
            rcl: [1, 2, 3],
            sch: { 0: 0, 1: 0, 2: 0, 3: 0 },
            wi: 2,
        });
        expect(say.mock.calls).toEqual([
            ["rong", 1],
            ["rong", 2],
            ["rong", 3],
        ]);
        expect(table.player.lastShown).not.toBe("pingju");
        vi.advanceTimersByTime(WIN_CALL_MS);
        expect(shownOf(table, "pingju")[0].data).toMatchObject({
            name: "三家和了",
            fenpei: [0, 0, 0, 0],
        });
    });

    it("shows another seat's added kan that a chankan robs and calls it out before the ron, ahead of the win's result", () => {
        vi.useFakeTimers();
        const table = startTable();
        const say = vi.fn();
        table.player.view = { kaiju() {}, redraw() {}, update() {}, say };
        table.receive(draw(0, 64, { wi: 1 }));
        table.decide({ dapai: "p8_" });
        table.receive(discard(0, 64));
        table.receive({ t: 0, m: 18549 });
        table.receive(discard(1, 125));
        table.receive(discard(2, 126));
        table.receive(discard(3, 127));
        table.receive(draw(0, 128, { wi: 2 }));
        table.decide({ dapai: "z6_" });
        table.receive(discard(0, 128));
        say.mockClear();

        table.receive({
            t: 4,
            rt: 1,
            ws: 2,
            ls: 1,
            wt: 67,
            hr: { han: 1, fu: 30, yk: [{ yi: 4, han: 1 }], pt: 10 },
            sch: { 0: 0, 1: -10, 2: 10, 3: 0 },
            rc: 0,
            ct: [1, 5, 10, 56, 60, 84, 88, 92, 96, 100, 104, 116, 117],
            ml: [],
            rk: { s: 1, ti: 67, kty: "added" },
            wi: 3,
        });
        const declarer = table.player.model.shoupai[1];
        expect(declarer._fulou).toEqual(["p888-8"]);
        expect(declarer._bingpai._).toBe(10);
        expect(say.mock.calls).toEqual([["gang", 1]]);
        vi.advanceTimersByTime(WIN_CALL_MS);
        expect(say.mock.calls).toEqual([
            ["gang", 1],
            ["rong", 2],
        ]);
        expect(table.player.lastShown).not.toBe("hule");
        vi.advanceTimersByTime(WIN_CALL_MS);
        expect(shownOf(table, "hule")[0].data).toMatchObject({ l: 2, baojia: 1 });
    });

    it("shows the added kan a chankan robbed, over the declarer's pon, when the seat reconnects during the round advance", () => {
        const table = startTable();
        table.translate.reconnect(
            snapshot({
                cp: 1,
                tr: 65,
                pst: [
                    { s: 0, sc: 250, dsc: [{ ti: 64 }, { ti: 128 }], ml: [], ri: false, tc: 13 },
                    { s: 1, sc: 240, dsc: [{ ti: 125 }], ml: [18549], ri: false, tc: 11 },
                    { s: 2, sc: 260, dsc: [{ ti: 126 }], ml: [], ri: false, tc: 13 },
                    { s: 3, sc: 250, dsc: [{ ti: 127 }], ml: [], ri: false, tc: 13 },
                ],
                rh: [
                    {
                        w: 0,
                        dl: 0,
                        h: 0,
                        rs: [],
                        ws: [2],
                        ls: 1,
                        sch: { 0: 0, 1: -10, 2: 10, 3: 0 },
                    },
                ],
                re: { rt: 1, ws: 2, ls: 1, wt: 67, rk: { s: 1, ti: 67, kty: "added" } },
            }),
        );

        const declarer = table.player.model.shoupai[1];
        expect(declarer._fulou).toEqual(["p888-8"]);
        expect(declarer._bingpai._).toBe(10);
        expect(shownOf(table, "hule")).toEqual([]);
        expect(table.sent).toEqual([]);
    });

    it("confirms the round result a taken-over seat still owes after a reconnect during the round advance, at the snapshot's scores, counting the round once in the standings", () => {
        const table = startTable();
        const sch = { 0: 30, 1: -10, 2: -10, 3: -10 };
        table.translate.reconnect(
            snapshot({
                cp: 1,
                tr: 0,
                pst: [280, 240, 240, 240].map((sc, s) => ({
                    s,
                    sc,
                    dsc: [],
                    ml: [],
                    ri: false,
                    tc: 13,
                })),
                rh: [{ w: 0, dl: 0, h: 0, rs: [], ws: [], ts: [0], sch }],
                re: { rt: 3, ts: [0], th: [], sch },
                oc: true,
            }),
        );
        expect(table.player.lastShown).toBe("pingju");
        expect(renderedTotals(table, table.player.shown.at(-1).data.fenpei)).toEqual([
            28000, 24000, 24000, 24000,
        ]);
        table.decide({});
        table.receive({
            t: 10,
            ws: 0,
            st: [0, 1, 2, 3].map((s) => ({ s, sc: 250, fs: 0 })),
            lb: 0,
        });

        expect(table.sent).toEqual([{ t: 3, a: 9, wi: 7 }]);
        expect(table.player.lastShown).toBe("jieju");
        expect(table.player.shown.at(-1).data.log).toHaveLength(1);
    });

    it("shows each win of an owed double ron after a reconnect at the snapshot's scores, not over them again", () => {
        vi.useFakeTimers();
        const table = startTable();
        table.translate.reconnect(
            snapshot({
                cp: 0,
                tr: 50,
                pst: [4, 180, 576, 250].map((sc, s) => ({
                    s,
                    sc,
                    dsc: [],
                    ml: [],
                    ri: false,
                    tc: 13,
                })),
                re: DOUBLE_RON,
                oc: true,
                el: 2,
            }),
        );
        vi.advanceTimersByTime(WIN_CALL_MS);
        table.decide({});
        const [, second] = shownOf(table, "hule");

        expect(renderedTotals(table, second.data.fenpei)).toEqual([400, 18000, 57600, 25000]);
        expect(table.player.screenCountdowns.slice(1)).toEqual([
            ["result", 2.5],
            ["result", 7.5],
        ]);
        table.decide({});
        expect(table.sent).toEqual([{ t: 3, a: 9, wi: 7 }]);
    });

    it.each([
        ["in its base time", 3, [2, 12], 12],
        ["in its bank time", 9, [0, 8], 7],
    ])(
        "counts a turn re-sent after a takeover %s down from what the server left of it, and charges the bank as the server does",
        (_, elapsed, countdown, bankAfter) => {
            vi.useFakeTimers();
            const table = startTable();
            const hand = [16, 17, 0, 4, 9, 36, 40, 44, 72, 76, 80, 108, 112, 120];
            table.translate.reconnect(
                snapshot({
                    cp: 0,
                    mt: hand,
                    tr: 69,
                    tm: { ...TIMER_SETTINGS, bk: 12 },
                    pst: [0, 1, 2, 3].map((s) => ({
                        s,
                        sc: 250,
                        dsc: [],
                        ml: [],
                        ri: false,
                        tc: s === 0 ? 14 : 13,
                    })),
                }),
            );

            table.receive(draw(0, 120, { wi: 7, el: elapsed }));
            table.receive({ t: 7, cd: "invalid_discard", msg: "no" });
            vi.advanceTimersByTime(1000);
            table.decide({ dapai: "z4_" });
            table.receive(discard(0, 120));
            table.receive({ t: 3, clt: 1, ti: 18, frs: 3, cs: 0, ac: [{ clt: 0 }], wi: 8, el: 2 });
            table.decide({});
            table.receive(draw(0, 121, { wi: 9 }));

            expect(shownOf(table, "zimo")).toHaveLength(3);
            expect(table.player.countdowns.at(0)).toEqual(countdown);
            expect(table.player.countdowns.slice(2)).toEqual([
                [3, 0],
                [5, bankAfter],
            ]);
        },
    );

    it("reopens the call prompt the server re-sends after a reconnect during its call wait, on the pending discard", () => {
        const table = startTable();
        table.translate.reconnect(
            snapshot({
                cp: 3,
                tr: 66,
                pst: [0, 1, 2, 3].map((s) => ({
                    s,
                    sc: 250,
                    dsc: [[{ ti: 120 }], [{ ti: 124 }], [{ ti: 128 }], [{ ti: 18 }]][s],
                    ml: [],
                    ri: false,
                    tc: 13,
                })),
            }),
        );

        table.receive({ t: 3, clt: 1, ti: 18, frs: 3, cs: 0, ac: [{ clt: 0 }], wi: 8 });
        expect(table.player.shown.at(-1)).toEqual({ name: "dapai", data: { l: 3, p: "m5" } });
        expect(table.player.offer.peng).toEqual(["m505-"]);
        table.decide({ fulou: "m505-" });

        expect(table.sent).toEqual([{ t: 3, a: 4, ti: 18, wi: 8 }]);
    });

    it("rebuilds each opponent's face-down hand to its tile count beside its melds, the turn's draw held, after a reconnect", () => {
        const table = startTable();
        table.translate.reconnect(
            snapshot({
                cp: 3,
                di: [132, 133, 134],
                tr: 61,
                pst: [
                    { s: 0, sc: 250, dsc: [{ ti: 64 }, { ti: 130 }], ml: [], ri: false, tc: 13 },
                    {
                        s: 1,
                        sc: 250,
                        dsc: [{ ti: 1 }, { ti: 125 }],
                        ml: [21801, 24405],
                        ri: false,
                        tc: 7,
                    },
                    {
                        s: 2,
                        sc: 250,
                        dsc: [{ ti: 126 }, { ti: 128 }, { ti: 129 }],
                        ml: [242, 18686],
                        ri: false,
                        tc: 7,
                    },
                    { s: 3, sc: 250, dsc: [{ ti: 68 }, { ti: 127 }], ml: [], ri: false, tc: 14 },
                ],
            }),
        );
        const model = table.player.model;
        expect(model.shoupai[1]._fulou).toEqual(["p888-8", "z3333"]);
        expect(model.shoupai[1]._bingpai._).toBe(7);
        expect(model.shoupai[2]._fulou).toEqual(["m1-23", "p999+"]);
        expect(model.shoupai[2]._bingpai._).toBe(7);

        table.receive(discard(3, 131));
        expect(model.shoupai[3]._bingpai._).toBe(13);
        table.receive(draw(0, 100, { wi: 8 }));
        table.decide({ dapai: "s8_" });
        table.receive(discard(0, 100));
        table.receive(discard(1, 101));
        table.receive(discard(2, 102));
        expect(model.shoupai[2]._bingpai._).toBe(7);
        expect(model.shan.paishu).toBe(58);
    });

    it("applies a pon of the pending discard after a reconnect during its call wait, marking the discarder's river", () => {
        const table = startTable();
        table.translate.reconnect(
            snapshot({
                cp: 1,
                tr: 64,
                pst: [0, 1, 2, 3].map((s) => ({
                    s,
                    sc: 250,
                    dsc: [
                        [{ ti: 120 }, { ti: 130 }],
                        [{ ti: 125 }, { ti: 64 }],
                        [{ ti: 126 }],
                        [{ ti: 127 }],
                    ][s],
                    ml: [],
                    ri: false,
                    tc: 13,
                })),
            }),
        );

        table.receive({ t: 0, m: 18550 });
        const model = table.player.model;
        expect(model.shoupai[2]._fulou).toEqual(["p888-"]);
        expect(model.he[1]._pai.at(-1)).toBe("p8-");
    });

    it("seeds the final standings with the rounds before a reconnect, every double ron winner marked, so each column adds up to its final score", () => {
        const table = startTable(BASE_HAND, {}, { gt: 1 });
        table.translate.reconnect({
            gid: "g",
            p: [0, 1, 2, 3].map((s) => ({ s, nm: `p${s}`, ai: s !== 0 })),
            dl: 3,
            dd: [
                [2, 3],
                [1, 4],
            ],
            s: 0,
            w: 0,
            n: 3,
            cp: 3,
            di: [132],
            h: 0,
            r: 0,
            mt: BASE_HAND,
            dc: [1, 1],
            tr: 69,
            tm: TIMER_SETTINGS,
            pst: [308, 234, 114, 344].map((sc, s) => ({
                s,
                sc,
                dsc: [],
                ml: [],
                ri: false,
                tc: s === 3 ? 14 : 13,
            })),
            f: false,
            rh: [
                {
                    w: 0,
                    dl: 0,
                    h: 0,
                    rs: [1],
                    ws: [3, 1],
                    ls: 2,
                    sch: { 0: 0, 1: 20, 2: -100, 3: 90 },
                },
                {
                    w: 0,
                    dl: 1,
                    h: 0,
                    rs: [],
                    ws: [],
                    ts: [0, 3],
                    sch: { 0: 15, 1: -15, 2: -15, 3: 15 },
                },
                { w: 0, dl: 2, h: 1, rs: [], ws: [0], sch: { 0: 43, 1: -11, 2: -21, 3: -11 } },
            ],
            wi: 7,
        });
        table.receive({ t: 4, rt: 3, ts: [], ns: [0, 1, 2, 3], th: [], scs: {}, sch: {} });
        table.receive({
            t: 10,
            ws: 3,
            st: [
                { s: 3, sc: 344, fs: 54 },
                { s: 0, sc: 308, fs: 11 },
                { s: 1, sc: 234, fs: -16 },
                { s: 2, sc: 114, fs: -49 },
            ],
            lb: 0,
        });
        table.decide({});
        expect(table.player.lastShown).toBe("jieju");

        const root = renderSummary();
        summary(root, table.player.shown.at(-1).data, 0);
        expect(rowTexts(root, ".row-diff")).toEqual([
            "東一局|0本場|ロン||+1,000リ|-10,000|+9,000",
            "東二局|0本場|流局|+1,500|-1,500|-1,500|+1,500",
            "東三局|1本場|ツモ|+4,300|-1,100|-2,100|-1,100",
            "東四局|0本場|流局|ノーテン|ノーテン|ノーテン|ノーテン",
        ]);
        expect(rowTexts(root, ".row-defen")).toEqual(["|30,800|23,400|11,400|34,400"]);
        expect(
            root
                .find(".row-diff")
                .first()
                .find(".diff")
                .map((i, cell) => cell.classList.contains("hule"))
                .get(),
        ).toEqual([false, true, false, true]);
    });

    it("shows フリテン above the seat's own nameplate while the server reports furiten, until it reports it over or the next deal", () => {
        const { table } = startTableOnPage();
        const shown = () => !$("#board .board > .furiten").hasClass("hide");
        expect(shown()).toBe(false);

        table.receive({ t: 11, f: true });
        expect(shown()).toBe(true);

        table.receive({ t: 11, f: false });
        expect(shown()).toBe(false);

        table.receive({ t: 11, f: true });
        table.receive({
            t: 9,
            s: 0,
            w: 0,
            n: 1,
            dl: 1,
            cp: 1,
            di: [132],
            h: 0,
            r: 0,
            mt: BASE_HAND,
            p: [0, 1, 2, 3].map((s) => ({ s, sc: 250 })),
            dc: [1, 1],
        });
        expect(shown()).toBe(false);
    });

    it("shows the reconnect snapshot's furiten above the seat's own nameplate", () => {
        const { table } = startTableOnPage();
        table.translate.reconnect({
            gid: "g",
            p: [0, 1, 2, 3].map((s) => ({ s, nm: `p${s}`, ai: s !== 0 })),
            dl: 0,
            dd: [
                [1, 1],
                [1, 1],
            ],
            s: 0,
            w: 0,
            n: 0,
            cp: 1,
            di: [132],
            h: 0,
            r: 0,
            mt: BASE_HAND,
            dc: [1, 1],
            tr: 68,
            pst: [0, 1, 2, 3].map((s) => ({
                s,
                sc: 250,
                dsc: s === 0 ? [{ ti: 120 }] : [],
                ml: [],
                ri: false,
                tc: s === 1 ? 14 : 13,
            })),
            f: true,
            rh: [],
            wi: 7,
            tm: TIMER_SETTINGS,
        });

        expect($("#board .board > .furiten").hasClass("hide")).toBe(false);
    });

    it("resumes its turn after a reconnect without taking the re-sent draw twice", () => {
        const table = startTable();
        const hand = [16, 17, 0, 4, 9, 36, 40, 44, 72, 76, 80, 108, 112, 120];
        table.translate.reconnect({
            gid: "g",
            p: [0, 1, 2, 3].map((s) => ({ s, nm: `p${s}`, ai: s !== 0 })),
            dl: 3,
            dd: [
                [1, 1],
                [1, 1],
            ],
            s: 0,
            w: 0,
            n: 2,
            cp: 0,
            di: [132],
            h: 0,
            r: 0,
            mt: hand,
            dc: [1, 1],
            tr: 68,
            pst: [0, 1, 2, 3].map((s) => ({
                s,
                sc: 250,
                dsc: s === 3 ? [{ ti: 127 }] : [],
                ml: [],
                ri: false,
                tc: s === 0 ? 14 : 13,
            })),
            f: false,
            rh: [],
            wi: 7,
            tm: { ...TIMER_SETTINGS, bk: 12 },
        });
        table.receive(draw(0, 120, { wi: 7 }));
        table.decide({ dapai: "z4_" });

        expect(table.player.countdowns).toEqual([[5, 12]]);
        expect(table.player.model.jushu).toBe(1);
        expect(table.player.shoupai.toString()).toBe("m12305p123s123z12z4");
        expect(table.sent).toEqual([{ t: 3, a: 0, ti: 120, wi: 7 }]);
    });
});
