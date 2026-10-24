"use strict";

import wire from './wire.js';
import * as tiles from './tiles.js';
import * as immef from './immef.js';

const DIR = ['_', '+', '=', '-'];

function dirMark(fromSeat, callerSeat) {
    return DIR[(fromSeat - callerSeat + 4) % 4];
}

function digitOf(id) { return tiles.tileToStr(id)[1]; }

function isRedFive(id) {
    const t34 = Math.floor(id / 4);
    return id % 4 == 0 && t34 < 27 && t34 % 9 == 4;
}

function plainDigitOf(ids) {
    return digitOf(ids.find(id => ! isRedFive(id)) || ids[0]);
}

function ponDigits(ponIds, calledId) {
    const red = ponIds.find(isRedFive);
    const d = plainDigitOf(ponIds);
    if (red == null) return d + d + d;
    if (red == calledId) return d + d + '0';
    return d + '0' + d;
}

function kanDigits(ids, calledId) {
    const red = ids.find(isRedFive);
    const d = plainDigitOf(ids);
    if (red == null) return d + d + d + d;
    if (red == calledId) return d + d + d + '0';
    return d + d + '0' + d;
}

/**
 * The Majiang mianzi string of a decoded meld; an added kan needs the pon it extends, whose three tiles and called
 * tile keep their places in the string.
 */
function mianziStr(meld, ponMeld) {
    const ids = meld.tileIds.slice().sort((a, b) => a - b);
    const t34 = Math.floor(ids[0] / 4);
    const suit = t34 < 27 ? 'mps'[Math.floor(t34 / 9)] : 'z';
    switch (meld.meldType) {
    case wire.MELD.CHI: {
        let s = '';
        for (const id of ids) {
            s += digitOf(id);
            if (id == meld.calledTileId) s += '-';
        }
        return suit + s;
    }
    case wire.MELD.PON:
        return suit + ponDigits(ids, meld.calledTileId) + dirMark(meld.fromSeat, meld.callerSeat);
    case wire.MELD.OPEN_KAN:
        return suit + kanDigits(ids, meld.calledTileId) + dirMark(meld.fromSeat, meld.callerSeat);
    case wire.MELD.CLOSED_KAN: {
        const d = plainDigitOf(ids);
        return suit + d + d + d + (ids.some(isRedFive) ? '0' : d);
    }
    case wire.MELD.ADDED_KAN: {
        const ponIds = (ponMeld ? ponMeld.tileIds : ids.slice(0, 3)).slice().sort((a, b) => a - b);
        const addedId = ids.find(id => ponIds.indexOf(id) < 0);
        return suit + ponDigits(ponIds, meld.calledTileId)
             + dirMark(meld.fromSeat, meld.callerSeat) + digitOf(addedId);
    }
    }
    throw new Error('unknown meld type: ' + meld.meldType);
}

function meldStrsFrom(ml) {
    return (ml || []).map(m => mianziStr(immef.decodeMeldCompact(m)));
}

export { dirMark, ponDigits, kanDigits, mianziStr, meldStrsFrom };
