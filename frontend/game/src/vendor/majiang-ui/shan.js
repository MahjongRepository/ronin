/*
 *  Majiang.UI.Shan
 */
"use strict";

import { setAttributeText } from '../../i18n/index.js';

export default class Shan {

    constructor(root, pai, shan) {

        this._node = {
            baopai:   $('.baopai',   root),
            fubaopai: $('.fubaopai', root),
            paishu:   $('.paishu',   root)
        };
        this._pai  = pai;
        this._shan = shan;
    }

    redraw() {

        let baopai = this._shan.baopai;
        this._node.baopai.each((i, node)=>
                setAttributeText(node, 'aria-label', 'yaku.120'));
        this._node.baopai.empty();
        for (let i = 0; i < 5; i++) {
            this._node.baopai.append(this._pai(baopai[i] || '_'));
        }

        let fubaopai = this._shan.fubaopai || [];
        this._node.fubaopai.each((i, node)=>
                setAttributeText(node, 'aria-label', 'yaku.122'));
        this._node.fubaopai.empty();
        for (let i = 0; i < 5; i++) {
            this._node.fubaopai.append(this._pai(fubaopai[i] || '_'));
        }

        this._node.paishu.text(this._shan.paishu);

        return this;
    }

    update() {
        this._node.paishu.text(this._shan.paishu);
        return this;
    }
}
