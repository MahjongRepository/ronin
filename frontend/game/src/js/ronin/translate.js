"use strict";

import wire  from './wire.js';
import * as tiles from './tiles.js';
import * as immef from './immef.js';
import * as mianzi from './mianzi.js';
import * as Offer from './offer.js';
import Shadow from './shadow.js';
import TurnClock from './clock.js';
import Autoplay from './autoplay.js';
import rules from './rules.js';
import { GENERIC_ABORTIVE_NAME, UnknownRoundResultError, abortiveResults, fenpeiByL, jiejuStandings, kanMianzi,
         pingjuMessage, roundResults, seatL, tenpaiByL, WIN_CALL_MS } from './results.js';

/** The seat of the first East dealer, by the server's two-roll rule (nidofuri) over the dealer dice. */
function firstDealerFromDice(dealerDice) {
    const [first, second] = dealerDice;
    const provisional = (first[0] + first[1] - 1) % 4;
    return (provisional + second[0] + second[1] - 1) % 4;
}

const GAME_TYPE_NAMES = {
    [wire.GAME_TYPE.HANCHAN]:  '半荘戦',
    [wire.GAME_TYPE.TONPUSEN]: '東風戦',
};

/** The game start screen's title: the game's length, then on a second line the local time it started. */
function gameTitle(gameType, startedAt) {
    const time = startedAt.toLocaleString('ja-JP', { dateStyle: 'medium', timeStyle: 'short' });
    return GAME_TYPE_NAMES[gameType] + '\n' + time;
}

/**
 * The tiles the reconnect replay takes from a face-down hand for each meld: an added kan replays as its pon, then its
 * fourth tile.
 */
const REPLAYED_FROM_HAND = {
    [wire.MELD.CHI]:        2,
    [wire.MELD.PON]:        2,
    [wire.MELD.OPEN_KAN]:   3,
    [wire.MELD.CLOSED_KAN]: 4,
    [wire.MELD.ADDED_KAN]:  3,
};

/** How long 自動和了 holds a ron before it calls it, so the discard shows first. */
const AUTO_RON_MS = 1000;

/**
 * A finished round of the reconnect snapshot's round history (rh) as the round log the final standings read: the deal
 * (wind, round, honba), each riichi that stood as its riichi discard followed by the next draw (the paipu shape the
 * standings take a riichi deposit from), then the result with its score changes. The standings read nothing else of
 * a round, so the rest is left out. A double ron logs a win per winner, as a live round end does; the history holds
 * only the round's total score changes, so the first win carries them all and the others none, which the standings
 * sum to the same row.
 */
function ledgerRound(entry, qijia) {
    const l = seat => seatL(seat, entry.dl);
    const log = [{ qipai: { zhuangfeng: entry.w, jushu: (entry.dl - qijia + 4) % 4, changbang: entry.h } }];
    for (const seat of entry.rs) {
        log.push({ dapai: { l: l(seat), p: '_*' } }, { zimo: { l: (l(seat) + 1) % 4, p: '_' } });
    }
    const fenpei = fenpeiByL(entry.sch, entry.dl);
    if (! entry.ws.length) {
        const tenpai = entry.ts ? tenpaiByL(entry.ts, entry.dl) : null;
        log.push(pingjuMessage({ name: '流局', fenpei, tenpai }));
        return log;
    }
    const baojia = entry.ls == null ? null : l(entry.ls);
    entry.ws.forEach((winner, i) => {
        log.push({ hule: { l: l(winner), baojia, fenpei: i == 0 ? fenpei : [0, 0, 0, 0] } });
    });
    return log;
}

class Translate {

    constructor(player, shadow, autoplay = new Autoplay()) {
        this.player = player;
        this.shadow = shadow;
        this.autoplay = autoplay;
        this.onDecision  = () => {};
        this.onGameError = () => {};
        this.retry = null;
        this.open = null;
        this.roundDialogOpen = false;
        this.pendingJieju = null;
        this.winCallTimer = null;
        this.resultsOpenedAt = null;
        this.clock = new TurnClock();
    }

    syncWall() {
        this.player._model.shan.paishu = this.shadow.wallLeft();
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
            case wire.E.TURN:          return this.turn(msg);
            case wire.E.CALL_PROMPT:   return this.callPrompt(msg);
            case wire.E.DORA_REVEALED: return this.dora(msg);
            case wire.E.ROUND_END:     return this.roundEnd(msg);
            case wire.E.GAME_END:      return this.gameEnd(msg);
            case wire.E.RIICHI_DECL:   return;   /* riichi arrives as the discard's '*' */
            case wire.E.FURITEN:       return this.furiten(msg.f);
            case wire.E.ERROR:         return this.gameError(msg);
            }
            console.warn('[ronin] unknown event t =', msg.t, msg);
        }
        catch (e) {
            console.error('[ronin] translate error:', e, 'event:', msg);
        }
    }

    /** A refused answer leaves the server's wait open, so the decision reopens with what is left of its countdown. */
    gameError(msg) {
        this.onGameError(msg.cd, msg.msg);
        if (msg.cd == wire.GAME_ERROR.STALE_ACTION || ! this.retry) return;
        this.clock.resume();
        const left = this.clock.remaining();
        this.retry();
        if (left) this.countDecision(left);
    }

    /**
     * Count the open decision down. A call prompt closes when its countdown runs out, sending nothing: the server has
     * already passed for the seat, and when another seat's draw follows, no message of its own would ever close it.
     * Counted after the decision is shown, so a prompt that arrives already expired (re-sent late in its window after
     * a reconnect) closes at once.
     */
    countDecision(left) {
        this.player.countdown(left, this.clock.decision.turn ? null : () => this.closeDecision());
    }

    /**
     * Close the open decision when the socket drops: an answer could not be sent, and after the reconnect the server
     * re-sends any wait it still owes the seat. A round result stays up, as its dismissal sends nothing on its own.
     */
    disconnected() {
        if (this.retry) this.closeDecision();
    }

    closeDecision() {
        this.endCountdown();
        this.player.clear_handler();
        this.shadow.prompt = null;
        this.retry = null;
        this.open = null;
    }

    /**
     * Mark a decision open before it is shown, under its wait, until the seat or the server ends it, so the auto
     * switches answer it only while it still is: one majiang-ui answers as it shows it (a drawn tile in riichi) is not
     * answered twice. Only a draw names its drawn tile: the turn after a pon or chi has none, though a reconnect's hand
     * cannot tell the two apart.
     */
    openDecision(turn, offer, drawn = null) {
        this.open = { turn, offer, drawn, waitId: this.shadow.waitId };
    }

    /**
     * Answer the decision just shown from the auto switches, as the player would; a refused answer's retry is not. A
     * ron waits AUTO_RON_MS with the prompt's buttons hidden, unless less of its time is left: dropped if the server
     * ends the prompt first, and shown again if 自動和了 is turned off meanwhile.
     */
    autoAnswer() {
        const open = this.open;
        if (! open) return;
        const reply = open.turn
            ? this.autoplay.turnReply(open.offer, open.drawn)
            : this.autoplay.promptReply(open.offer);
        if (! reply) return;
        const [left] = this.clock.remaining() || [0];
        if (open.turn || ! reply.hule || left * 1000 <= AUTO_RON_MS) return this.player.callback(reply);
        this.player.clear_handler();
        setTimeout(() => {
            if (this.open !== open || this.shadow.waitId != open.waitId) return;
            if (! this.autoplay.win) return this.retry();
            this.player.callback(reply);
        }, AUTO_RON_MS);
    }

    gameStarted(msg) {
        const s = this.shadow;
        s.gameId = msg.gid;
        s.mySeat = msg.s;
        s.qijia = msg.dl;
        s.title = gameTitle(msg.gt, new Date());
        this.clock.configure(msg[wire.TIMER_SETTINGS]);
        this.readPlayers(msg.p);
        s.playersConnected = [true, true, true, true];
        this.feedKaiju();
        if (this.clock.settings.gp) this.player.screenCountdown('kaiju', this.clock.settings.gp);
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
        this.open = null;
        this.roundDialogOpen = false;
        clearTimeout(this.winCallTimer);
        this.player.clearScreenCountdown();
        this.clock.addRoundBonus();

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

        this.feed({ qipai }, 'qipai');

        s.startRoundLog({ qipai });
        this.syncWall();
    }

    /**
     * The game start sets the model's players and the board's viewpoint, and shows the start screen from the seat the
     * game_started message names. The server holds the first deal back for its game start pause, so the screen stays
     * up that long, counting it down, before the deal hides it; a reconnect feeds it right before its own deal.
     */
    feedKaiju() {
        this.feed({ kaiju: this.kaiju() }, 'kaiju');
    }

    /**
     * The seat's draw opens its turn. It also ends any call prompt the seat left unanswered: one that timed out on the
     * server gets no message of its own when this draw comes next.
     */
    draw(msg) {
        const s = this.shadow;
        const { seat, tileId } = immef.decodeDraw(msg.d);
        if (seat != s.mySeat) return;

        this.player.clear_handler();
        s.prompt = null;
        const zimo = { p: tiles.tileToStr(tileId), l: s.l(seat) };
        s.drawnTileId = tileId;
        this.player.countdown(this.clock.startTurn(msg[wire.WAIT_ELAPSED], msg[wire.TURN_BANK]));

        if (s.hand.indexOf(tileId) >= 0) {
            const offer = Offer.forTurn(msg.aa, s);
            this.retry = () => this.present('zimo', offer, P => P.action_zimo(zimo, false));
            this.openDecision(true, offer, zimo.p);
            this.retry();
            this.autoAnswer();
            return;
        }

        s.hand.push(tileId);
        s.hand.sort((a, b) => a - b);
        const offer = Offer.forTurn(msg.aa, s);
        const rinshan = s.noteDraw(seat);
        const m = rinshan ? { gangzimo: zimo } : { zimo };
        this.openDecision(true, offer, zimo.p);
        this.feedDraw(m, 'zimo', offer);
        s.logMessage(m);
        this.retry = () => this.present('zimo', offer, P => P.action_zimo(zimo, rinshan));
        this.autoAnswer();
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

        this.endCountdown();
        P.clear_handler();
        s.prompt = null;
        this.retry = null;
        this.open = null;

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
        this.feed(m, 'dapai');
        s.logMessage(m);
        this.syncWall();
        if (isRiichi && P._view) P._view.say(mianzi.CALLOUT.RIICHI, l);
    }

    meld(msg) {
        const s = this.shadow;
        const P = this.player;
        const meld = immef.decodeMeldCompact(msg.m);
        const mine = meld.callerSeat == s.mySeat;

        this.endCountdown();
        P.clear_handler();
        s.prompt = null;
        this.retry = null;
        this.open = null;

        const ponMeld = meld.meldType == wire.MELD.ADDED_KAN
            ? s.findPon(meld.callerSeat, Math.floor(meld.tileIds[0] / 4))
            : null;
        const str = mianzi.mianziStr(meld, ponMeld);
        meld.str = str;

        const declared = s.declaredKan != null && meld.callerSeat == s.declaredKan.s
            && meld.tileIds.includes(s.declaredKan.ti);
        s.declaredKan = null;

        const kind = mianzi.KIND_OF_MELD[meld.meldType];
        if (kind == 'gang' && ! mine && ! declared) this.feedHiddenDraw(meld.callerSeat);

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
        if (declared) return this.syncWall();

        const l = s.l(meld.callerSeat);
        const m = { [kind]: { m: str, l } };
        this.feedModel(m);
        s.logMessage(m);
        this.syncWall();

        if (P._view) P._view.say(mianzi.SAY_OF_MELD[meld.meldType], l);
    }

    /** The seat's own pon or chi opens its turn without a draw: this event follows it with the types kuikae blocks. */
    turn(msg) {
        const offer = Offer.forCallTurn(msg.kt);
        this.player.countdown(this.clock.startTurn(msg[wire.WAIT_ELAPSED], msg[wire.TURN_BANK]));
        this.retry = () => this.present('fulou', offer, P => P.show_button(() => P.select_dapai()));
        this.openDecision(true, offer);
        this.retry();
        this.autoAnswer();
    }

    /**
     * A chankan prompt first shows the kan it offers to rob as declared, with no prompt open: the declarer's hidden
     * draw would answer an open one with a pass. A discard's prompt names the discard it opens on, so a prompt the
     * server re-sends after a reconnect reopens its decision too.
     */
    callPrompt(msg) {
        const s = this.shadow;
        const chankan = msg.clt == wire.CLT.CHANKAN;
        s.prompt = null;
        if (chankan) this.declareKan(this.chankanKan(msg));
        s.prompt = msg;
        const offer = Offer.forPrompt(msg, s);
        const dapai = { l: s.l(msg.frs), p: tiles.tileToStr(msg.ti) };
        const left = this.clock.startCallDecision(msg[wire.WAIT_ELAPSED]);
        this.retry = () => {
            s.prompt = msg;
            this.present(chankan ? 'chankan' : 'dapai', offer,
                         P => chankan ? P.action_chankan() : P.action_dapai(dapai));
        };
        this.openDecision(false, offer);
        this.retry();
        this.countDecision(left);
        this.autoAnswer();
    }

    /** Open a decision on the model's current state, with the server's offer as its buttons. */
    present(kind, offer, show) {
        const P = this.player;
        P.clear_handler();
        P.offer = offer;
        this.shadow.offerActions = offer.actions;
        P._callback = reply => this.answer(kind, reply || {});
        show(P);
    }

    /**
     * Send the seat's answer. The server ends the turn of an own kan at once, but the kan's meld reaches the seat only
     * after other seats pass on robbing it, so the clock holds at the answer instead of waiting for it.
     */
    answer(kind, reply) {
        this.open = null;
        if (kind == 'zimo' && reply.gang) this.clock.pause();
        this.onDecision(kind, reply);
    }

    /** End the seat's countdown when the server ends its wait: on its answer, a timeout or another seat's call. */
    endCountdown() {
        this.clock.stop();
        this.player.clear_timer();
    }

    /** The server reports the seat's furiten as it changes; the board shows it on the seat's nameplate. */
    furiten(on) {
        if (this.player._view) this.player._view.furiten(on);
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

    fenpei(sch) {
        return fenpeiByL(sch, this.shadow.dealer);
    }

    /**
     * A round end's result messages and callouts. The live game never stops on a round end it cannot read: an
     * abortive draw with no name shows as a generic one, and any other unknown result is skipped with a warning.
     */
    resultsOf(msg) {
        const facts = { dealer: this.shadow.dealer, riichi: this.shadow.riichi };
        try {
            return roundResults(msg, facts);
        }
        catch (e) {
            if (! (e instanceof UnknownRoundResultError)) throw e;
            console.warn('[ronin]', e.message);
            return msg.rt == wire.RT.ABORTIVE ? abortiveResults(msg, facts, GENERIC_ABORTIVE_NAME) : null;
        }
    }

    /**
     * The mianzi of a kan open to chankan: an added kan extends its declarer's pon in the shadow by the kan tile; a
     * closed kan, which only kokushi musou robs, holds every copy of the tile's type.
     */
    kanStr(kan) {
        return kanMianzi(kan, (seat, tile34) => this.shadow.findPon(seat, tile34));
    }

    /** The kan a chankan prompt offers to rob: an added kan when its declarer holds a pon of the tile, else a closed one. */
    chankanKan(prompt) {
        const pon = this.shadow.findPon(prompt.frs, Math.floor(prompt.ti / 4));
        return { s: prompt.frs, ti: prompt.ti, kty: pon ? wire.KAN.ADDED : wire.KAN.CLOSED };
    }

    /**
     * Play a kan open to chankan as declared. A robbed kan never completes, so no meld event shows it: its chankan
     * prompt, its round end or the reconnect snapshot does. It draws no replacement tile, so the shadow counts no kan.
     */
    feedKan(kan) {
        const m = { gang: { m: this.kanStr(kan), l: this.shadow.l(kan.s) } };
        this.feedModel(m);
        this.shadow.logMessage(m);
    }

    /**
     * Show a kan open to chankan as declared, with the declarer's hidden draw and its call, once: at the chankan
     * prompt of a seat offered to rob it, else at the round end that robs it. A declined kan's meld event then plays
     * only into the shadow.
     */
    declareKan(kan) {
        this.feedHiddenDraw(kan.s);
        this.feedKan(kan);
        this.shadow.declaredKan = kan;
        if (this.player._view) this.player._view.say(mianzi.CALLOUT.KAN, this.shadow.l(kan.s));
    }

    roundEnd(msg) {
        const s = this.shadow;
        const P = this.player;
        clearTimeout(this.winCallTimer);
        this.endCountdown();
        P.clear_handler();
        s.prompt = null;
        this.retry = null;
        this.open = null;
        this.autoplay.reset();
        const kanFirst = msg.rk != null && s.declaredKan == null;
        if (kanFirst) this.declareKan(msg.rk);

        const built = this.resultsOf(msg);
        if (! built) return;
        const { results, callouts } = built;
        s.roundAdvance = msg[wire.WAIT_ID] != null;
        this.resultsOpenedAt = this.clock.now() - (msg[wire.WAIT_ELAPSED] || 0) * 1000;
        this.roundDialogOpen = true;
        for (const m of results) s.logMessage(m);
        s.closeRound();
        this.syncWall();

        if (! callouts.length) return this.showResults(results);
        const callOut = () => {
            if (P._view) for (const { name, l } of callouts) P._view.say(name, l);
            this.winCallTimer = setTimeout(() => this.showResults(results), WIN_CALL_MS);
        };
        if (! kanFirst) return callOut();
        this.winCallTimer = setTimeout(callOut, WIN_CALL_MS);
    }

    /**
     * Show a round's results one after another, each dismissed before the next: a double ron's wins in the server's
     * order, counter-clockwise from the discarder, so the first is the one that took the riichi sticks. The round is
     * confirmed, and the final standings shown, only once the last is dismissed.
     */
    showResults([m, ...rest], index = 0) {
        const kind = m.hule ? 'hule' : 'pingju';
        this.feed(m, kind, Offer.NO_OFFER, reply => {
            this.player.clearScreenCountdown();
            if (rest.length) return this.showResults(rest, index + 1);
            this.roundDialogOpen = false;
            this.onDecision(kind, reply);
            this.showPendingJieju();
        });
        this.countResultDown(index, rest.length > 0);
    }

    /**
     * Count a result down to its share of the round end's time, one round advance timeout (ra) per result, as the
     * server waits a round advance: each result but the last dismisses itself at its share. The last of a round
     * advance stops at 0 until the server confirms the seat and deals the next round; the last of the game's last
     * round end, which opens no wait and is followed by no deal, dismisses itself too, so the final standings show.
     */
    countResultDown(index, more) {
        const deadline = this.resultsOpenedAt + (index + 1) * this.clock.settings.ra * 1000;
        const seconds = (deadline - this.clock.now()) / 1000;
        const dismisses = more || ! this.shadow.roundAdvance;
        this.player.screenCountdown('result', seconds, dismisses ? () => this.player.callback() : undefined);
    }

    gameEnd(msg) {
        const s = this.shadow;
        s.closeRound();
        s.gameEnded = true;

        this.pendingJieju = {
            title:  s.title,
            rule:   rules,
            player: s.names.slice(),
            qijia:  s.qijia,
            ...jiejuStandings(msg),
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

    /** Play an event the model and view show but no decision answers: a meld, whose own turn opens with `turn`. */
    feedModel(msg) {
        this.player.offer = Offer.NO_OFFER;
        this.shadow.offerActions = Offer.NO_OFFER.actions;
        this.player.action(msg);
    }

    feed(msg, kind, offer = Offer.NO_OFFER, callback = reply => this.answer(kind, reply)) {
        this.player.offer = offer;
        this.shadow.offerActions = offer.actions;
        this.player.action(msg, reply => callback(reply || {}));
    }

    /** A reconnect within the round keeps the auto switches; one past its end, or into a round result, clears them. */
    reconnect(msg) {
        const s = this.shadow;
        const P = this.player;

        const sameRound = s.round != null && s.round.w == msg.w && s.round.n == msg.n && s.honba == msg.h;
        if (! sameRound || msg[wire.ROUND_RESULT]) this.autoplay.reset();
        s.gameId = msg.gid;
        s.mySeat = msg.s;
        s.dealer = msg.dl;
        s.qijia = firstDealerFromDice(msg.dd);
        s.round = { w: msg.w, n: msg.n };
        s.roundInWind = (msg.dl - s.qijia + 4) % 4;
        s.honba = msg.h;
        s.riichiSticks = msg.r;
        s.waitId = msg[wire.WAIT_ID];
        this.clock.configure(msg[wire.TIMER_SETTINGS]);
        this.readPlayers(msg.p);
        this.retry = null;
        this.open = null;
        this.roundDialogOpen = false;
        clearTimeout(this.winCallTimer);
        this.player.clearScreenCountdown();

        s.startRound();
        s.scores = [0, 0, 0, 0];
        s.dora = (msg.di || []).map(tiles.tileToStr);
        s.wallOffset = (msg.tr || 0) - 70;
        s.log = null;
        s.rounds = msg.rh.map(entry => ledgerRound(entry, s.qijia));

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
                meld.str = mianzi.mianziStr(meld);
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

        const result = msg[wire.ROUND_RESULT];
        const owed = result && msg[wire.CONFIRMATION_OWED];
        /* an owed result plays its score changes over the table again, so the table starts from before them */
        const settled = owed ? this.fenpei(result.sch) : [0, 0, 0, 0];
        const defen = [];
        const shoupai = [];
        for (let l = 0; l < 4; l++) {
            const seat = (msg.dl + l) % 4;
            defen[l] = s.scores[seat] - settled[l];
            shoupai[l] = seat == s.mySeat ? myHandStr : '_'.repeat(13);
        }
        P.clear_handler();
        this.feedKaiju();
        const qipai = { zhuangfeng: msg.w, jushu: s.roundInWind, changbang: msg.h,
                        lizhibang: msg.r, defen, shoupai, baopai: s.dora[0] };
        this.feed({ qipai }, 'qipai');
        /* the round history already holds a round that ended, so its replay is logged nowhere */
        if (! result) s.startRoundLog({ qipai });

        for (let i = 1; i < s.dora.length; i++) {
            const m = { kaigang: { baopai: s.dora[i] } };
            this.feed(m, 'kaigang');
            s.logMessage(m);
        }

        /* other seats' draws are not replayed: pad each hand so the replay leaves it its tile count, a held draw apart */
        const holdsDraw = seat => pst[seat] && pst[seat].tc % 3 == 2;
        for (let seat = 0; seat < 4; seat++) {
            if (seat == s.mySeat || ! pst[seat]) continue;
            const replayed = (discards[seat] || []).length
                + meldsBySeat[seat].reduce((n, meld) => n + REPLAYED_FROM_HAND[meld.meldType], 0);
            const closed = pst[seat].tc - (holdsDraw(seat) ? 1 : 0);
            P._model.shoupai[s.l(seat)]._bingpai._ += closed + replayed - 13;
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
                            const called = meld.meldType == wire.MELD.ADDED_KAN ? meld.str.slice(0, 5) : meld.str;
                            const mm = { fulou: { m: called, l: cl } };
                            s.logMessage(mm);
                            if (c == s.mySeat) {
                                P._model.he[l].fulou(called);
                                continue;
                            }
                            if (mine) P._model.lunban = l;   /* so board.fulou marks my river */
                            this.feed(mm, 'fulou');
                        }
                    }
                }
            }
        }

        /* after the discard replay, so an added kan finds the pon it was replayed as */
        for (let seat = 0; seat < 4; seat++) {
            if (seat == s.mySeat) continue;
            const l = s.l(seat);
            for (const meld of meldsBySeat[seat]) {
                if (meld.meldType != wire.MELD.CLOSED_KAN
                    && meld.meldType != wire.MELD.ADDED_KAN) continue;
                const m = { gang: { m: meld.str, l } };
                this.feed(m, 'gang');
                s.logMessage(m);
            }
            /* the replay is not in play order, so a meld may be left as the hand's last take */
            P._model.shoupai[l]._zimo = null;
            if (holdsDraw(seat)) this.feedModel({ zimo: { l, p: '_' } });
        }
        if (result && result.rk) {
            this.feedKan(result.rk);
            s.declaredKan = result.rk;
        }
        /* the replay ends on the last seat replayed, but a call on the pending discard marks its discarder's river */
        P._model.lunban = s.l(msg.cp);

        /* the snapshot scores already hold the riichi deposits */
        P._model._lizhi = false;

        this.syncWall();

        if (P._view && P._view.redraw) P._view.redraw();
        this.furiten(msg.f);

        P.clear_timer();
        if (owed) this.roundEnd({ ...result, [wire.WAIT_ID]: msg[wire.WAIT_ID], [wire.WAIT_ELAPSED]: msg[wire.WAIT_ELAPSED] });
    }
}

export default Translate;
