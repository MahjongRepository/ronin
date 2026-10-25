import { describe, expect, it } from "vitest";

import "../majiang.js";
import RONIN_RULE from "../ronin/rules.js";
import { SAMPLE_PLAYERS } from "../storybook/board-page.js";
import {
    DECISION_VARIANTS,
    TABLE_VARIANTS,
    createTableModel,
    dealDecision,
} from "../storybook/in-round.js";

const TILE_SET_SIZE = 136;
const DEAD_WALL_SIZE = 14;
const COPIES_PER_TILE = 4;
const RED_FIVE = "0";

function playDecisionModel({ hand, events }) {
    const model = new Majiang.Board({ title: "", player: [...SAMPLE_PLAYERS], qijia: 0 });
    model.qipai(dealDecision(hand));
    for (const event of events) {
        const [[type, data]] = Object.entries(event);
        model[type](data);
    }
    return model;
}

const SAMPLES = [
    ...DECISION_VARIANTS.map((variant) => [`decisions/${variant.key}`, playDecisionModel(variant)]),
    ...TABLE_VARIANTS.filter((variant) => variant.table).map((variant) => [
        `table/${variant.key}`,
        createTableModel(variant.table),
    ]),
];

function concealedTiles(shoupai) {
    return ["m", "p", "s", "z"].flatMap((s) =>
        shoupai._bingpai[s].flatMap((count, n) => {
            if (n === 0) {
                return [];
            }
            const red = s !== "z" && n === 5 ? shoupai._bingpai[s][0] : 0;
            return [...Array(count - red).fill(`${s}${n}`), ...Array(red).fill(`${s}${RED_FIVE}`)];
        }),
    );
}

function meldTiles(meld) {
    return meld.match(/\d/g).map((n) => `${meld[0]}${n}`);
}

function handTiles(shoupai) {
    return [...concealedTiles(shoupai), ...shoupai._fulou.flatMap(meldTiles)];
}

function riverTiles(he) {
    return he._pai.filter((p) => !/[+=-]/.test(p)).map((p) => p.slice(0, 2));
}

function shownTiles(model) {
    return [
        ...model.shoupai.flatMap(handTiles),
        ...model.he.flatMap(riverTiles),
        ...model.shan.baopai,
    ];
}

function countBy(tiles, key) {
    const counts = {};
    for (const tile of tiles) {
        counts[key(tile)] = (counts[key(tile)] ?? 0) + 1;
    }
    return counts;
}

describe("storybook in-round samples", () => {
    it.each(SAMPLES)("%s shows at most four of a tile and the rule's red fives", (_, model) => {
        const tiles = shownTiles(model);
        const copies = countBy(tiles, (p) => p.replace(RED_FIVE, "5"));
        const redFives = countBy(
            tiles.filter((p) => p[1] === RED_FIVE),
            (p) => p[0],
        );

        expect(Object.entries(copies).filter(([, n]) => n > COPIES_PER_TILE)).toEqual([]);
        expect(Object.entries(redFives).filter(([s, n]) => n > RONIN_RULE.赤牌[s])).toEqual([]);
    });

    it.each(SAMPLES)("%s accounts for all 136 tiles and a dora per kan", (_, model) => {
        const inHands = model.shoupai.reduce(
            (sum, shoupai) => sum + handTiles(shoupai).length + shoupai._bingpai._,
            0,
        );
        const inRivers = model.he.flatMap(riverTiles).length;
        const kans = model.shoupai.flatMap((shoupai) =>
            shoupai._fulou.filter((meld) => meldTiles(meld).length === COPIES_PER_TILE),
        );

        expect(inHands + inRivers + DEAD_WALL_SIZE + model.shan.paishu).toBe(TILE_SET_SIZE);
        expect(model.shan.baopai).toHaveLength(kans.length + 1);
    });
});
