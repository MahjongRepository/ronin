"use strict";

import $ from 'jquery';

import UI from '../../vendor/majiang-ui/index.js';

import { BEEP_SECONDS } from '../../vendor/majiang-ui/player.js';
import { NO_OFFER } from './offer.js';

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

    /** Count a decision down; it beeps through its last five seconds only when it ran longer, so a call prompt stays quiet. */
    countdown([limit, allowed]) {
        this.set_timer(limit, allowed, limit + allowed > BEEP_SECONDS && this._audio.beep);
    }

    /** A countdown that runs out stops at 0 and leaves the decision open: the server plays its default. */
    timeout() {
        this._timer_id = clearInterval(this._timer_id);
        this._node.timer.text('0');
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

    action_chankan() {
        this.set_button('rong', () => this.callback({ hule: '-' }));
        this.show_button(() => this.callback());
    }
}

export default RoninPlayer;
