"use strict";

import wire  from './wire.js';
import * as tiles from './tiles.js';
import * as immef from './immef.js';
import * as mianzi from './mianzi.js';
import * as Offer from './offer.js';
import Shadow from './shadow.js';
import rules from './rules.js';
import * as yaku  from './yaku.js';

function fullHandStr(closedIds, meldStrs, winTileId) {
    let s = tiles.handStr((closedIds || []).filter(id => id != winTileId));
    if (winTileId != null) s += tiles.tileToStr(winTileId);
    if (meldStrs && meldStrs.length) s += ',' + meldStrs.join(',');
    return s;
}

/** The seat of the first East dealer, by the server's two-roll rule (nidofuri) over the dealer dice. */
function firstDealerFromDice(dealerDice) {
    const [first, second] = dealerDice;
    const provisional = (first[0] + first[1] - 1) % 4;
    return (provisional + second[0] + second[1] - 1) % 4;
}

const ABORTIVE_NAMES = {
    nine_terminals: '九種九牌',
    four_riichi:    '四家立直',
    triple_ron:     '三家和了',
    four_kans:      '四開槓',
    four_winds:     '四風連打',
};

const KIND_OF_MELD = {
    [wire.MELD.CHI]:        'fulou',
    [wire.MELD.PON]:        'fulou',
    [wire.MELD.OPEN_KAN]:   'fulou',
    [wire.MELD.CLOSED_KAN]: 'gang',
    [wire.MELD.ADDED_KAN]:  'gang',
};

const SAY_OF_MELD = {
    [wire.MELD.CHI]: 'chi',
    [wire.MELD.PON]: 'peng',
};

/** How long a win's ロン or ツモ shows before its result, which fades every call out: upstream Game.delay's minimum. */
const WIN_CALL_MS = 500;

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

class Translate {

    constructor(player, shadow) {
        this.player = player;
        this.shadow = shadow;
        this.onDecision  = () => {};
        this.onGameError = () => {};
        this.retry = null;
        this.roundDialogOpen = false;
        this.pendingJieju = null;
        this.kaijuFed = false;
        this.winCallTimer = null;
    }

    syncWall() {
        this.player._model.shan.paishu = this.shadow.wallLeft();
    }

    static scoreMap(map) {
        const out = {};
        for (const k of Object.keys(map || {})) out[+k] = map[k];
        return out;
    }

    handle(msg) {
        if (msg.t == null) return;
        if (msg[wire.WAIT_ID] != null) this.shadow.waitId = msg[wire.WAIT_ID];
        try {
            switch (msg.t) {
            case wire.E.GAME_STARTED:  return this.gameStarted(msg);
            case wire.E.ROUND_STARTED: return this.roundStarted(msg);
            case wire.E.DRAW:          return this.draw(msg);
            case wire.E.DISCARD:       return this.discard(msg);
            case wire.E.MELD:          return this.meld(msg);
            case wire.E.CALL_PROMPT:   return this.callPrompt(msg);
            case wire.E.DORA_REVEALED: return this.dora(msg);
            case wire.E.ROUND_END:     return this.roundEnd(msg);
            case wire.E.GAME_END:      return this.gameEnd(msg);
            case wire.E.RIICHI_DECL:   return;   /* riichi arrives as the discard's '*' */
            case wire.E.FURITEN:       return;   /* the model tracks furiten itself */
            case wire.E.ERROR:         return this.gameError(msg);
            }
            console.warn('[ronin] unknown event t =', msg.t, msg);
        }
        catch (e) {
            console.error('[ronin] translate error:', e, 'event:', msg);
        }
    }

    gameError(msg) {
        this.onGameError(msg.cd, msg.msg);
        if (msg.cd != wire.GAME_ERROR.STALE_ACTION && this.retry) this.retry();
    }

    gameStarted(msg) {
        const s = this.shadow;
        s.gameId = msg.gid;
        s.qijia = msg.dl;
        s.title = 'Ronin: ' + msg.gid;
        this.readPlayers(msg.p);
        s.playersConnected = [true, true, true, true];
    }

    readPlayers(players) {
        const s = this.shadow;
        s.names = [];
        s.ai = [];
        for (const p of players || []) {
            s.names[p.s] = p.nm;
            s.ai[p.s] = !! p.ai;
        }
    }

    kaiju() {
        const s = this.shadow;
        return { id: s.mySeat, title: s.title, rule: rules, player: s.names.slice(), qijia: s.qijia };
    }

    roundStarted(msg) {
        const s = this.shadow;

        s.mySeat = msg.s;
        s.dealer = msg.dl;
        s.round  = { w: msg.w, n: msg.n };
        s.roundInWind = (msg.dl - s.qijia + 4) % 4;
        s.honba  = msg.h;
        s.riichiSticks = msg.r;
        s.hand   = (msg.mt || []).slice().sort((a, b) => a - b);
        s.scores = [0, 0, 0, 0];
        for (const p of msg.p || []) s.scores[p.s] = p.sc * wire.SCORE_DIV;
        s.dora   = (msg.di || []).map(tiles.tileToStr);
        s.startRound();
        this.retry = null;
        this.roundDialogOpen = false;
        clearTimeout(this.winCallTimer);

        const defen = [];
        const shoupai = [];
        for (let l = 0; l < 4; l++) {
            const seat = (msg.dl + l) % 4;
            defen[l] = s.scores[seat];
            shoupai[l] = seat == s.mySeat ? tiles.handStr(s.hand) : '_'.repeat(13);
        }

        const qipai = {
            zhuangfeng: msg.w,
            jushu:      s.roundInWind,
            changbang:  msg.h,
            lizhibang:  msg.r,
            defen,
            shoupai,
            baopai:     s.dora[0],
        };

        if (! this.kaijuFed) this.feedKaiju();
        this.feed({ qipai }, 'qipai');

        s.startRoundLog({ qipai });
        this.syncWall();
    }

    /**
     * The game start sets the model's players and the board's viewpoint. Its screen is not shown: the server sends
     * the first deal and the dealer's draw with it, on the dealer's turn timer, so the deal fed next hides it at once.
     */
    feedKaiju() {
        this.feed({ kaiju: this.kaiju() }, 'kaiju');
        this.kaijuFed = true;
    }

    draw(msg) {
        const s = this.shadow;
        const { seat, tileId } = immef.decodeDraw(msg.d);
        if (seat != s.mySeat) return;

        const zimo = { p: tiles.tileToStr(tileId), l: s.l(seat) };
        s.drawnTileId = tileId;

        if (s.hand.indexOf(tileId) >= 0) {
            this.present('zimo', Offer.forTurn(msg.aa, s), P => P.action_zimo(zimo, false));
            return;
        }

        s.hand.push(tileId);
        s.hand.sort((a, b) => a - b);
        const offer = Offer.forTurn(msg.aa, s);
        const rinshan = s.noteDraw(seat);
        const m = rinshan ? { gangzimo: zimo } : { zimo };
        this.feedDraw(m, 'zimo', offer);
        s.logMessage(m);
        this.retry = () => this.present('zimo', offer, P => P.action_zimo(zimo, rinshan));
    }

    /** Feed another seat's draw, which the server never sends, before the model sees that seat act. */
    feedHiddenDraw(seat) {
        const s = this.shadow;
        const l = s.l(seat);
        if (this.player._model.shoupai[l]._zimo != null) return;
        const zimo = { p: '_', l };
        const m = s.noteDraw(seat) ? { gangzimo: zimo } : { zimo };
        this.feedDraw(m, 'zimo');
        s.logMessage(m);
    }

    feedDraw(m, kind, offer) {
        this.player._model.shan.paishu = this.shadow.wallLeft() + 1;
        this.feed(m, kind, offer);
    }

    discard(msg) {
        const s = this.shadow;
        const P = this.player;
        const { seat, tileId, isRiichi } = immef.decodeDiscard(msg.d);
        const l = s.l(seat);
        const p = tiles.tileToStr(tileId) + (isRiichi ? '*' : '');

        P.clear_handler();
        s.prompt = null;
        this.retry = null;

        if (seat == s.mySeat) {
            const idx = s.hand.indexOf(tileId);
            if (idx >= 0) s.hand.splice(idx, 1);
            s.drawnTileId = null;
        }
        else {
            this.feedHiddenDraw(seat);
        }
        if (isRiichi) s.riichi[seat] = true;

        const m = { dapai: { p, l } };
        s.lastDapai = m.dapai;
        this.feed(m, 'dapai');
        s.logMessage(m);
        this.syncWall();
        if (isRiichi && P._view) P._view.say('lizhi', l);
    }

    meld(msg) {
        const s = this.shadow;
        const P = this.player;
        const meld = immef.decodeMeldCompact(msg.m);
        const mine = meld.callerSeat == s.mySeat;

        P.clear_handler();
        s.prompt = null;
        this.retry = null;

        const ponMeld = meld.meldType == wire.MELD.ADDED_KAN
            ? s.findPon(meld.callerSeat, Math.floor(meld.tileIds[0] / 4))
            : null;
        const str = mianzi.mianziStr(meld, ponMeld);
        meld.str = str;

        const kind = KIND_OF_MELD[meld.meldType];
        if (kind == 'gang' && ! mine) this.feedHiddenDraw(meld.callerSeat);

        if (mine) {
            const fromHand = meld.meldType == wire.MELD.CLOSED_KAN
                ? meld.tileIds
                : meld.tileIds.filter(id => id != meld.calledTileId);
            for (const id of fromHand) {
                const idx = s.hand.indexOf(id);
                if (idx >= 0) s.hand.splice(idx, 1);
            }
            s.drawnTileId = null;
        }
        if (ponMeld) s.melds[meld.callerSeat].splice(s.melds[meld.callerSeat].indexOf(ponMeld), 1);
        s.noteMeld(meld.callerSeat, meld);

        const l = s.l(meld.callerSeat);
        const m = { [kind]: { m: str, l } };
        this.feed(m, kind);
        s.logMessage(m);
        this.syncWall();
        if (mine && kind == 'fulou') this.retry = () => this.present('fulou', Offer.NO_OFFER, P => P.action_fulou(m.fulou));

        if (P._view) P._view.say(SAY_OF_MELD[meld.meldType] || 'gang', l);
    }

    callPrompt(msg) {
        const s = this.shadow;
        s.prompt = msg;
        const offer = Offer.forPrompt(msg, s);
        const chankan = msg.clt == wire.CLT.CHANKAN;
        const dapai = s.lastDapai;
        this.retry = () => {
            s.prompt = msg;
            this.present(chankan ? 'chankan' : 'dapai', offer,
                         P => chankan ? P.action_chankan() : P.action_dapai(dapai));
        };
        this.retry();
    }

    /** Open a decision on the model's current state, with the server's offer as its buttons. */
    present(kind, offer, show) {
        const P = this.player;
        P.clear_handler();
        P.offer = offer;
        this.shadow.offerActions = offer.actions;
        P._callback = reply => this.onDecision(kind, reply || {});
        show(P);
    }

    dora(msg) {
        const s = this.shadow;
        const str = tiles.tileToStr(msg.ti);
        s.dora.push(str);
        const m = { kaigang: { baopai: str } };
        this.feed(m, 'kaigang');
        s.logMessage(m);
        this.syncWall();
    }

    /** Each seat's score once the round's payments are made: the round end's scores are taken before them. */
    settledScoresBySeat(scs, sch) {
        const before = Translate.scoreMap(scs);
        const change = Translate.scoreMap(sch);
        return [0, 1, 2, 3].map(seat => ((before[seat] || 0) + (change[seat] || 0)) * wire.SCORE_DIV);
    }

    fenpei(sch) {
        const s = this.shadow;
        const map = Translate.scoreMap(sch);
        const out = [];
        for (let l = 0; l < 4; l++) {
            out[l] = (map[(s.dealer + l) % 4] || 0) * wire.SCORE_DIV;
        }
        return out;
    }

    /** The hule message of one winner: a tsumo or ron round end itself, or one entry of a double ron's winners. */
    buildHule(winner, winTile, loserSeat, sch) {
        const s = this.shadow;
        let shoupai = fullHandStr(winner.ct, mianzi.meldStrsFrom(winner.ml), winTile);
        if (s.riichi[winner.ws]) shoupai += '*';
        return huleMessage({
            l:        s.l(winner.ws),
            shoupai,
            baojia:   loserSeat == null ? null : s.l(loserSeat),
            hr:       winner.hr,
            fenpei:   this.fenpei(sch),
            fubaopai: winner.ud && winner.ud.map(tiles.tileToStr),
        });
    }

    revealedHands(tenpaiHands) {
        const s = this.shadow;
        const shoupai = [null, null, null, null];
        for (const h of tenpaiHands || []) {
            shoupai[s.l(h.s)] = fullHandStr(h.ct, mianzi.meldStrsFrom(h.ml), null);
        }
        return shoupai;
    }

    tenpaiByL(tenpaiSeats) {
        const seats = tenpaiSeats || [];
        return [0, 1, 2, 3].map(l => seats.includes((this.shadow.dealer + l) % 4));
    }

    roundEnd(msg) {
        const s = this.shadow;
        const P = this.player;
        clearTimeout(this.winCallTimer);
        P.clear_handler();
        s.prompt = null;
        this.retry = null;

        s.settledScores = msg.scs ? this.settledScoresBySeat(msg.scs, msg.sch) : null;

        let m;
        let winners = [];
        switch (msg.rt) {
        case wire.RT.TSUMO:
            m = this.buildHule(msg, msg.wt, null, msg.sch);
            winners = [msg.ws];
            break;
        case wire.RT.RON:
            m = this.buildHule(msg, msg.wt, msg.ls, msg.sch);
            winners = [msg.ws];
            break;
        case wire.RT.DOUBLE_RON: {
            const mine = (msg.wn || []).find(w => w.ws == s.mySeat);
            const w = mine || (msg.wn || [])[0];
            m = this.buildHule(w, msg.wt, msg.ls, msg.sch);
            winners = (msg.wn || []).map(x => x.ws);
            break;
        }
        case wire.RT.EXHAUSTIVE:
            m = pingjuMessage({ name: '荒牌平局', shoupai: this.revealedHands(msg.th),
                                fenpei: this.fenpei(msg.sch), tenpai: this.tenpaiByL(msg.ts) });
            break;
        case wire.RT.ABORTIVE:
            m = pingjuMessage({ name: ABORTIVE_NAMES[msg.rn] || '途中流局', fenpei: this.fenpei(msg.sch),
                                players: msg.s == null ? [] : [s.l(msg.s)] });
            break;
        case wire.RT.NAGASHI:
            m = pingjuMessage({ name: '流し満貫', shoupai: this.revealedHands(msg.th),
                                fenpei: this.fenpei(msg.sch), tenpai: this.tenpaiByL(msg.ts),
                                players: (msg.qs || []).map(seat => s.l(seat)) });
            break;
        default:
            console.warn('[ronin] unknown round result rt =', msg.rt);
            return;
        }
        const kind = m.hule ? 'hule' : 'pingju';
        s.roundAdvance = msg[wire.WAIT_ID] != null;
        this.roundDialogOpen = true;
        const showResult = () => {
            this.feed(m, kind, Offer.NO_OFFER, reply => {
                this.roundDialogOpen = false;
                this.onDecision(kind, reply);
                this.showPendingJieju();
            });
        };
        s.logMessage(m);
        s.closeRound();
        this.syncWall();

        if (! winners.length) return showResult();
        const call = msg.rt == wire.RT.TSUMO ? 'zimo' : 'rong';
        if (P._view) for (const seat of winners) P._view.say(call, s.l(seat));
        this.winCallTimer = setTimeout(showResult, WIN_CALL_MS);
    }

    gameEnd(msg) {
        const s = this.shadow;
        s.closeRound();
        s.gameEnded = true;

        const defen = [0, 0, 0, 0];
        const point = [0, 0, 0, 0];
        const rank  = [0, 0, 0, 0];
        const gongtuo = [0, 0, 0, 0];
        (msg.st || []).forEach((p, i) => {
            defen[p.s] = p.sc * wire.SCORE_DIV;
            point[p.s] = p.fs;
            rank[p.s]  = i + 1;
            if (s.settledScores) gongtuo[p.s] = defen[p.s] - s.settledScores[p.s];
        });

        this.pendingJieju = {
            title:  s.title,
            rule:   rules,
            player: s.names.slice(),
            qijia:  s.qijia,
            defen,
            point,
            rank,
            gongtuo,
            log:    s.rounds.slice(),
        };
        if (! this.roundDialogOpen) this.showPendingJieju();
    }

    showPendingJieju() {
        const paipu = this.pendingJieju;
        if (! paipu) return;
        this.pendingJieju = null;
        this.player.clear_handler();
        this.feed({ jieju: paipu }, 'jieju');
    }

    feed(msg, kind, offer = Offer.NO_OFFER, callback = reply => this.onDecision(kind, reply)) {
        this.player.offer = offer;
        this.shadow.offerActions = offer.actions;
        this.player.action(msg, reply => callback(reply || {}));
    }

    reconnect(msg) {
        const s = this.shadow;
        const P = this.player;

        s.gameId = msg.gid;
        s.mySeat = msg.s;
        s.dealer = msg.dl;
        s.qijia = firstDealerFromDice(msg.dd);
        s.round = { w: msg.w, n: msg.n };
        s.roundInWind = (msg.dl - s.qijia + 4) % 4;
        s.honba = msg.h;
        s.riichiSticks = msg.r;
        s.title = 'Ronin: ' + msg.gid;
        s.waitId = msg[wire.WAIT_ID];
        this.readPlayers(msg.p);
        this.retry = null;
        this.roundDialogOpen = false;
        clearTimeout(this.winCallTimer);

        s.startRound();
        s.scores = [0, 0, 0, 0];
        s.dora = (msg.di || []).map(tiles.tileToStr);
        s.wallOffset = (msg.tr || 0) - 70;
        s.log = null;
        s.rounds = [];

        const pst = {};
        const discards = {};
        for (const st of msg.pst || []) {
            pst[st.s] = st;
            s.scores[st.s] = st.sc * wire.SCORE_DIV;
            s.riichi[st.s] = !!st.ri;
            discards[st.s] = st.dsc || [];
        }
        const meldsBySeat = {};
        for (let seat = 0; seat < 4; seat++) {
            meldsBySeat[seat] = (pst[seat] ? pst[seat].ml || [] : []).map(m => immef.decodeMeldCompact(m));
        }
        for (let seat = 0; seat < 4; seat++) {
            for (const meld of meldsBySeat[seat]) {
                const ponMeld = meld.meldType == wire.MELD.ADDED_KAN
                    ? meldsBySeat[seat].find(x => x.meldType == wire.MELD.PON
                        && Math.floor(x.tileIds[0] / 4) == Math.floor(meld.tileIds[0] / 4))
                    : null;
                meld.str = mianzi.mianziStr(meld, ponMeld);
                s.melds[seat].push(meld);
            }
        }

        const mt = msg.mt || [];
        const myTurn = msg.cp == s.mySeat && mt.length % 3 == 2;
        let myHandStr = myTurn
            ? tiles.handStr(mt.slice(0, -1)) + tiles.tileToStr(mt[mt.length - 1])
            : tiles.handStr(mt);
        if (s.riichi[s.mySeat]) myHandStr += '*';
        const myMeldStrs = s.melds[s.mySeat].map(m => m.str);
        if (myMeldStrs.length)  myHandStr += ',' + myMeldStrs.join(',');
        s.hand = mt.slice().sort((a, b) => a - b);
        s.drawnTileId = myTurn ? mt[mt.length - 1] : null;

        const defen = [];
        const shoupai = [];
        for (let l = 0; l < 4; l++) {
            const seat = (msg.dl + l) % 4;
            defen[l] = s.scores[seat];
            shoupai[l] = seat == s.mySeat ? myHandStr : '_'.repeat(13);
        }
        P.clear_handler();
        this.feedKaiju();
        const qipai = { zhuangfeng: msg.w, jushu: s.roundInWind, changbang: msg.h,
                        lizhibang: msg.r, defen, shoupai, baopai: s.dora[0] };
        this.feed({ qipai }, 'qipai');
        s.startRoundLog({ qipai });

        for (let i = 1; i < s.dora.length; i++) {
            const m = { kaigang: { baopai: s.dora[i] } };
            this.feed(m, 'kaigang');
            s.logMessage(m);
        }

        /* other seats' draws are not replayed: pad their hands by discards, meld tiles from hand, and their turn's draw */
        for (let seat = 0; seat < 4; seat++) {
            if (seat == s.mySeat) continue;
            const contrib = (meld) => meld.meldType == wire.MELD.CHI
                || meld.meldType == wire.MELD.PON ? 2
                : meld.meldType == wire.MELD.OPEN_KAN ? 3
                : meld.meldType == wire.MELD.CLOSED_KAN ? 4 : 1;
            const meldContrib = meldsBySeat[seat].reduce((a, m) => a + contrib(m), 0);
            const pad = (discards[seat] || []).length + meldContrib + (msg.cp == seat ? 1 : 0);
            P._model.shoupai[s.l(seat)]._bingpai._ += pad;
        }
        for (let seat = 0; seat < 4; seat++) {
            const mine = seat == s.mySeat;
            const l = s.l(seat);
            for (const d of discards[seat] || []) {
                const p = tiles.tileToStr(d.ti) + (d.rd ? '*' : '');
                if (mine) {
                    /* mt is already post-discard, so build my river without discarding from the hand model */
                    P._model.he[l].dapai(p);
                    s.logMessage({ dapai: { p, l } });
                }
                else {
                    const m = { dapai: { p, l } };
                    this.feed(m, 'dapai');
                    s.logMessage(m);
                    /* the snapshot scores already hold the riichi deposits */
                    if (d.rd) P._model._lizhi = false;
                }
                for (let c = 0; c < 4; c++) {
                    if (c == seat) continue;
                    for (const meld of meldsBySeat[c]) {
                        if (meld.calledTileId == d.ti && ! meld._claimed) {
                            meld._claimed = true;
                            const cl = s.l(c);
                            const mm = { fulou: { m: meld.str, l: cl } };
                            s.logMessage(mm);
                            if (c == s.mySeat) {
                                P._model.he[l].fulou(meld.str);
                                continue;
                            }
                            if (mine) P._model.lunban = l;   /* so board.fulou marks my river */
                            this.feed(mm, 'fulou');
                        }
                    }
                }
            }
        }

        /* after the discard replay, so an added kan finds its pon */
        for (let seat = 0; seat < 4; seat++) {
            if (seat == s.mySeat) continue;
            for (const meld of meldsBySeat[seat]) {
                if (meld._claimed) continue;
                if (meld.meldType != wire.MELD.CLOSED_KAN
                    && meld.meldType != wire.MELD.ADDED_KAN) continue;
                const l = s.l(seat);
                const m = { gang: { m: meld.str, l } };
                this.feed(m, 'gang');
                s.logMessage(m);
            }
        }

        /* the snapshot scores already hold the riichi deposits */
        P._model._lizhi = false;

        this.syncWall();

        if (P._view && P._view.redraw) P._view.redraw();

        if (myTurn) this.present('fulou', Offer.NO_OFFER, P => P.select_dapai());
    }
}

export { ABORTIVE_NAMES, huleMessage, pingjuMessage };
export default Translate;
