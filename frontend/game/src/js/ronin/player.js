"use strict";

import $ from 'jquery';

import UI from '../../vendor/majiang-ui/index.js';

import { BEEP_SECONDS } from '../../vendor/majiang-ui/player.js';
import { NO_OFFER } from './offer.js';

/** Where each screen the server moves on from by itself shows its countdown: the game start and a round result. */
const SCREEN_COUNTDOWNS = {
    kaiju:  '.kaiju .countdown',
    result: '.hule-dialog .next .countdown',
};

/**
 * majiang-ui's player whose buttons and selectable tiles offer exactly what the server offers: the server, not the
 * local engine, judges every win, call, kan, riichi, kyuushu and kuikae, and refuses or disconnects on anything else.
 */
class RoninPlayer extends UI.Player {

    constructor(root, pai, audio) {
        super(root, pai, audio);
        this.offer = NO_OFFER;
    }

    allow_hule(shoupai, p) { return p == null ? this.offer.tsumo : this.offer.ron; }

    allow_pingju() { return this.offer.kyuushu; }

    allow_no_daopai() { return false; }

    allow_lizhi() { return this.offer.riichi; }

    /** Any tile in hand, in riichi only the drawn one (majiang-core's own listing), but the types kuikae blocks. */
    get_dapai(shoupai) {
        const kuikae = this.offer.kuikae;
        return shoupai.get_dapai(false).filter(p => kuikae.indexOf(p[0] + p[1].replace('0', '5')) < 0);
    }

    get_gang_mianzi() { return this.offer.gang; }

    get_peng_mianzi() { return this.offer.peng; }

    get_chi_mianzi() { return this.offer.chi; }

    /**
     * Count a decision down; it beeps through its last five seconds only when it ran longer, so a call prompt stays
     * quiet. Running out runs onExpire, unless the decision was answered or cleared first.
     */
    countdown([limit, allowed], onExpire = null) {
        this._on_expire = onExpire;
        this.set_timer(limit, allowed, limit + allowed > BEEP_SECONDS && this._audio.beep);
    }

    /** A countdown that runs out stops at 0 and answers nothing: the server plays its default. */
    timeout() {
        this._timer_id = clearInterval(this._timer_id);
        this._node.timer.text('0');
        const onExpire = this._on_expire;
        this._on_expire = null;
        if (onExpire) onExpire();
    }

    clear_timer() {
        this._on_expire = null;
        super.clear_timer();
    }

    /**
     * The seat's own discard is the server's, which may not be the tile clicked: a click that reached the server after
     * its timeout is refused while it discards for the seat, and a refused click leaves its mark beside the next one.
     * Unless one click matches the server's tile, the hand drops the tile the server names.
     */
    dapai(dapai) {
        const clicked = $('.pai.dapai', this._node.dapai);
        const matches = clicked.length == 1 && clicked.attr('data-pai') == dapai.p.slice(0, 2);
        if (dapai.l == this._menfeng && ! matches) clicked.removeClass('dapai');
        super.dapai(dapai);
    }

    /**
     * Count down the seconds left before the server moves on from a screen; at 0 the countdown stops and runs
     * onExpire, which may open the next screen's countdown.
     */
    screenCountdown(screen, seconds, onExpire = () => {}) {
        this.clearScreenCountdown();
        const node = $(SCREEN_COUNTDOWNS[screen], this._node.root);
        const deadline = Date.now() + seconds * 1000;
        const tick = () => {
            const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
            node.text(String(left));
            if (left > 0) return;
            this._screen_timer_id = clearInterval(this._screen_timer_id);
            onExpire();
        };
        this._screen_countdown = node;
        this._screen_timer_id = setInterval(tick, 200);
        tick();
    }

    clearScreenCountdown() {
        this._screen_timer_id = clearInterval(this._screen_timer_id);
        if (this._screen_countdown) this._screen_countdown.text('');
        this._screen_countdown = null;
    }

    /**
     * Only 次へ dismisses a round result, by click, as the focused button by keyboard, or by Escape or a right-click
     * once the dialog is ready: a click elsewhere on the dialog (a discard click that lands as it opens, a tap to
     * scroll it) would skip a result the round advance timeout already shows only briefly.
     */
    action_hule() {
        const next = $('.hule-dialog .next', this._node.root);
        $('.hule-dialog', this._node.root).off('click')
                                          .on('click.dialog', '.next', () => this.callback());
        this.set_dialog_timeout(() => {
            next.trigger('focus');
            this.set_default(() => next.trigger('click'));
        });
    }

    action_chankan() {
        this.set_button('rong', () => this.callback({ hule: '-' }));
        this.show_button(() => this.callback());
    }
}

export default RoninPlayer;
