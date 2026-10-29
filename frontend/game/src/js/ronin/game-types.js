"use strict";

import wire from './wire.js';
import { t } from '../../i18n/index.js';

const GAME_TYPE_KEYS = Object.freeze({
    [wire.GAME_TYPE.HANCHAN]:  'game.type.hanchan',
    [wire.GAME_TYPE.TONPUSEN]: 'game.type.tonpuu',
});

/** The game's length as the start screen titles it, by its wire game type (`gt`). */
export function gameTypeName(gameType) {
    return t(GAME_TYPE_KEYS[gameType]);
}
