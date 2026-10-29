import $ from "jquery";

import rules from "../ronin/rules.js";
import { t } from "../../i18n/index.js";
import { DRAW_CODE } from "../ronin/draws.js";
import { huleMessage, jiejuStandings, pingjuMessage } from "../ronin/results.js";
import { replayPath } from "../routes.js";
import { SAMPLE_PLAYERS, currentVariant, renderVariantNav, showBoardPage } from "./board-page.js";

const VIEWPOINT = 0;
const QIJIA = 0;
const SAMPLE_GAME_ID = "storybook-sample";
const NO_PAYMENTS = Object.freeze([0, 0, 0, 0]);

const YAKU = Object.freeze({
    RIICHI: 1,
    RINSHAN: 5,
    PINFU: 12,
    TANYAO: 13,
    HAKU: 15,
    HATSU: 16,
    ITTSU: 27,
    HONITSU: 36,
    SUUANKOU: 102,
    DAISANGEN: 103,
    SUUKANTSU: 106,
    DORA: 120,
    AKA_DORA: 121,
    URA_DORA: 122,
});

const MODEL_ACTIONS = Object.freeze({
    qipai: "qipai",
    zimo: "zimo",
    gangzimo: "zimo",
    dapai: "dapai",
    fulou: "fulou",
    gang: "gang",
    kaigang: "kaigang",
    hule: "hule",
    pingju: "pingju",
});

function turn(l, token) {
    const [draw, discard] = token.includes(">") ? token.split(">") : [token.slice(0, 2), token];
    return [{ zimo: { l, p: draw } }, { dapai: { l, p: discard } }];
}

function rotation(rivers) {
    const tokens = rivers.map((river) => river.split(" "));
    const cycles = Math.max(...tokens.map((river) => river.length));
    return Array.from({ length: cycles }, (_, i) =>
        tokens.flatMap((river, l) => (river[i] ? turn(l, river[i]) : [])),
    ).flat();
}

function yaku(...entries) {
    return entries.map(([yi, han]) => ({ yi, han }));
}

function hule({ baojia = null, ...win }) {
    return huleMessage({ baojia, ...win });
}

function pingju(code, fenpei, draw = {}) {
    return pingjuMessage({ code, fenpei, ...draw });
}

export const WIN_SAMPLES = Object.freeze([
    {
        key: "ron",
        title: "Riichi ron with ura-dora",
        round: { zhuangfeng: 0, jushu: 1, changbang: 0, lizhibang: 0 },
        defen: [29000, 21000, 25000, 25000],
        baopai: "p9",
        hand: "m23p234678s345z17",
        events: rotation([
            "z4 m9 p1 z6 s2",
            "z3 p9 s9_ s8 m4",
            "s1 z2 m1 p8",
            "s6>z1 m9_ s6>z7* p1_",
        ]),
        end: hule({
            l: 3,
            baojia: 1,
            shoupai: "m23p234678s34566m4*",
            hr: {
                han: 4,
                fu: 30,
                yk: yaku([YAKU.RIICHI, 1], [YAKU.PINFU, 1], [YAKU.TANYAO, 1], [YAKU.URA_DORA, 1]),
                pt: 80,
            },
            fenpei: [0, -8000, 0, 9000],
            fubaopai: ["s2"],
        }),
    },
    {
        key: "tsumo",
        title: "Opponent tsumo with open melds",
        round: { zhuangfeng: 0, jushu: 2, changbang: 1, lizhibang: 1 },
        defen: [28000, 21000, 24000, 26000],
        baopai: "p4",
        hand: "m5p1234789s2468z3",
        events: [
            ...rotation(["z1", "p9", "z4_", "s1"]),
            ...turn(0, "m7"),
            { fulou: { l: 1, m: "m7-89" } },
            { dapai: { l: 1, p: "s5" } },
            ...turn(2, "p5>z3"),
            ...turn(3, "z2"),
            ...turn(0, "p2"),
            ...turn(1, "z6"),
            ...turn(2, "z5_"),
            { fulou: { l: 1, m: "z555+" } },
            { dapai: { l: 1, p: "p3" } },
            ...turn(2, "s3>m5"),
            ...turn(3, "p8"),
            ...turn(0, "s7"),
            { zimo: { l: 1, p: "m6" } },
        ],
        end: hule({
            l: 1,
            shoupai: "m12340z77m6,m7-89,z555+",
            hr: {
                han: 5,
                fu: 30,
                yk: yaku([YAKU.HAKU, 1], [YAKU.ITTSU, 1], [YAKU.HONITSU, 2], [YAKU.AKA_DORA, 1]),
                pt: 80,
            },
            fenpei: [-4100, 9300, -2100, -2100],
        }),
    },
    {
        key: "yakuman",
        title: "Dealer yakuman tsumo",
        round: { zhuangfeng: 1, jushu: 0, changbang: 0, lizhibang: 0 },
        defen: [18000, 32000, 27000, 23000],
        baopai: "m4",
        hand: "m2229p144s888z114",
        events: [
            ...rotation(["m9>z4 p4>p1 z6_", "z3 p9 m8", "s1 z7 p2", "m1 s9_ z2"]),
            { zimo: { l: 0, p: "z1" } },
        ],
        end: hule({
            l: 0,
            shoupai: "m22299p444s888z11z1",
            hr: { han: 13, fu: 50, yk: yaku([YAKU.SUUANKOU, 13]), pt: 480 },
            fenpei: [48000, -16000, -16000, -16000],
        }),
    },
    {
        key: "kan-dora",
        title: "Rinshan tsumo with kan dora",
        round: { zhuangfeng: 0, jushu: 3, changbang: 2, lizhibang: 0 },
        defen: [24000, 22000, 30000, 24000],
        baopai: "s5",
        hand: "m345p77s2678z4666",
        events: [
            ...rotation(["z1", "p9>z4", "s9", "s1"]),
            ...turn(0, "p7"),
            { fulou: { l: 1, m: "p777-" } },
            { dapai: { l: 1, p: "p9" } },
            ...turn(2, "z3"),
            ...turn(3, "m1"),
            ...turn(0, "m9"),
            { zimo: { l: 1, p: "p7" } },
            { gang: { l: 1, m: "p777-7" } },
            { gangzimo: { l: 1, p: "z2" } },
            { dapai: { l: 1, p: "z2_" } },
            { kaigang: { baopai: "z1" } },
            ...turn(2, "p2"),
            ...turn(3, "z7"),
            ...turn(0, "s9"),
            { zimo: { l: 1, p: "z6" } },
            { gang: { l: 1, m: "z6666" } },
            { kaigang: { baopai: "m2" } },
            { gangzimo: { l: 1, p: "s2" } },
        ],
        end: hule({
            l: 1,
            shoupai: "m345s2678s2,p777-7,z6666",
            hr: {
                han: 4,
                fu: 70,
                yk: yaku([YAKU.HATSU, 1], [YAKU.RINSHAN, 1], [YAKU.DORA, 2]),
                pt: 80,
            },
            fenpei: [-4200, 8600, -2200, -2200],
        }),
    },
    {
        key: "four-kan",
        title: "Four kans, tanki ron",
        round: { zhuangfeng: 0, jushu: 1, changbang: 0, lizhibang: 0 },
        defen: [26000, 23000, 27000, 24000],
        baopai: "s3",
        hand: "m13456p1469s237z7",
        events: [
            ...rotation(["z1", "z4", "m9", "s9_"]),
            ...turn(0, "s8"),
            { fulou: { l: 1, m: "s8888-" } },
            { gangzimo: { l: 1, p: "z6" } },
            { dapai: { l: 1, p: "z6_" } },
            { kaigang: { baopai: "m7" } },
            ...turn(2, "p9"),
            ...turn(3, "s1>p4"),
            { fulou: { l: 1, m: "p4444=" } },
            { gangzimo: { l: 1, p: "p1" } },
            { dapai: { l: 1, p: "p1_" } },
            { kaigang: { baopai: "p2" } },
            ...turn(2, "m2"),
            { fulou: { l: 1, m: "m2222+" } },
            { gangzimo: { l: 1, p: "m9" } },
            { dapai: { l: 1, p: "m9_" } },
            { kaigang: { baopai: "s5" } },
            ...turn(2, "z2"),
            ...turn(3, "z3_"),
            ...turn(0, "m8"),
            { zimo: { l: 1, p: "z5" } },
            { gang: { l: 1, m: "z5555" } },
            { kaigang: { baopai: "z3" } },
            { gangzimo: { l: 1, p: "m1" } },
            { dapai: { l: 1, p: "m1_" } },
            ...turn(2, "z1"),
            ...turn(3, "p5>z7"),
        ],
        end: hule({
            l: 1,
            baojia: 3,
            shoupai: "z7z7,s8888-,p4444=,m2222+,z5555",
            hr: { han: 13, fu: 80, yk: yaku([YAKU.SUUKANTSU, 13]), pt: 320 },
            fenpei: [0, 32000, 0, -32000],
        }),
    },
    {
        key: "double-ron",
        title: "Double ron, shown win by win",
        round: { zhuangfeng: 0, jushu: 0, changbang: 1, lizhibang: 1 },
        defen: [27000, 24000, 26000, 22000],
        baopai: "p1",
        hand: "p22234678s78z666",
        events: rotation([
            "z1_ m9_ p9_ s1_ z2_ m1_",
            "z4 m1 s9 p1 z7 m8",
            "z3 p9 m9 z5 s2 s6",
            "z2 s1 m9 p1* z4_",
        ]),
        end: [
            hule({
                l: 3,
                baojia: 2,
                shoupai: "m234678p567s4588s6*",
                hr: {
                    han: 3,
                    fu: 30,
                    yk: yaku([YAKU.RIICHI, 1], [YAKU.PINFU, 1], [YAKU.TANYAO, 1]),
                    pt: 39,
                },
                fenpei: [0, 0, -4200, 6200],
                fubaopai: ["z1"],
                page: { number: 1, count: 2 },
            }),
            hule({
                l: 0,
                baojia: 2,
                shoupai: "p22234678s78z666s6",
                hr: { han: 4, fu: 40, yk: yaku([YAKU.HATSU, 1], [YAKU.DORA, 3]), pt: 120 },
                fenpei: [12300, 0, -12300, 0],
                page: { number: 2, count: 2 },
            }),
        ],
    },
    {
        key: "pao",
        title: "Pao ron with a head-bumped caller",
        round: { zhuangfeng: 0, jushu: 0, changbang: 0, lizhibang: 0 },
        defen: [26000, 24000, 25000, 25000],
        baopai: "s3",
        hand: "m1569p147s2569z24",
        events: [
            ...rotation(["z1", "p9", "m9", "s1"]),
            ...turn(0, "z6"),
            { fulou: { l: 1, m: "z666-" } },
            { dapai: { l: 1, p: "s9" } },
            ...turn(2, "z5"),
            { fulou: { l: 1, m: "z555+" } },
            { dapai: { l: 1, p: "p1" } },
            ...turn(2, "m1"),
            ...turn(3, "z7"),
            { fulou: { l: 1, m: "z777=" } },
            { dapai: { l: 1, p: "s2" } },
            ...turn(2, "p8"),
            ...turn(3, "m8"),
            ...turn(0, "m4"),
        ],
        end: hule({
            l: 1,
            baojia: 0,
            shoupai: "m23p55m4,z555+,z666-,z777=",
            hr: { han: 13, fu: 40, yk: yaku([YAKU.DAISANGEN, 13]), pt: 320 },
            fenpei: [-16000, 32000, 0, -16000],
            pao: 3,
            headBumped: [2],
        }),
    },
]);

export const DRAW_SAMPLES = Object.freeze([
    {
        key: "exhaustive",
        title: "Exhaustive draw, two tenpai",
        round: { zhuangfeng: 1, jushu: 1, changbang: 0, lizhibang: 0 },
        defen: [31000, 22000, 20000, 27000],
        baopai: "p4",
        hand: "m1456p3789s238z17",
        events: rotation([
            "z4 p9 m1 s9 z6 p1 z3 m9 s2 p8 z5 s3 m3 p2 s6 m6 z1 p3",
            "z1 m9 s1 p9 z4 m2* s9_ p1_ z6_ m1_ s1_ z3_ p8_ s3_ m7_ z5_ s7_ s2_",
            "z3 s1 p1 m9 z5 s9 z6 p9 m1 z4 s2 p7 m4 s7 p6 m6 z1",
            "s4>z1 z7>m1 s8>p3 p1_ m9_ z3_ s1_ z5_ p2_ m3_ z4_ s9_ p6_ m7_ z6_ s5_ m2_",
        ]),
        end: pingju(DRAW_CODE.EXHAUSTIVE, [-1500, 1500, -1500, 1500], {
            shoupai: [null, "m88p234067s567z22", null, "m456p789s23488z77"],
            tenpai: [false, true, false, true],
        }),
    },
    {
        key: "nine-terminals",
        title: "Kyuushu Kyuuhai",
        round: { zhuangfeng: 0, jushu: 2, changbang: 0, lizhibang: 0 },
        defen: [27000, 23000, 25000, 25000],
        baopai: "s4",
        hand: "m1469p157s39z1236",
        events: [...rotation(["p5", "s8"]), { zimo: { l: 2, p: "z7" } }],
        end: pingju(DRAW_CODE.NINE_TERMINALS, NO_PAYMENTS, { players: [2] }),
    },
    {
        key: "four-riichi",
        title: "Four riichi",
        round: { zhuangfeng: 0, jushu: 0, changbang: 0, lizhibang: 0 },
        defen: [25000, 25000, 25000, 25000],
        baopai: "m4",
        hand: "m1237p456s5789z14",
        events: rotation([
            "m8>z4 s5>z1 z7_* p1_",
            "z2 p7 s1* p8_",
            "p9 z3 s2 m1*",
            "s9 z5 p2_ z1*",
        ]),
        end: pingju(DRAW_CODE.FOUR_RIICHI, NO_PAYMENTS),
    },
    {
        key: "nagashi",
        title: "Nagashi mangan",
        round: { zhuangfeng: 0, jushu: 3, changbang: 1, lizhibang: 1 },
        defen: [26000, 23000, 24000, 26000],
        baopai: "p6",
        hand: "m1357p2468s1357z1",
        events: rotation([
            "p9 z2 m1 s9 p1 z3 m6 s7 z6 p8 m7 s2 p3 z5 m8 s6 p2 z7",
            "m9>z1 s9_ p5_ z2_ m4_ s8_ p7_ z4_ m6_ s2_ p3_ z6_ m8_ s4_ p1_ p9_ s6_ z3_",
            "z1 m9 p1 z5 s9 z7 m1 p9 z2 s1 z6 m9 z3 p1 s9 z4 m1",
            "z1 z7 m9 p9 z5 s1 p2 z6 m7 p7 z3 s2 p8_ m3_ z2_ s8_ p4_",
        ]),
        end: pingju(DRAW_CODE.NAGASHI, [-4000, -2000, 8000, -2000], {
            shoupai: [null, null, null, "m34p555s345678z44"],
            tenpai: [false, false, false, true],
            players: [2],
        }),
    },
]);

const GAME_ROUNDS = Object.freeze([
    {
        round: [0, 0, 0],
        riichi: [0],
        hule: { l: 0, baojia: null, fenpei: [7000, -2000, -2000, -2000] },
    },
    { round: [0, 0, 1], hule: { l: 2, baojia: 1, fenpei: [0, -2300, 2300, 0] } },
    {
        round: [0, 1, 0],
        riichi: [3],
        pingju: { code: DRAW_CODE.EXHAUSTIVE, fenpei: [1500, -1500, -1500, 1500] },
    },
    {
        round: [0, 1, 1],
        riichi: [2],
        hule: { l: 2, baojia: null, fenpei: [-4100, -2100, 10300, -2100] },
    },
    { round: [0, 2, 0], hule: { l: 2, baojia: 0, fenpei: [-3900, 0, 3900, 0] } },
    { round: [0, 3, 0], pingju: { code: DRAW_CODE.NINE_TERMINALS, fenpei: NO_PAYMENTS } },
    { round: [0, 3, 1], riichi: [1], hule: { l: 2, baojia: 1, fenpei: [0, -5500, 6500, 0] } },
    { round: [1, 0, 0], hule: { l: 0, baojia: null, fenpei: [12000, -4000, -4000, -4000] } },
    {
        round: [1, 0, 1],
        pingju: {
            code: DRAW_CODE.EXHAUSTIVE,
            fenpei: NO_PAYMENTS,
            tenpai: [false, false, false, false],
        },
    },
    { round: [1, 1, 2], hule: { l: 2, baojia: 1, fenpei: [0, -2600, 2600, 0] } },
    {
        round: [1, 2, 0],
        riichi: [0],
        hule: { l: 3, baojia: null, fenpei: [-2000, -1000, -1000, 5000] },
    },
]);

const EXHAUSTIVE_SAMPLE = DRAW_SAMPLES.find((sample) => sample.key === "exhaustive");

export const FINAL_ROUND = Object.freeze({
    round: { zhuangfeng: 1, jushu: 3, changbang: 0, lizhibang: 0 },
    defen: [28400, 37800, 25600, 8200],
    baopai: EXHAUSTIVE_SAMPLE.baopai,
    hand: "m88p234067s567z22",
    events: EXHAUSTIVE_SAMPLE.events,
    end: EXHAUSTIVE_SAMPLE.end,
});

const GAME_END = Object.freeze({
    ws: 0,
    st: [
        { s: 0, sc: 393, fs: 49 },
        { s: 3, sc: 269, fs: 7 },
        { s: 1, sc: 241, fs: -16 },
        { s: 2, sc: 97, fs: -40 },
    ],
    lb: 10,
});

const FOUR_KAN_SAMPLE = WIN_SAMPLES.find((sample) => sample.key === "four-kan");

const BUST_ROUNDS = Object.freeze([
    { round: [0, 0, 0], hule: { l: 2, baojia: 0, fenpei: [-2000, 0, 2000, 0] } },
]);

const BUST_FINAL_ROUND = Object.freeze({
    round: FOUR_KAN_SAMPLE.round,
    defen: [25000, 27000, 25000, 23000],
    baopai: FOUR_KAN_SAMPLE.baopai,
    hand: FOUR_KAN_SAMPLE.hand,
    events: FOUR_KAN_SAMPLE.events,
    end: FOUR_KAN_SAMPLE.end,
});

const BUST_GAME_END = Object.freeze({
    ws: 2,
    st: [
        { s: 2, sc: 590, fs: 69 },
        { s: 1, sc: 250, fs: 5 },
        { s: 3, sc: 250, fs: -15 },
        { s: 0, sc: -90, fs: -59 },
    ],
    lb: 0,
});

const STANDINGS_SAMPLES = Object.freeze([
    {
        key: "riichi",
        title: "Hanchan with riichi deposits",
        rounds: GAME_ROUNDS,
        final: FINAL_ROUND,
        gameEnd: GAME_END,
    },
    {
        key: "no-riichi",
        title: "Bust after two hands, no riichi",
        rounds: BUST_ROUNDS,
        final: BUST_FINAL_ROUND,
        gameEnd: BUST_GAME_END,
    },
]);

function viewpointSeatIndex(jushu) {
    return (VIEWPOINT - QIJIA - jushu + 8) % 4;
}

export function sampleLog({ round, defen, baopai, hand, events, end }) {
    const viewpointL = viewpointSeatIndex(round.jushu);
    const shoupai = SAMPLE_PLAYERS.map((_, l) => (l === viewpointL ? hand : ""));
    return [{ qipai: { ...round, defen, baopai, shoupai } }, ...events, end];
}

function summaryLog({ round: [zhuangfeng, jushu, changbang], riichi = [], ...end }) {
    const riichiTurns = riichi.flatMap((l) => [
        { dapai: { l, p: "z1*" } },
        { zimo: { l: (l + 1) % 4 } },
    ]);
    return [{ qipai: { zhuangfeng, jushu, changbang } }, ...riichiTurns, end];
}

function playEvent(model, event) {
    const [type, data] = Object.entries(event)[0];
    const hiddenDraw = MODEL_ACTIONS[type] === "zimo" && data.l !== viewpointSeatIndex(model.jushu);
    model[MODEL_ACTIONS[type]](hiddenDraw ? { l: data.l } : data);
}

export function createRoundModel(log) {
    const model = new Majiang.Board({
        title: t("game.type.hanchan"),
        player: [...SAMPLE_PLAYERS],
        qijia: QIJIA,
    });
    for (const event of log) {
        playEvent(model, event);
    }
    return model;
}

function createJieju(gameEnd, log) {
    const player = [...SAMPLE_PLAYERS];
    return {
        title: t("game.type.hanchan"),
        rule: rules,
        player,
        qijia: QIJIA,
        ...jiejuStandings(gameEnd),
        log,
        replayUrl: replayPath(SAMPLE_GAME_ID, VIEWPOINT),
    };
}

/** Show a round's results the way a player sees them: the first at once, each next one when its 次へ is clicked. */
function showResults(board, model, [result, ...rest]) {
    board.update(result);
    if (!rest.length) {
        return;
    }
    $(".hule-dialog .next").one("click", () => {
        playEvent(model, rest[0]);
        showResults(board, model, rest);
    });
}

function showRoundEndPage(header, pai, variants) {
    const sample = currentVariant(variants);
    header.append(renderVariantNav(variants, sample));
    const [first, ...rest] = [sample.end].flat();
    const model = createRoundModel(sampleLog({ ...sample, end: first }));
    const board = showBoardPage(header, pai, model, { viewpoint: VIEWPOINT });
    board.sound_on = false;
    showResults(board, model, [first, ...rest]);
}

export function showWinPage(header, pai) {
    showRoundEndPage(header, pai, WIN_SAMPLES);
}

export function showDrawPage(header, pai) {
    showRoundEndPage(header, pai, DRAW_SAMPLES);
}

export function showStandingsPage(header, pai) {
    const sample = currentVariant(STANDINGS_SAMPLES);
    header.append(renderVariantNav(STANDINGS_SAMPLES, sample));
    const finalLog = sampleLog(sample.final);
    const paipu = createJieju(sample.gameEnd, [...sample.rounds.map(summaryLog), finalLog]);
    const model = createRoundModel(finalLog);
    model.jieju(paipu);
    showBoardPage(header, pai, model, { viewpoint: VIEWPOINT }).summary(paipu);
}
