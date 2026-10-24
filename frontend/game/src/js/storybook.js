import $ from "jquery";

import { STORYBOOK_PAGE, storybookPath } from "./routes.js";
import { SAMPLE_PLAYERS, showBoardPage } from "./storybook/board-page.js";
import { showDecisionsPage, showTablePage } from "./storybook/in-round.js";
import { showDrawPage, showStandingsPage, showWinPage } from "./storybook/round-end.js";

const PAGE_TITLES = Object.freeze({
    [STORYBOOK_PAGE.INDEX]: "Tiles",
    [STORYBOOK_PAGE.BOARD]: "Board",
    [STORYBOOK_PAGE.DISCARDS]: "Discards",
    [STORYBOOK_PAGE.HAND]: "Hand",
    [STORYBOOK_PAGE.MELDS]: "Melds",
    [STORYBOOK_PAGE.DECISIONS]: "Decisions",
    [STORYBOOK_PAGE.TABLE]: "Table",
    [STORYBOOK_PAGE.WIN]: "Win",
    [STORYBOOK_PAGE.DRAW]: "Draw",
    [STORYBOOK_PAGE.STANDINGS]: "Standings",
});

const TILE_SUITS = Object.freeze([
    ["m", [1, 2, 3, 4, 5, 0, 6, 7, 8, 9]],
    ["p", [1, 2, 3, 4, 5, 0, 6, 7, 8, 9]],
    ["s", [1, 2, 3, 4, 5, 0, 6, 7, 8, 9]],
    ["z", [1, 2, 3, 4, 5, 6, 7]],
]);
const TILE_BACK = "_";

const HAND_SAMPLES = Object.freeze([
    { title: "Closed hand with a drawn tile", hand: "m123p456s789z1122", draw: "z2", open: true },
    { title: "Red fives", hand: "m0556p0556s0556z1", open: true },
    { title: "Opponent's hand (face down)", hand: "m123p456s789z1122", draw: "z2", open: false },
    { title: "Single tile after four melds", hand: "s9,m1-23,p777=,s2222+,z666-", open: true },
]);

const MELD_SAMPLES = Object.freeze([
    { title: "Chi from the left", hand: "p456s789z1122,m1-23" },
    { title: "Pon from the right, across and left", hand: "s789z1,p555+,z666=,s777-" },
    { title: "Open kan with a red five, closed kan", hand: "p456s789z1,m5550=,z1111" },
    { title: "Added kan", hand: "p456s789z1122,p333+3" },
]);

const DISCARD_SAMPLES = Object.freeze([
    {
        title: "Tsumogiri tiles (dimmed) and a riichi tile (sideways)",
        discards: ["m1", "p9_", "z3", "s5*", "m0_", "z7", "p2", "s1"],
    },
    {
        title: "Three full rows, one tile called away",
        discards: ["z1", "z2", "m9_", "p1", "s9", "z5", "z6", "m2", "p8_", "s2", "z4", "m7"].concat(
            ["p3", "s6_", "m4", "p7", "s3", "z7", "m8_", "p6"],
        ),
        call: "p6-78",
    },
]);

const STARTING_POINTS = 25000;
const BOARD_EVENTS = Object.freeze([
    { zimo: { l: 0, p: "z4" } },
    { dapai: { l: 0, p: "z4_" } },
    { zimo: { l: 1 } },
    { dapai: { l: 1, p: "z3" } },
    { zimo: { l: 2 } },
    { dapai: { l: 2, p: "m1" } },
    { zimo: { l: 3 } },
    { dapai: { l: 3, p: "s9" } },
    { zimo: { l: 0, p: "p9" } },
    { dapai: { l: 0, p: "p9_" } },
    { zimo: { l: 1 } },
    { dapai: { l: 1, p: "z7" } },
    { zimo: { l: 2 } },
    { dapai: { l: 2, p: "z1" } },
    { fulou: { l: 0, m: "z111=" } },
    { dapai: { l: 0, p: "m1" } },
    { zimo: { l: 1 } },
    { dapai: { l: 1, p: "s1*" } },
    { zimo: { l: 2 } },
    { dapai: { l: 2, p: "m9" } },
    { fulou: { l: 3, m: "m789-" } },
    { dapai: { l: 3, p: "p1" } },
    { zimo: { l: 0, p: "z2" } },
]);

function renderNav(currentPage) {
    const links = Object.values(STORYBOOK_PAGE).map((page) =>
        $("<a>")
            .attr("href", storybookPath(page))
            .toggleClass("active", page === currentPage)
            .text(PAGE_TITLES[page]),
    );
    return $('<header class="storybook-header">').append(
        $("<h1>").text("Game Storybook"),
        $('<nav class="storybook-nav">').append(links),
    );
}

function renderSection(title, content) {
    return $('<section class="storybook-sample">').append($("<h2>").text(title), content);
}

function renderTiles(pai) {
    const rows = TILE_SUITS.map(([suit, numbers]) =>
        $('<div class="storybook-tile-row">').append(
            numbers.map((n) => renderTileCell(pai, `${suit}${n}`)),
        ),
    );
    const back = $('<div class="storybook-tile-row">').append(renderTileCell(pai, TILE_BACK));
    return [renderSection("Tile faces", rows), renderSection("Tile back", back)];
}

function renderTileCell(pai, tile) {
    return $('<figure class="storybook-tile">').append(pai(tile), $("<figcaption>").text(tile));
}

function createHandNode() {
    return $('<div class="shoupai">').append('<div class="bingpai">', '<div class="fulou">');
}

function renderHand(pai, { hand, draw, open = true }) {
    const shoupai = Majiang.Shoupai.fromString(hand);
    if (draw) {
        shoupai.zimo(draw);
    }
    const node = createHandNode();
    new Majiang.UI.Shoupai(node, pai, shoupai).redraw(open);
    return node;
}

function renderHands(pai) {
    return HAND_SAMPLES.map((sample) => renderSection(sample.title, renderHand(pai, sample)));
}

function renderMelds(pai) {
    return MELD_SAMPLES.map((sample) => renderSection(sample.title, renderHand(pai, sample)));
}

function renderRiver(pai, { discards, call }) {
    const he = new Majiang.He();
    for (const tile of discards) {
        he.dapai(tile);
    }
    if (call) {
        he.fulou(call);
    }
    const riichiStick = $('<img class="chouma">').attr(
        "src",
        `${import.meta.env.BASE_URL}img/1000.gif`,
    );
    const node = $('<div class="he">').append(
        $('<div class="lizhi">').append(riichiStick),
        '<div class="dapai">',
    );
    new Majiang.UI.He(node, pai, he).redraw();
    return node;
}

function renderDiscards(pai) {
    return DISCARD_SAMPLES.map((sample) => renderSection(sample.title, renderRiver(pai, sample)));
}

function createBoardModel() {
    const model = new Majiang.Board({ title: "Storybook", player: [...SAMPLE_PLAYERS], qijia: 0 });
    model.qipai({
        zhuangfeng: 0,
        jushu: 0,
        changbang: 1,
        lizhibang: 0,
        defen: SAMPLE_PLAYERS.map(() => STARTING_POINTS),
        baopai: "s3",
        shoupai: ["m123p405s789z1122", "", "", ""],
    });
    for (const event of BOARD_EVENTS) {
        const [type, data] = Object.entries(event)[0];
        model[type](data);
    }
    return model;
}

function showSampleBoard(header, pai) {
    showBoardPage(header, pai, createBoardModel());
}

const BOARD_PAGES = Object.freeze({
    [STORYBOOK_PAGE.BOARD]: showSampleBoard,
    [STORYBOOK_PAGE.DECISIONS]: showDecisionsPage,
    [STORYBOOK_PAGE.TABLE]: showTablePage,
    [STORYBOOK_PAGE.WIN]: showWinPage,
    [STORYBOOK_PAGE.DRAW]: showDrawPage,
    [STORYBOOK_PAGE.STANDINGS]: showStandingsPage,
});

const SAMPLE_PAGES = Object.freeze({
    [STORYBOOK_PAGE.INDEX]: renderTiles,
    [STORYBOOK_PAGE.DISCARDS]: renderDiscards,
    [STORYBOOK_PAGE.HAND]: renderHands,
    [STORYBOOK_PAGE.MELDS]: renderMelds,
});

export function showStorybook(page) {
    const pai = Majiang.UI.pai($("#loaddata"));
    const nav = renderNav(page);

    if (page in BOARD_PAGES) {
        BOARD_PAGES[page](nav, pai);
        return;
    }

    $("#space, #board").remove();
    $("body")
        .removeClass("board")
        .addClass("storybook")
        .append(nav, $('<main class="storybook-samples">').append(SAMPLE_PAGES[page](pai)));
}
