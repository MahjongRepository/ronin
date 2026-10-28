"use strict";

import { t, tCode } from '../../i18n/index.js';

/** The winds in seat and round order, as their catalog keys name them (`wind.<code>`, `round.<code>_<n>`). */
const WIND_CODES = Object.freeze(['east', 'south', 'west', 'north']);

/** The rounds of each wind: 東一局 to 東四局. */
const ROUNDS_PER_WIND = 4;

/** A round's catalog key: its wind (zhuangfeng, from 0) and its number within it (jushu, from 0). */
function roundKey(zhuangfeng, jushu) {
    return `round.${WIND_CODES[zhuangfeng]}_${jushu + 1}`;
}

/** A round's name in the page's locale: 東一局, East 1, Восток 1. */
function roundName(zhuangfeng, jushu) {
    return t(roundKey(zhuangfeng, jushu));
}

/** A round's name with its honba: 東一局 1本場, East 1, 1 honba. */
function roundWithHonba(zhuangfeng, jushu, honba) {
    return t('round.with_honba', { round: roundName(zhuangfeng, jushu), honba });
}

/** A wind's name in text (seat or round), never a table glyph: East, Восток, 東. */
function windName(wind) {
    return t(`wind.${WIND_CODES[wind]}`);
}

/** A draw's name by its code (DRAW_CODE); a code the client does not know shows as a draw, and is reported. */
function drawName(code) {
    return tCode('draw.', code, 'draw.generic');
}

export { ROUNDS_PER_WIND, WIND_CODES, drawName, roundKey, roundName, roundWithHonba, windName };
