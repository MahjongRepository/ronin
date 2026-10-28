"use strict";

/* Round results as majiang-ui messages, from wire fields plus the round facts they omit (its dealer, a winner's
   riichi, a robbed kan's pon), which the caller passes in. */
import wire from './wire.js';
import * as tiles from './tiles.js';
import * as mianzi from './mianzi.js';
import * as yaku from './yaku.js';

/** How long a win's ロン or ツモ shows before its result, which fades every call out: the minimum upstream's Game paced it with. */
const WIN_CALL_MS = 500;

/** A seat's place in majiang's seat order, which counts from the round's dealer. */
function seatL(seat, dealer) {
    return (seat - dealer + 4) % 4;
}

/** The seat at majiang's seat order place l, which counts from the round's dealer. */
function seatOfL(l, dealer) {
    return (dealer + l) % 4;
}

/** The round's number within its wind, from 0: how far the dealer sits from the game's first dealer (qijia). */
function roundInWind(dealer, qijia) {
    return seatL(dealer, qijia);
}

/** A hand as majiang's shoupai string: its closed tiles, the drawn or winning tile among them last, then its melds. */
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

/** The name the live client shows for an abortive draw it has no name for. */
const GENERIC_ABORTIVE_NAME = '途中流局';

/** The names of the two draws that end a round with its wall: an exhaustive draw and a nagashi mangan. */
const DRAW_NAMES = {
    EXHAUSTIVE: '荒牌平局',
    NAGASHI:    '流し満貫',
};

/**
 * A win as majiang-ui's hule message. Its defen is the hand's value alone (the server's hr.pt), which the dialog
 * prints and names (満貫, 跳満, …) by; the winner's score change can't stand in for it, since it holds the honba, the
 * riichi sticks and any pao the winner owes another winner. Without ura-dora to show, fubaopai is null: the dialog
 * hides the ura row only for null. pao is the liable seat's l (null without one), headBumped the l of each ron caller
 * a nearer winner head-bumped, and page, for a round with several wins, which of them this is ({ number, count }).
 */
function huleMessage({ l, shoupai, baojia, hr, fenpei, fubaopai, pao = null, headBumped = [], page = null }) {
    return {
        hule: {
            l,
            shoupai,
            baojia,
            ...yaku.buildHupai(hr),
            defen:    hr.pt * wire.SCORE_DIV,
            fenpei,
            fubaopai: fubaopai && fubaopai.length ? fubaopai : null,
            pao,
            headBumped,
            page,
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
        out[l] = ((sch || {})[seatOfL(l, dealer)] || 0) * wire.SCORE_DIV;
    }
    return out;
}

/** The tenpai seats of a draw as majiang's per-seat tenpai flags, in seat order from the round's dealer. */
function tenpaiByL(tenpaiSeats, dealer) {
    return [0, 1, 2, 3].map(l => tenpaiSeats.includes(seatOfL(l, dealer)));
}

/**
 * The hule message of one winner (ws, ct, ml, hr, sch, ud, ps): a tsumo or ron round end itself, or one entry of a
 * double ron's winners, whose own score changes (sch) hold only what that win moved. riichi says the winner stood in
 * riichi, which marks the hand; loserSeat is the ron's discarder, null for a tsumo; headBumpedSeats are the round's
 * head-bumped ron callers, which the round end names once for all its wins (hbs); page is huleMessage's. A liable
 * discarder pays the whole ron as any discarder does, so the win names no pao.
 */
function winHule({ winner, winTile, loserSeat, dealer, riichi, headBumpedSeats, page }) {
    let shoupai = fullHandStr(winner.ct, mianzi.meldStrsFrom(winner.ml), winTile);
    if (riichi) shoupai += '*';
    return huleMessage({
        l:          seatL(winner.ws, dealer),
        shoupai,
        baojia:     loserSeat == null ? null : seatL(loserSeat, dealer),
        hr:         winner.hr,
        fenpei:     fenpeiByL(winner.sch, dealer),
        fubaopai:   winner.ud && winner.ud.map(tiles.tileToStr),
        pao:        winner.ps == null || winner.ps == loserSeat ? null : seatL(winner.ps, dealer),
        headBumped: headBumpedSeats.map(seat => seatL(seat, dealer)),
        page,
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
    if (! pon) throw new Error('robbed added kan without its pon');
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

/** A round end the builders cannot read: an unknown result type, or an abortive draw with no name. */
class UnknownRoundResultError extends Error {
    constructor(message) {
        super(message);
        this.name = 'UnknownRoundResultError';
    }
}

/**
 * A round won by each of winners in recorded order (a double ron's, counter-clockwise from the discarder): one hule
 * message per winner, each called out and numbered among them. riichi says, by seat, who stands in riichi.
 */
function winResults({ roundEnd, winners, loserSeat, dealer, riichi }) {
    const results = winners.map((winner, i) => winHule({
        winner,
        winTile:         roundEnd.wt,
        loserSeat,
        dealer,
        riichi:          !! riichi[winner.ws],
        headBumpedSeats: roundEnd.hbs || [],
        page:            winners.length > 1 ? { number: i + 1, count: winners.length } : null,
    }));
    const name = loserSeat == null ? mianzi.CALLOUT.TSUMO : mianzi.CALLOUT.RON;
    return { results, callouts: results.map(m => ({ name, l: m.hule.l })) };
}

function exhaustiveResults(roundEnd, dealer) {
    return { results: [pingjuMessage({
        name:    DRAW_NAMES.EXHAUSTIVE,
        shoupai: revealedHands(roundEnd.th, dealer),
        fenpei:  fenpeiByL(roundEnd.sch, dealer),
        tenpai:  tenpaiByL(roundEnd.ts || [], dealer),
    })], callouts: [] };
}

function nagashiResults(roundEnd, dealer) {
    return { results: [pingjuMessage({
        name:    DRAW_NAMES.NAGASHI,
        shoupai: revealedHands(roundEnd.th, dealer),
        fenpei:  fenpeiByL(roundEnd.sch, dealer),
        tenpai:  tenpaiByL(roundEnd.ts || [], dealer),
        players: (roundEnd.qs || []).map(seat => seatL(seat, dealer)),
    })], callouts: [] };
}

/**
 * An abortive draw named name. A kyuushu declarer (s) is the draw's player, its hand shown when handOf(seat) gives it
 * as a shoupai string; a triple ron's callers (rcl) call ron, though nobody wins.
 */
function abortiveResults(roundEnd, { dealer, handOf = () => null }, name) {
    const declarers = roundEnd.s == null ? [] : [roundEnd.s];
    const shoupai = [null, null, null, null];
    for (const seat of declarers) shoupai[seatL(seat, dealer)] = handOf(seat);
    return {
        results: [pingjuMessage({
            name,
            shoupai,
            fenpei:  fenpeiByL(roundEnd.sch, dealer),
            players: declarers.map(seat => seatL(seat, dealer)),
        })],
        callouts: (roundEnd.rcl || []).map(seat => ({ name: mianzi.CALLOUT.RON, l: seatL(seat, dealer) })),
    };
}

/**
 * A round end as the result messages that show it (a hule per winner in recorded order, or one pingju) and the
 * callouts that announce them, given the round facts it omits: its dealer, who stands in riichi (by seat) and,
 * optionally, handOf(seat), a kyuushu declarer's hand right after its draw as a shoupai string, which reveals it.
 * Throws an UnknownRoundResultError for a result type or abortive draw it does not know.
 */
function roundResults(roundEnd, facts) {
    const { dealer, riichi } = facts;
    switch (roundEnd.rt) {
    case wire.RT.TSUMO:
        return winResults({ roundEnd, winners: [roundEnd], loserSeat: null, dealer, riichi });
    case wire.RT.RON:
        return winResults({ roundEnd, winners: [roundEnd], loserSeat: roundEnd.ls, dealer, riichi });
    case wire.RT.DOUBLE_RON:
        return winResults({ roundEnd, winners: roundEnd.wn, loserSeat: roundEnd.ls, dealer, riichi });
    case wire.RT.EXHAUSTIVE:
        return exhaustiveResults(roundEnd, dealer);
    case wire.RT.NAGASHI:
        return nagashiResults(roundEnd, dealer);
    case wire.RT.ABORTIVE: {
        const name = ABORTIVE_NAMES[roundEnd.rn];
        if (! name) throw new UnknownRoundResultError('unknown abortive draw ' + roundEnd.rn);
        return abortiveResults(roundEnd, facts, name);
    }
    }
    throw new UnknownRoundResultError('unknown round result type ' + roundEnd.rt);
}

export {
    ABORTIVE_NAMES, DRAW_NAMES, GENERIC_ABORTIVE_NAME, UnknownRoundResultError, abortiveResults, fenpeiByL,
    fullHandStr, huleMessage, jiejuStandings, kanMianzi, pingjuMessage, revealedHands, roundInWind, roundResults, seatL,
    seatOfL, tenpaiByL, WIN_CALL_MS, winHule,
};
