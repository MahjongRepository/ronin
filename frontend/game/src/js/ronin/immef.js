/* IMME (backend/shared/lib/melds/README.md): value = meld_index*4 + caller_seat */
"use strict";

const CHI_OFFSET = 0,           CHI_COUNT = 4032;
const PON_OFFSET = 4032,        PON_COUNT = 1224;
const SHOUMINKAN_OFFSET = 5256, SHOUMINKAN_COUNT = 408;
const DAIMINKAN_OFFSET = 5664,  DAIMINKAN_COUNT = 408;
const ANKAN_OFFSET = 6072,      ANKAN_COUNT = 34;
const MAX_VALUE = (ANKAN_OFFSET + ANKAN_COUNT) * 4 - 1;

function allFourCopies(t34) { return [0, 1, 2, 3].map(c => t34 * 4 + c); }
function copiesExcluding(t34, missingCopy) {
    return allFourCopies(t34).filter((_id, idx) => idx != missingCopy);
}

function decodeChi(meldIndex, callerSeat) {
    const calledPos = meldIndex % 3;
    const r1 = Math.trunc(meldIndex / 3);
    const copyIndex = r1 % 64;
    const baseIndex = Math.trunc(r1 / 64);
    const suitIndex = Math.trunc(baseIndex / 7);
    const startInSuit = baseIndex % 7;
    const tLo = suitIndex * 9 + startInSuit;
    const cLo = Math.trunc(copyIndex / 16);
    const cMid = Math.trunc(copyIndex / 4) % 4;
    const cHi = copyIndex % 4;
    const tileIds = [tLo * 4 + cLo, (tLo + 1) * 4 + cMid, (tLo + 2) * 4 + cHi];
    return { meldType: 'chi', callerSeat, fromSeat: (callerSeat + 3) % 4,
             tileIds, calledTileId: tileIds[calledPos] };
}

function decodePon(ponIndex, callerSeat) {
    const fromOffset = ponIndex % 3;
    let r = Math.trunc(ponIndex / 3);
    const calledPos = r % 3;
    r = Math.trunc(r / 3);
    const missingCopy = r % 4;
    const t34 = Math.trunc(r / 4);
    const tileIds = copiesExcluding(t34, missingCopy);
    return { meldType: 'pon', callerSeat,
             fromSeat: (callerSeat + fromOffset + 1) % 4,
             tileIds, calledTileId: tileIds[calledPos] };
}

function decodeOpenKan(localIndex, callerSeat, meldType) {
    const fromOffset = localIndex % 3;
    let r = Math.trunc(localIndex / 3);
    const calledCopy = r % 4;
    const t34 = Math.trunc(r / 4);
    return { meldType, callerSeat,
             fromSeat: (callerSeat + fromOffset + 1) % 4,
             tileIds: allFourCopies(t34), calledTileId: t34 * 4 + calledCopy };
}

function decodeAnkan(localIndex, callerSeat) {
    return { meldType: 'closed_kan', callerSeat, fromSeat: null,
             tileIds: allFourCopies(localIndex), calledTileId: null };
}

const MELD_RANGES = [
    [CHI_OFFSET, CHI_COUNT, decodeChi],
    [PON_OFFSET, PON_COUNT, decodePon],
    [SHOUMINKAN_OFFSET, SHOUMINKAN_COUNT,
        (li, cs) => decodeOpenKan(li, cs, 'added_kan')],
    [DAIMINKAN_OFFSET, DAIMINKAN_COUNT,
        (li, cs) => decodeOpenKan(li, cs, 'open_kan')],
    [ANKAN_OFFSET, ANKAN_COUNT, decodeAnkan],
];

function decodeMeldCompact(value) {
    if (! Number.isInteger(value) || value < 0 || value > MAX_VALUE) {
        throw new RangeError('IMME value must be 0-' + MAX_VALUE + ', got ' + value);
    }
    const callerSeat = value % 4;
    const meldIndex = Math.trunc(value / 4);
    for (const [offset, count, decoder] of MELD_RANGES) {
        if (meldIndex < offset + count) return decoder(meldIndex - offset, callerSeat);
    }
    throw new RangeError('IMME value ' + value + ' (meld_index=' + meldIndex + ') out of range');
}

/* draw/discard packed int → (seat, tile_id[, is_tsumogiri, is_riichi]) */
function decodeDraw(d) {
    if (! Number.isInteger(d) || d < 0 || d >= 544) {
        throw new RangeError('Draw packed value must be 0-543, got ' + d);
    }
    const seat = Math.trunc(d / 136);
    return { seat, tileId: d % 136 };
}

function decodeDiscard(d) {
    if (! Number.isInteger(d) || d < 0 || d > 2175) {
        throw new RangeError('Discard packed value must be 0-2175, got ' + d);
    }
    const flag = Math.trunc(d / 544);
    const r = d % 544;
    const seat = Math.trunc(r / 136);
    return { seat, tileId: r % 136,
             isTsumogiri: (flag & 0b01) != 0,
             isRiichi:   (flag & 0b10) != 0 };
}

export { decodeMeldCompact, decodeDraw, decodeDiscard };
