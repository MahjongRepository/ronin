/*!
 *  @kobalab/majiang-core v1.4.1
 *
 *  Copyright(C) 2021 Satoshi Kobayashi
 *  Released under the MIT license
 *  https://github.com/kobalab/majiang-core/blob/master/LICENSE
 */

"use strict";

import rule from './rule.js';
import Shoupai from './shoupai.js';
import Shan from './shan.js';
import He from './he.js';
import Board from './board.js';
import Game from './game.js';
import Player from './player.js';
import xiangting from './xiangting.js';
import hule from './hule.js';

export default {
    rule:    rule,
    Shoupai: Shoupai,
    Shan:    Shan,
    He:      He,
    Board:   Board,
    Game:    Game,
    Player:  Player,
    Util:    Object.assign(xiangting,
                           hule)
}
