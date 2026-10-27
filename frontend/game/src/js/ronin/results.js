"use strict";

/* Round results as majiang-ui messages, from wire fields plus the round facts they omit (its dealer, a winner's
   riichi, a robbed kan's pon), which the caller passes in. */
import wire from './wire.js';
import * as tiles from './tiles.js';
import * as mianzi from './mianzi.js';
import * as yaku from './yaku.js';

/** A seat's place in majiang's seat order, which counts from the round's dealer. */
function seatL(seat, dealer) {
    return (seat - dealer + 4) % 4;
}

function fullHandStr(closedIds, meldStrs, winTileId) {
    let s = tiles.handStr((closedIds || []).filter(id => id != winTileId));
    if (winTileId != null) s += tiles.tileToStr(winTileId);
    if (meldStrs && meldStrs.length) s += ',' + meldStrs.join(',');
    return s;
}

const ABORTIVE_NAMES = {
    nine_terminals: '九種九牌',
    four_riichi:    '四家立直',
    triple_ron:     '三家和了',
    four_kans:      '四開槓',
    four_winds:     '四風連打',
};

/**
 * A win as majiang-ui's hule message. Its defen is the hand's value alone (the server's hr.pt), which the dialog
 * prints and names (満貫, 跳満, …) by; the winner's score change can't stand in for it, since it holds the honba, the
 * riichi sticks and any pao the winner owes another winner. Without ura-dora to show, fubaopai is null: the dialog
 * hides the ura row only for null.
 */
function huleMessage({ l, shoupai, baojia, hr, fenpei, fubaopai }) {
    return {
        hule: {
            l,
            shoupai,
            baojia,
            ...yaku.buildHupai(hr),
            defen:    hr.pt * wire.SCORE_DIV,
            fenpei,
            fubaopai: fubaopai && fubaopai.length ? fubaopai : null,
        },
    };
}

/**
 * A draw as majiang-ui's pingju message. tenpai marks each seat's tenpai on a draw that judges it (null otherwise);
 * players names who the draw is about: the seat that declared nine terminals, the seats that made nagashi mangan.
 */
function pingjuMessage({ name, shoupai = [null, null, null, null], fenpei, tenpai = null, players = [] }) {
    return { pingju: { name, shoupai, fenpei, tenpai, players } };
}

/**
 * A wire map of score changes by seat as majiang's fenpei: points in seat order from the round's dealer. A missing
 * map moves nothing.
 */
function fenpeiByL(sch, dealer) {
    const out = [];
    for (let l = 0; l < 4; l++) {
        out[l] = ((sch || {})[(dealer + l) % 4] || 0) * wire.SCORE_DIV;
    }
    return out;
}

/** The tenpai seats of a draw as majiang's per-seat tenpai flags, in seat order from the round's dealer. */
function tenpaiByL(tenpaiSeats, dealer) {
    return [0, 1, 2, 3].map(l => tenpaiSeats.includes((dealer + l) % 4));
}

/**
 * The hule message of one winner (ws, ct, ml, hr, sch, ud): a tsumo or ron round end itself, or one entry of a double
 * ron's winners, whose own score changes (sch) hold only what that win moved. riichi says the winner stood in riichi,
 * which marks the hand; loserSeat is the ron's discarder, null for a tsumo.
 */
function winHule({ winner, winTile, loserSeat, dealer, riichi }) {
    let shoupai = fullHandStr(winner.ct, mianzi.meldStrsFrom(winner.ml), winTile);
    if (riichi) shoupai += '*';
    return huleMessage({
        l:        seatL(winner.ws, dealer),
        shoupai,
        baojia:   loserSeat == null ? null : seatL(loserSeat, dealer),
        hr:       winner.hr,
        fenpei:   fenpeiByL(winner.sch, dealer),
        fubaopai: winner.ud && winner.ud.map(tiles.tileToStr),
    });
}

/** A draw's revealed hands (th: {s, ct, ml}) as majiang's shoupai in seat order from the dealer, null where hidden. */
function revealedHands(tenpaiHands, dealer) {
    const shoupai = [null, null, null, null];
    for (const h of tenpaiHands || []) {
        shoupai[seatL(h.s, dealer)] = fullHandStr(h.ct, mianzi.meldStrsFrom(h.ml), null);
    }
    return shoupai;
}

/**
 * The mianzi of a kan open to chankan, in the shape of a round end's rk ({s, ti, kty}): an added kan extends its
 * declarer's pon, which findPon(seat, tile34) gives, by the kan tile; a closed kan, which only kokushi musou robs,
 * holds every copy of the tile's type.
 */
function kanMianzi(kan, findPon) {
    const t34 = Math.floor(kan.ti / 4);
    if (kan.kty == wire.KAN.CLOSED) {
        return mianzi.mianziStr({ meldType: wire.MELD.CLOSED_KAN, tileIds: [0, 1, 2, 3].map(c => t34 * 4 + c) });
    }
    const pon = findPon(kan.s, t34);
    return mianzi.mianziStr({ ...pon, meldType: wire.MELD.ADDED_KAN, tileIds: pon.tileIds.concat([kan.ti]) }, pon);
}

/**
 * The final standings of a game_end message as majiang-ui's jieju fields, by seat: each seat's score, uma-adjusted
 * points and place, and gongtuo, the points the riichi sticks left on the table at the end gave the winner (lb).
 */
function jiejuStandings({ ws, st, lb }) {
    const defen   = [0, 0, 0, 0];
    const point   = [0, 0, 0, 0];
    const rank    = [0, 0, 0, 0];
    const gongtuo = [0, 0, 0, 0];
    st.forEach((p, i) => {
        defen[p.s] = p.sc * wire.SCORE_DIV;
        point[p.s] = p.fs;
        rank[p.s]  = i + 1;
    });
    gongtuo[ws] = lb * wire.SCORE_DIV;
    return { defen, point, rank, gongtuo };
}

export {
    ABORTIVE_NAMES, fenpeiByL, huleMessage, jiejuStandings, kanMianzi, pingjuMessage, revealedHands, seatL, tenpaiByL,
    winHule,
};
