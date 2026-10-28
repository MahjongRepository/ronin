/*
 *  Majiang.UI.He
 */
"use strict";

import $ from 'jquery';

import { setAttributeText } from '../../i18n/index.js';

export default class He {

    constructor(root, pai, he) {

        this._node = {
            root:   root,
            chouma: $('.chouma', root),
            dapai:  $('.dapai',  root)
        };
        this._pai  = pai;
        this._he   = he;
        this._node.chouma.addClass('hide');
    }

    /* deposited: whether the riichi stick is down. The riichi discard lies
     * sideways regardless; a riichi voided before its deposit gets no stick. */
    redraw(deposited = true) {

        this._node.root.each((i, root)=>
                setAttributeText(root, 'aria-label', 'game.aria.river'));
        this._node.chouma.each((i, chouma)=>
                setAttributeText(chouma, 'aria-label', 'game.call.riichi'));
        this._node.dapai.empty();
        let lizhi = false;
        let declared = false;
        let i = 0;
        for (let p of this._he._pai) {
            if (p.match(/\*/)) {
                lizhi = true;
                declared = true;
            }
            if (p.match(/[\+\=\-]/)) continue;

            let pai = this._pai(p);
            if (p[2] == '_') {
                pai.addClass('mopai');
            }
            if (lizhi) {
                pai = $('<span class="lizhi">').append(pai);
                setAttributeText(pai[0], 'aria-label', 'game.call.riichi');
                lizhi = false;
            }
            this._node.dapai.append(pai);

            i++;
            if (i < 6 * 3 && i % 6 == 0) {
                this._node.dapai.append($('<span class="break">'));
            }
        }
        this._node.chouma.toggleClass('hide', ! (declared && deposited));
        return this;
    }

    dapai(p) {

        let pai = this._pai(p).addClass('dapai').attr('aria-live','assertive');
        if (p[2] == '_') pai.addClass('mopai');
        if (p.match(/\*/)) pai = $('<span class="lizhi">').append(pai);
        this._node.dapai.append(pai);
        return this;
    }
}
