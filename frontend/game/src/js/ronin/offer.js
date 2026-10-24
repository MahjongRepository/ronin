"use strict";

import wire from './wire.js';
import * as mianzi from './mianzi.js';

/**
 * What the server lets the player do at a decision, in the terms majiang-ui asks about (tsumo, kyuushu, riichi, ron
 * and the mianzi strings of its kan, pon and chi buttons), plus the wire action each mianzi string stands for.
 */
const NO_OFFER = Object.freeze({
    tsumo: false, kyuushu: false, riichi: false, ron: false,
    gang: [], peng: [], chi: [], actions: {},
});

function sameTypeIds(hand, tileId) {
    const t34 = Math.floor(tileId / 4);
    return hand.filter(id => Math.floor(id / 4) == t34);
}

function emptyOffer() {
    return { tsumo: false, kyuushu: false, riichi: false, ron: false,
             gang: [], peng: [], chi: [], actions: {} };
}

function addCall(offer, kind, str, action) {
    offer[kind].push(str);
    offer.actions[str] = action;
}

function forTurn(availableActions, shadow) {
    const offer = emptyOffer();
    const hand = shadow.hand;
    for (const item of availableActions || []) {
        switch (item.a) {
        case wire.PA.TSUMO:   offer.tsumo = true;   break;
        case wire.PA.KYUUSHU: offer.kyuushu = true; break;
        case wire.PA.RIICHI:  offer.riichi = true;  break;
        case wire.PA.KAN:
            for (const t34 of item.tl || []) {
                const ids = hand.filter(id => Math.floor(id / 4) == t34);
                addCall(offer, 'gang',
                        mianzi.mianziStr({ meldType: wire.MELD.CLOSED_KAN, tileIds: ids }),
                        { a: wire.A.CALL_KAN, ti: ids[0], kan_type: wire.KAN.CLOSED });
            }
            break;
        case wire.PA.ADDED_KAN:
            for (const t34 of item.tl || []) {
                const pon = shadow.findPon(shadow.mySeat, t34);
                const addedId = hand.find(id => Math.floor(id / 4) == t34);
                const kan = { ...pon, meldType: wire.MELD.ADDED_KAN, tileIds: pon.tileIds.concat([addedId]) };
                addCall(offer, 'gang', mianzi.mianziStr(kan, pon),
                        { a: wire.A.CALL_KAN, ti: addedId, kan_type: wire.KAN.ADDED });
            }
            break;
        }
    }
    return offer;
}

function forPrompt(prompt, shadow) {
    const offer = emptyOffer();
    if (prompt.clt != wire.CLT.MELD) {
        offer.ron = true;
        return offer;
    }
    const ti = prompt.ti;
    const meld = (meldType, ids) => mianzi.mianziStr({
        meldType, tileIds: ids.concat([ti]), calledTileId: ti,
        fromSeat: prompt.frs, callerSeat: shadow.mySeat,
    });
    for (const call of prompt.ac || []) {
        switch (call.clt) {
        case wire.MELD_CALL.PON:
            addCall(offer, 'peng', meld(wire.MELD.PON, sameTypeIds(shadow.hand, ti).slice(0, 2)),
                    { a: wire.A.CALL_PON, ti });
            break;
        case wire.MELD_CALL.CHI:
            for (const pair of call.opt || []) {
                addCall(offer, 'chi', meld(wire.MELD.CHI, pair),
                        { a: wire.A.CALL_CHI, ti, sequence_tiles: pair });
            }
            break;
        case wire.MELD_CALL.OPEN_KAN:
            addCall(offer, 'gang', meld(wire.MELD.OPEN_KAN, sameTypeIds(shadow.hand, ti).slice(0, 3)),
                    { a: wire.A.CALL_KAN, ti, kan_type: wire.KAN.OPEN });
            break;
        }
    }
    return offer;
}

export { NO_OFFER, forTurn, forPrompt };
