"use strict";

import wire  from './wire.js';
import * as tiles from './tiles.js';

const ROUND_END_KINDS = new Set(['hule', 'pingju']);

class Reply {

    constructor(shadow, send, leave) {
        this.shadow = shadow;
        this.send   = send;
        this.leave  = leave;
    }

    decide(kind, reply) {
        if (reply.dapai)                  return this.discard(reply.dapai);
        if (reply.hule)                   return this.act({ a: kind == 'zimo' ? wire.A.DECLARE_TSUMO : wire.A.CALL_RON });
        if (reply.daopai && kind == 'zimo') return this.act({ a: wire.A.CALL_KYUUSHU });
        if (reply.gang || reply.fulou)    return this.call(reply.gang || reply.fulou);
        if (ROUND_END_KINDS.has(kind))    return this.confirmRound();
        if (kind == 'jieju')              return this.leave();
        this.pass();
    }

    discard(p) {
        const s = this.shadow;
        const type = p.slice(0, 2);
        const ids = tiles.idsOf(type, s.hand);
        const tsumogiri = p.indexOf('_') >= 0 && ids.indexOf(s.drawnTileId) >= 0;
        const ti = tsumogiri ? s.drawnTileId : (ids.find(id => id != s.drawnTileId) ?? ids[0]);
        if (ti == null) {
            console.error('[ronin] discard of a tile not in hand:', p, s.hand.map(tiles.tileToStr));
            return;
        }
        this.act({ a: p.slice(-1) == '*' ? wire.A.DECLARE_RIICHI : wire.A.DISCARD, ti });
    }

    call(m) {
        const action = this.shadow.offerActions[m];
        if (! action) {
            console.error('[ronin] call the server did not offer:', m);
            return;
        }
        this.act(action);
    }

    pass() {
        if (this.shadow.prompt) this.act({ a: wire.A.PASS });
    }

    confirmRound() {
        if (! this.shadow.roundAdvance) return;
        this.shadow.roundAdvance = false;
        this.act({ a: wire.A.CONFIRM_ROUND });
    }

    act(data) {
        this.shadow.prompt = null;
        if (! this.send({ t: wire.T.GAME_ACTION, ...data, [wire.WAIT_ID]: this.shadow.waitId })) {
            console.warn('[ronin] answer not sent, the socket is down:', data);
        }
    }
}

export default Reply;
