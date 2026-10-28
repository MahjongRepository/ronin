"use strict";

/**
 * Each draw's stable code, which every display looks its text up by (catalog key `draw.<code>`); an abortive draw's is
 * the round end's `rn`, and ABORTIVE stands for one the client has no code for.
 */
const DRAW_CODE = Object.freeze({
    EXHAUSTIVE:     'exhaustive',
    NAGASHI:        'nagashi',
    NINE_TERMINALS: 'nine_terminals',
    FOUR_RIICHI:    'four_riichi',
    TRIPLE_RON:     'triple_ron',
    FOUR_KANS:      'four_kans',
    FOUR_WINDS:     'four_winds',
    ABORTIVE:       'abortive',
});

/** The abortive draws a round end names by their code (`rn`). */
const ABORTIVE_CODES = Object.freeze([
    DRAW_CODE.NINE_TERMINALS, DRAW_CODE.FOUR_RIICHI, DRAW_CODE.TRIPLE_RON, DRAW_CODE.FOUR_KANS, DRAW_CODE.FOUR_WINDS,
]);

/**
 * Each draw's Japanese name, which majiang-core's model reads (its board matches 三家和 on it) and the replay shows
 * beside a translated name; never looked up for display otherwise.
 */
const DRAW_MODEL_NAMES = Object.freeze({
    [DRAW_CODE.EXHAUSTIVE]:     '荒牌平局',
    [DRAW_CODE.NAGASHI]:        '流し満貫',
    [DRAW_CODE.NINE_TERMINALS]: '九種九牌',
    [DRAW_CODE.FOUR_RIICHI]:    '四家立直',
    [DRAW_CODE.TRIPLE_RON]:     '三家和了',
    [DRAW_CODE.FOUR_KANS]:      '四開槓',
    [DRAW_CODE.FOUR_WINDS]:     '四風連打',
    [DRAW_CODE.ABORTIVE]:       '途中流局',
});

/** The draws that void a riichi discarded into them, so its stick is never deposited: a triple ron and four winds. */
function voidsRiichiStick(code) {
    return code == DRAW_CODE.TRIPLE_RON || code == DRAW_CODE.FOUR_WINDS;
}

export { ABORTIVE_CODES, DRAW_CODE, DRAW_MODEL_NAMES, voidsRiichiStick };
