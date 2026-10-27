/*
 *  Majiang.UI.HuleDialog
 */
"use strict";

import $ from 'jquery';

import Majiang from '../majiang-core/index.js';

import Shoupai from './shoupai.js';
import Shan    from './shan.js';

import fadein from './fadein.js';
const { hide, show, fadeIn, fadeOut } = fadein;

const feng_hanzi = ['東','南','西','北'];
const yakuman_name = ['役満','ダブル役満','トリプル役満','四倍役満','五倍役満','六倍役満'];
const player_role = { '九種九牌': '宣言', '流し満貫': '達成' };

function yakuman(n) {
    return yakuman_name[Math.min(n, yakuman_name.length) - 1];
}

function fanshu_text(fanshu) {
    return (''+fanshu)[0] == '*' ? yakuman(fanshu.length) : fanshu + '翻';
}

function score_text(defen) {
    return (''+defen).replace(/(\d)(\d{3})$/, '$1,$2');
}

export default class HuleDialog {

    constructor(root, pai, model, viewpoint = 0) {

        this._node = {
            root:   root,
            title:  $('.title',  root),
            hule:   $('.hule',   root),
            pingju: $('.pingju', root),
            fenpei: $('.fenpei', root),
        };
        this._r_hupai = $('.r-hupai', root).eq(0);
        this._r_defen = $('.r-defen', root).eq(0);
        this.hide();

        this._pai = pai;

        this._model     = model;
        this._viewpoint = viewpoint
    }

    hule(hule) {

        hide(this._node.root);
        hide(this._node.pingju);
        show(this._node.hule);

        this._node.title.text(
            hule.baojia == null ? `${this.name(hule.l)} ツモ`
                                : `${this.name(hule.l)} ロン ← ${this.name(hule.baojia)}`);
        show(this._node.title);

        if (hule.fubaopai) show($('.shan.fubaopai', this._node.hule));
        else               hide($('.shan.fubaopai', this._node.hule));

        new Shan($('.shan', this._node.hule), this._pai, this._model.shan)
                                                            .redraw();

        new Shoupai($('.shoupai', this._node.hule), this._pai,
                    Majiang.Shoupai.fromString(hule.shoupai)).redraw(true);

        let hupai = $('.hupai', this._node.hule).empty();
        if (hule.hupai) {
            for (let h of hule.hupai) {
                let r_hupai = this._r_hupai.clone();
                $('.name',   r_hupai).text(h.name);
                $('.fanshu', r_hupai).text(fanshu_text(h.fanshu));
                hupai.append(show(r_hupai));
            }
            let text = hule.damanguan ? ''
                                      : hule.fu + '符 ' + hule.fanshu + '翻 ';
            let manguan = hule.defen / (hule.l == 0 ? 6 : 4) / 2000;
            text += (manguan >= 4 * 6) ? '六倍役満 '
                  : (manguan >= 4 * 5) ? '五倍役満 '
                  : (manguan >= 4 * 4) ? '四倍役満 '
                  : (manguan >= 4 * 3) ? 'トリプル役満 '
                  : (manguan >= 4 * 2) ? 'ダブル役満 '
                  : (manguan >= 4)     ? '役満 '
                  : (manguan >= 3)     ? '三倍満 '
                  : (manguan >= 2)     ? '倍満 '
                  : (manguan >= 1.5)   ? '跳満 '
                  : (manguan >= 1)     ? '満貫 '
                  :                      '';
            text += hule.defen + '点';
            let r_defen = this._r_defen.clone();
            $('.defen', r_defen).text(text);
            hupai.append(r_defen);
        }
        else {
            let r_hupai = this._r_hupai.clone();
            hupai.append(hide(r_hupai));
            let r_defen = this._r_defen.clone();
            $('.defen', r_defen).text('役なし');
            hupai.append(r_defen);
        }

        $('.jicun .changbang', this._node.hule).text(this._model.changbang);
        $('.jicun .lizhibang', this._node.hule).text(this._model.lizhibang);

        if (hule.fenpei) this.fenpei(hule.fenpei);

        this._node.root.attr('aria-label', 'ホーラ情報')
        fadeIn(this._node.root);
        return this;
    }

    pingju(pingju) {

        hide(this._node.root);
        hide(this._node.hule);
        hide(this._node.title);
        show(this._node.pingju);

        $('.name', this._node.pingju).text(pingju.name);
        let players = (pingju.players || []).map(l => this.name(l)).join('・');
        let role = player_role[pingju.name];
        $('.players', this._node.pingju)
                .text(players && role ? `${role}: ${players}` : players);

        if (pingju.fenpei) this.fenpei(pingju.fenpei, pingju.tenpai);

        this._node.root.attr('aria-label', '流局情報')
        fadeIn(this._node.root);
        return this;
    }

    name(l) {
        return this._model.player[this._model.player_id[l]].replace(/\n.*$/,'');
    }

    fenpei(fenpei, tenpai) {

        let rows = [];
        for (let l = 0; l < 4; l++) {

            let id = this._model.player_id[l];
            let diff = fenpei[l];
            let row = $('<tr>').toggleClass('main', id == this._viewpoint);

            row.append($('<td class="feng">').text(feng_hanzi[l]));
            row.append($('<td class="player">').text(this.name(l)));
            if (tenpai) row.append($('<td class="tenpai">')
                                .toggleClass('noten', ! tenpai[l])
                                .text(tenpai[l] ? 'テンパイ' : 'ノーテン'));
            row.append($('<td class="defen">')
                                .text(score_text(this._model.defen[id] + diff)));
            row.append($('<td class="diff">')
                                .addClass(diff > 0 ? 'plus' : diff < 0 ? 'minus' : '')
                                .text(diff > 0 ? '+' + score_text(diff)
                                    : diff < 0 ? score_text(diff)
                                    :            ''));
            rows.push(row);
        }
        this._node.fenpei.empty().append(rows);
    }

    hide() {
        this._node.root.scrollTop(0);
        hide(this._node.root);
        return this;
    }
}
