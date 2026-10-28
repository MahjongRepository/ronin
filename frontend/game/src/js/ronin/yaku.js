"use strict";

import { tCode } from '../../i18n/index.js';

/** Every yaku id the server sends (the game engine's yaku table), each named by catalog key `yaku.<id>`. */
const YAKU_IDS = Object.freeze([
    ...Array.from({ length: 40 }, (_, i) => i),
    ...Array.from({ length: 23 }, (_, i) => 100 + i),
]);

const YAKUMAN_IDS = { min: 100, max: 119 };
const YAKUMAN_HAN = 13;

function isYakuman(yi) { return yi >= YAKUMAN_IDS.min && yi <= YAKUMAN_IDS.max; }

/** A yaku's name in the page's locale; an id the client does not know shows as a numbered yaku, and is reported. */
function yakuName(yi) {
    return tCode('yaku.', yi, 'yaku.unknown', { id: String(yi) });
}

/** A yaku row as majiang-ui's dialog reads it: the yaku's id, which it names at display time, and its han or yakuman. */
function yakuEntry(yi, han) {
    if (isYakuman(yi)) return { yi, fanshu: '*'.repeat(Math.max(1, Math.round(han / YAKUMAN_HAN))) };
    return { yi, fanshu: han };
}

/** A win's hand result as majiang-ui's dialog reads it: its yaku rows, total han and fu, and the yakuman multiple. */
function buildHupai(hr) {
    const yk = hr ? hr.yk || [] : [];
    const yakumanHan = yk.filter(y => isYakuman(y.yi)).reduce((sum, y) => sum + y.han, 0);
    return {
        hupai:     yk.map(y => yakuEntry(y.yi, y.han)),
        fanshu:    hr ? hr.han : 0,
        fu:        hr ? hr.fu : 0,
        damanguan: Math.round(yakumanHan / YAKUMAN_HAN),
    };
}

export { YAKU_IDS, yakuEntry, yakuName, buildHupai };
