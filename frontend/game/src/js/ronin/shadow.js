"use strict";

import wire from './wire.js';

const WALL_START = 70;   /* 136 - 13*4 - 14 */

const KAN_TYPES = new Set([wire.MELD.CLOSED_KAN, wire.MELD.OPEN_KAN, wire.MELD.ADDED_KAN]);

class Shadow {

    constructor() {
        this.reset();
    }

    reset() {
        this.mySeat   = null;
        this.dealer   = null;
        this.names    = [];
        this.ai       = [];
        this.hand     = [];
        this.drawnTileId = null;
        this.scores   = [0, 0, 0, 0];
        this.riichi   = [false, false, false, false];
        this.afterKan = [false, false, false, false];
        this.melds    = [[], [], [], []];
        this.dora     = [];
        this.nDraws   = 0;
        this.nKans    = 0;
        this.wallOffset = 0;
        this.honba    = 0;
        this.riichiSticks = 0;
        this.round    = null;                  /* { w, n } */
        this.roundInWind = 0;
        this.waitId   = null;
        this.roundAdvance = false;
        this.prompt   = null;
        this.declaredKan = null;               /* a kan shown at its chankan prompt, before its meld or round end */
        this.offerActions = {};
        this.log      = null;
        this.rounds   = [];
        this.gameId   = null;
        this.qijia    = null;
        this.title    = '';
        this.playersConnected = [true, true, true, true];
        this.gameEnded = false;
    }

    startRound() {
        this.riichi   = [false, false, false, false];
        this.afterKan = [false, false, false, false];
        this.melds    = [[], [], [], []];
        this.nDraws   = 0;
        this.nKans    = 0;
        this.wallOffset = 0;
        this.drawnTileId = null;
        this.prompt   = null;
        this.declaredKan = null;
        this.lastDapai = null;
        this.offerActions = {};
        this.roundAdvance = false;
    }

    l(seat) {
        return (seat - this.dealer + 4) % 4;
    }

    /* live wall = 70 - non-rinshan draws - kans + reconnect offset */
    wallLeft() {
        return WALL_START - this.nDraws - this.nKans + this.wallOffset;
    }

    /**
     * Count a draw, mine or a hidden one of another seat, and return whether it was a replacement draw after a kan:
     * that one comes from the dead wall, so the live wall keeps its count.
     */
    noteDraw(seat) {
        const rinshan = this.afterKan[seat];
        this.afterKan[seat] = false;
        if (! rinshan) this.nDraws++;
        return rinshan;
    }

    noteMeld(seat, meld) {
        this.melds[seat].push(meld);
        if (KAN_TYPES.has(meld.meldType)) {
            this.nKans++;
            this.afterKan[seat] = true;
        }
    }

    findPon(seat, tile34) {
        return this.melds[seat].find(m =>
            m.meldType == wire.MELD.PON && Math.floor(m.tileIds[0] / 4) == tile34);
    }

    startRoundLog(msg) {
        this.log = [msg];
    }

    logMessage(msg) {
        if (this.log) this.log.push(msg);
    }

    closeRound() {
        if (this.log) {
            this.rounds.push(this.log);
            this.log = null;
        }
    }
}

Shadow.KAN_TYPES = KAN_TYPES;

export default Shadow;
