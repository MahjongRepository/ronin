/*!
 *  @kobalab/majiang-ui v1.6.1
 *
 *  Copyright(C) 2021 Satoshi Kobayashi
 *  Released under the MIT license
 *  https://github.com/kobalab/majiang-ui/blob/master/LICENSE
 */

"use strict";

import pai from './pai.js';
import audio from './audio.js';
import Shoupai from './shoupai.js';
import He from './he.js';
import Shan from './shan.js';
import Board from './board.js';
import HuleDialog from './dialog.js';
import Player from './player.js';
import GameCtl from './gamectl.js';
import fadein from './fadein.js';
import selector from './selector.js';
import scale from './scale.js';

export default {
    pai:         pai,
    audio:       audio,
    Shoupai:     Shoupai,
    He:          He,
    Shan:        Shan,
    Board:       Board,
    HuleDialog:  HuleDialog,
    Player:      Player,
    GameCtl:     GameCtl,
    Util:        Object.assign(fadein,
                               selector,
                               scale)
}
