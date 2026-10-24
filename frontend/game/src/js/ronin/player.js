"use strict";

import UI from '../../vendor/majiang-ui/index.js';

import { NO_OFFER } from './offer.js';

/**
 * majiang-ui's player whose buttons offer exactly what the server offers: the server, not the local engine, judges
 * every win, call, kan, riichi and kyuushu, and refuses or disconnects on anything else.
 */
class RoninPlayer extends UI.Player {

    constructor(root, pai, audio) {
        super(root, pai, audio);
        this.offer = NO_OFFER;
    }

    allow_hule(shoupai, p) { return p == null ? this.offer.tsumo : this.offer.ron; }

    allow_pingju() { return this.offer.kyuushu; }

    allow_no_daopai() { return false; }

    allow_lizhi(shoupai, p) { return this.offer.riichi && super.allow_lizhi(shoupai, p); }

    get_gang_mianzi() { return this.offer.gang; }

    get_peng_mianzi() { return this.offer.peng; }

    get_chi_mianzi() { return this.offer.chi; }

    action_chankan() {
        this.set_button('rong', () => this.callback({ hule: '-' }));
        this.show_button(() => this.callback());
    }
}

export default RoninPlayer;
