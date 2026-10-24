/*!
 *  Copyright(C) 2017 Satoshi Kobayashi
 *  Released under the MIT license
 *  https://github.com/kobalab/Majiang/blob/master/LICENSE
 */
"use strict";
import Core from '../vendor/majiang-core/index.js';
import UI from '../vendor/majiang-ui/index.js';
import jQuery from 'jquery';

globalThis.Majiang = Core;
globalThis.Majiang.UI = UI;
globalThis.jQuery  = jQuery;
globalThis.$ = jQuery;
