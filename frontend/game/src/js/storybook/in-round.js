import $ from "jquery";

import { showChat } from "../ronin/chat.js";
import { NO_OFFER } from "../ronin/offer.js";
import RoninPlayer from "../ronin/player.js";
import RONIN_RULE from "../ronin/rules.js";
import Shadow from "../ronin/shadow.js";
import Translate from "../ronin/translate.js";
import wire from "../ronin/wire.js";
import { SAMPLE_PLAYERS, currentVariant, renderVariantNav, showBoardPage } from "./board-page.js";

const VIEWPOINT = 0;
const GAME_TITLE = "半荘戦";

const EAST_ONE = Object.freeze({
    zhuangfeng: 0,
    jushu: 0,
    changbang: 0,
    lizhibang: 0,
    defen: SAMPLE_PLAYERS.map(() => 25000),
});

function ownTurn(draw, discard = `${draw}_`) {
    return [{ zimo: { l: VIEWPOINT, p: draw } }, { dapai: { l: VIEWPOINT, p: discard } }];
}

function hiddenTurns(...discards) {
    return discards.flatMap((p, i) => [{ zimo: { l: i + 1 } }, { dapai: { l: i + 1, p } }]);
}

function goAround(own, ...others) {
    return [...ownTurn(own), ...hiddenTurns(...others)];
}

const OPENING = Object.freeze(goAround("z7", "z4", "s9", "m9"));

const DECISION_VARIANTS = Object.freeze([
    {
        key: "turn",
        title: "Tsumo, riichi or kan",
        hand: "m11112p567s789z55",
        events: [
            ...OPENING,
            ...goAround("p9", "z6", "s1", "p1"),
            { zimo: { l: VIEWPOINT, p: "m3" } },
        ],
        offer: { tsumo: true, riichi: true, gang: ["m1111"] },
    },
    {
        key: "call",
        title: "Chi, pon or kan on a discard",
        hand: "m234p23334s678z11",
        events: [...OPENING, ...ownTurn("p9"), ...hiddenTurns("z6", "s1", "p3")],
        offer: { chi: ["p23-4"], peng: ["p333-"], gang: ["p3333-"] },
    },
    {
        key: "ron",
        title: "Ron on a discard",
        hand: "m234p456s678s99z11",
        events: [...OPENING, ...ownTurn("p9"), ...hiddenTurns("z6", "z1")],
        offer: { ron: true },
    },
    {
        key: "chi",
        title: "Choosing a chi",
        hand: "m3467p234s567z223",
        events: [...OPENING, ...ownTurn("p9"), ...hiddenTurns("z6", "s1", "m5")],
        offer: { chi: ["m345-", "m45-6", "m5-67"] },
        press: "chi",
    },
    {
        key: "riichi",
        title: "Riichi discard",
        hand: "m234567p234s99z11",
        events: [
            ...OPENING,
            ...goAround("p9", "z6", "m1", "p1"),
            { zimo: { l: VIEWPOINT, p: "p5" } },
        ],
        offer: { riichi: true },
        press: "lizhi",
    },
    {
        key: "after-riichi",
        title: "After riichi",
        hand: "m234567p234888z1",
        events: [
            ...OPENING,
            ...ownTurn("s9", "z1*"),
            ...hiddenTurns("z6", "m1", "p1"),
            ...goAround("z5", "p9", "s2", "m8"),
            { zimo: { l: VIEWPOINT, p: "p8" } },
        ],
        offer: { gang: ["p8888"] },
    },
    {
        key: "kyuushu",
        title: "Kyuushu kyuuhai",
        hand: "m159p159s159z1234",
        events: [{ zimo: { l: VIEWPOINT, p: "z5" } }],
        offer: { kyuushu: true },
    },
]);

const MID_ROUND = Object.freeze({
    round: EAST_ONE,
    shoupai: ["m22456p3478s3567", "", "", ""],
    rivers: ["z1 m9 p1 z4 s9 z7", "z2 s1 m1 p9 z3 m8", "z3 p9 z6 m9 s8 p1", "z4 z1 s9 m1 p8"],
    dora: ["p6"],
    paishu: 46,
    lunban: 3,
});

const TABLE_VARIANTS = Object.freeze([
    {
        key: "rivers",
        title: "Long rivers",
        table: {
            round: { ...EAST_ONE, lizhibang: 3, defen: [24000, 24000, 24000, 25000] },
            shoupai: ["m123456789p11z77*", "", "", ""],
            rivers: [
                "z1 z3 p9 s1 z4 m1 s9 p8 z6 s2 p7 m9 s8 z5 p6* s7_ p2_ z2_ s6_ p3_",
                "z2 z4 m1 s9 p1 z6 m8 s1 p9 z3 m2 s8 p7 m7 s2 m3* s3_ p4_ m4_",
                "z3 z1 s9 m9 p1 z4 p8 s1 m2 z6 s7 m8 p2 z5 s6* p0_ m6_ s4_",
                "z4 z2 m1 p9 s9 z3 s1 m8 p8 z6 m7 p7 s8 p3 m6 z1 s5*",
            ],
            dora: ["s3"],
            paishu: 0,
            lunban: 3,
        },
    },
    {
        key: "melds",
        title: "Four melds each",
        table: {
            round: EAST_ONE,
            shoupai: [
                "s9,m1-23,p777=,s2222+,z666-",
                "_,m777+,p2-34,z2222,s3-45",
                "_,m999=,p888-,s7-89,z444+",
                "_,s111=,m2-34,p999+,z333-",
            ],
            rivers: [
                "z1 m9 p1 s9 z7 m8 p6 s6 z3 m5 s4",
                "z1 s9 p8 m1 s8 s7 m6 p6 z7 s6 p5",
                "p1 s9 m1 z1 m4 m6 z7 s4 m8 p5",
                "p3 s5 m3 s8 m8 z4 p6 m5 s4 z1 z5",
            ],
            dora: ["s6", "m4", "p1"],
            paishu: 24,
            lunban: 0,
        },
    },
    {
        key: "dora",
        title: "Five dora, last tiles",
        table: {
            round: EAST_ONE,
            shoupai: ["m234567p345s678z2", "", "", "_,m1111,p9999=,z7777,s5550-"],
            rivers: [
                "z1 z3 p3 s1 m9 z6 p1 s9 m8 p8 z4 s2 m6 p7 z5 s7",
                "z4 z1 s9 m9 p1 z6 s1 p8 m2 z3 s8 p7 m7 z5 s4 p2_ m3",
                "z3 z4 m9 p1 s1 z5 p8 s9 m2 z6 s8 p6 m6 s2 p2 m3",
                "z2 z3 p1 m9 s1 z6 s9 p8 m2 z5 s8 m3 p7 s4 p6 z2",
            ],
            dora: ["s3", "m8", "z1", "p4", "s6"],
            paishu: 1,
            lunban: 3,
        },
    },
    {
        key: "south",
        title: "South 3, sitting West",
        table: {
            round: {
                zhuangfeng: 1,
                jushu: 2,
                changbang: 8,
                lizhibang: 5,
                defen: [18700, 5000, 0, 71300],
            },
            shoupai: ["", "", "m345p34567s345z66*", ""],
            rivers: [
                "z1 m9 p1 s9 z4 m1 p8 s1",
                "z2 s9 m1 z1 p9 s1 m8 p2 z4",
                "z3 p9 m9 z4 s1 s8* p1_ m2_",
                "z4 z1 m1 p9 s9 m8 z3 p2",
            ],
            dora: ["z7"],
            paishu: 37,
            lunban: 1,
        },
    },
    {
        key: "calls",
        title: "Call bubbles",
        table: MID_ROUND,
        say: [
            ["lizhi", 0],
            ["gang", 1],
            ["peng", 2],
            ["chi", 3],
        ],
    },
    {
        key: "ron",
        title: "Double ron bubbles",
        table: MID_ROUND,
        say: [
            ["rong", 0],
            ["rong", 2],
        ],
    },
    { key: "tsumo", title: "Tsumo bubble", table: MID_ROUND, say: [["zimo", 0]] },
    {
        key: "chat",
        title: "Chat and a dropped player",
        table: MID_ROUND,
        chat: [
            [0, "gl hf"],
            [1, "ron"],
            [
                2,
                "that was a really long wait for the last tile, I almost fell asleep at the table, wake me up when it is my turn",
            ],
            [3, "よろしくお願いします"],
        ],
        connected: [true, true, true, false],
    },
    {
        key: "chat-calls",
        title: "Chat over call bubbles",
        table: MID_ROUND,
        say: [
            ["lizhi", 0],
            ["gang", 1],
            ["peng", 2],
            ["chi", 3],
        ],
        chat: [
            [0, "ロン"],
            [1, "sorry"],
            [2, "nice"],
            [3, "ツモ!"],
        ],
    },
    {
        key: "kaiju",
        title: "Game start",
        gameStarted: {
            t: wire.E.GAME_STARTED,
            gid: "3f2b6c1e-8a4d-4f0b-9c7e-5d1a2b3c4d5e",
            gt: wire.GAME_TYPE.HANCHAN,
            dl: 0,
            dd: [
                [1, 1],
                [1, 1],
            ],
            p: SAMPLE_PLAYERS.map((nm, s) => ({ s, nm, ai: s !== VIEWPOINT })),
        },
    },
]);

function playDecision(header, pai, { hand, events, offer, press }) {
    const player = new RoninPlayer($("#board"), pai, Majiang.UI.audio($("#loaddata")));
    const kaiju = {
        id: VIEWPOINT,
        title: GAME_TITLE,
        rule: RONIN_RULE,
        player: [...SAMPLE_PLAYERS],
        qijia: 0,
    };
    player.action({ kaiju });
    player.action({ qipai: { ...EAST_ONE, baopai: "s3", shoupai: [hand, "", "", ""] } });
    for (const event of events.slice(0, -1)) {
        player.action(event);
    }

    player.view = showBoardPage(header, pai, player.model, { viewpoint: VIEWPOINT });
    player.view.sound_on = false;
    player.offer = { ...NO_OFFER, ...offer };
    player.action(events.at(-1), () => {});
    if (press) {
        $(`#board .player-button .${press}`).trigger("click");
    }
}

function createTableModel({ round, shoupai, rivers, dora, paishu, lunban }) {
    const model = new Majiang.Board({ title: GAME_TITLE, player: [...SAMPLE_PLAYERS], qijia: 0 });
    model.qipai({ ...round, shoupai, baopai: dora[0] });
    rivers.forEach((river, l) => {
        for (const tile of river.split(" ")) {
            model.he[l].dapai(tile);
        }
    });
    for (const baopai of dora.slice(1)) {
        model.kaigang({ baopai });
    }
    model.shan.paishu = paishu;
    model.lunban = lunban;
    return model;
}

function drawTable(header, pai, { table, say = [], chat = [], connected }) {
    const board = showBoardPage(header, pai, createTableModel(table), { viewpoint: VIEWPOINT });
    board.sound_on = false;
    for (const [name, l] of say) {
        board.say(name, l);
    }
    for (const [l, text] of chat) {
        showChat(board, l, text);
    }
    if (connected) {
        board.players(connected);
    }
}

function showGameStart(header, pai, { gameStarted }) {
    const player = new RoninPlayer($("#board"), pai, Majiang.UI.audio($("#loaddata")));
    const translate = new Translate(player, new Shadow());
    translate.handle(gameStarted);

    player.view = showBoardPage(header, pai, player.model, { viewpoint: VIEWPOINT, dealt: false });
    player.view.sound_on = false;
    player.action({ kaiju: { ...translate.kaiju(), id: VIEWPOINT } });
}

function showTableVariant(header, pai, variant) {
    if (variant.gameStarted) {
        showGameStart(header, pai, variant);
    } else {
        drawTable(header, pai, variant);
    }
}

function showVariantPage(header, pai, variants, show) {
    const variant = currentVariant(variants);
    header.append(renderVariantNav(variants, variant));
    show(header, pai, variant);
}

export function showDecisionsPage(header, pai) {
    showVariantPage(header, pai, DECISION_VARIANTS, playDecision);
}

export function showTablePage(header, pai) {
    showVariantPage(header, pai, TABLE_VARIANTS, showTableVariant);
}
