"use strict";

import { t, tCode } from '../../i18n/index.js';

/** Every yaku id the server sends (the game engine's yaku table), each named by catalog key `yaku.<id>`. */
const YAKU_IDS = Object.freeze([
    ...Array.from({ length: 40 }, (_, i) => i),
    ...Array.from({ length: 23 }, (_, i) => 100 + i),
]);

const YAKUMAN_IDS = { min: 100, max: 119 };
const YAKUMAN_HAN = 13;

/**
 * Daisharin's id, which the server also scores its man and sou forms under (the has_daisharin_other_suits rule); those
 * take their own names, told apart by the suit the hand is made of.
 */
const DAISHARIN = 109;
const DAISHARIN_VARIANTS = Object.freeze({ m: 'daisuurin', s: 'daichikurin' });

function isYakuman(yi) { return yi >= YAKUMAN_IDS.min && yi <= YAKUMAN_IDS.max; }

/**
 * A yaku's name in the page's locale, a variant's (a daisharin of another suit) by its own key; an id the client does
 * not know shows as a numbered yaku, and is reported.
 */
function yakuName(yi, variant = null) {
    if (variant) return t(`yaku.${variant}`);
    return tCode('yaku.', yi, 'yaku.unknown', { id: String(yi) });
}

/** The suit a hand's tiles are all of (m, p, s or z), from its shoupai string, or null for a hand of several. */
function handSuit(shoupai) {
    const suits = new Set((shoupai || '').split(',')[0].match(/[mpsz]/g));
    return suits.size == 1 ? [...suits][0] : null;
}

/** The variant a yaku of this hand is named as, or null for the yaku's own name. */
function yakuVariant(yi, shoupai) {
    if (yi != DAISHARIN) return null;
    return DAISHARIN_VARIANTS[handSuit(shoupai)] ?? null;
}

/**
 * A yaku row as majiang-ui's dialog reads it: the yaku's id and variant, which it names at display time, and its han
 * or yakuman.
 */
function yakuEntry(yi, han, variant = null) {
    if (isYakuman(yi)) return { yi, variant, fanshu: '*'.repeat(Math.max(1, Math.round(han / YAKUMAN_HAN))) };
    return { yi, variant, fanshu: han };
}

/**
 * A win's hand result as majiang-ui's dialog reads it: its yaku rows, total han and fu, and the yakuman multiple; the
 * winning hand's shoupai string names a yaku's variant.
 */
function buildHupai(hr, shoupai) {
    const yk = hr ? hr.yk || [] : [];
    const yakumanHan = yk.filter(y => isYakuman(y.yi)).reduce((sum, y) => sum + y.han, 0);
    return {
        hupai:     yk.map(y => yakuEntry(y.yi, y.han, yakuVariant(y.yi, shoupai))),
        fanshu:    hr ? hr.han : 0,
        fu:        hr ? hr.fu : 0,
        damanguan: Math.round(yakumanHan / YAKUMAN_HAN),
    };
}

export { YAKU_IDS, yakuEntry, yakuName, buildHupai };
