"use strict";

import $ from 'jquery';

const SWITCH_CLASS = {
    win:       'win',
    tsumogiri: 'tsumogiri',
    noCall:    'no-call',
};

/**
 * The seat's auto switches, kept on the client alone and only until the round ends: 自動和了 declares every win the
 * server offers, ツモ切り discards a drawn tile whose turn offers nothing else, 鳴きなし passes every call prompt
 * that offers no ron. A switch answers the decisions opened after it is turned on, never one already showing.
 */
class Autoplay {

    constructor(root = $()) {
        this.root = root;
        for (const name of Object.keys(SWITCH_CLASS)) {
            this.button(name).on('click.autoplay', () => this.set(name, ! this[name]));
        }
        this.reset();
    }

    button(name) {
        return $(`.${SWITCH_CLASS[name]}`, this.root);
    }

    set(name, on) {
        this[name] = on;
        this.button(name).attr('aria-checked', String(on));
    }

    reset() {
        for (const name of Object.keys(SWITCH_CLASS)) this.set(name, false);
    }

    /** The switches' answer to the seat's turn, or null to leave it to the player. */
    turnReply(offer, drawn) {
        if (this.win && offer.tsumo) return { hule: '-' };
        const choice = offer.tsumo || offer.kyuushu || offer.riichi.length || offer.gang.length;
        if (this.tsumogiri && drawn != null && ! choice) return { dapai: drawn + '_' };
        return null;
    }

    /** The switches' answer to a call prompt, a pass as the empty reply, or null to leave it to the player. */
    promptReply(offer) {
        if (this.win && offer.ron) return { hule: '-' };
        if (this.noCall && ! offer.ron) return {};
        return null;
    }
}

export default Autoplay;
