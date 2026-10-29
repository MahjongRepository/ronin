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

import { applyStaticText, formatNumber, t } from '../../i18n/index.js';
import { yakuName } from '../../js/ronin/yaku.js';
import { drawName } from '../../js/ronin/terms.js';
import { DRAW_CODE } from '../../js/ronin/draws.js';

const feng_hanzi = ['東','南','西','北'];
const YAKUMAN_MULTIPLES = 6;
/* Who a draw names, by its code: the seat that declared nine terminals,
 * the seats that made nagashi mangan. */
const player_role = { [DRAW_CODE.NINE_TERMINALS]: 'game.result.declared',
                      [DRAW_CODE.NAGASHI]:        'game.result.achieved' };

/* A yakuman's name by its multiple: 役満, ダブル役満, … 六倍役満. */
function yakuman(n) {
    return t(`game.score.yakuman_${Math.min(n, YAKUMAN_MULTIPLES)}`);
}

function fanshu_text(fanshu) {
    return (''+fanshu)[0] == '*' ? yakuman(fanshu.length)
                                 : t('game.result.han', { han: fanshu });
}

/* A hand's limit name by its value in mangan (満貫 … 六倍役満), or null. */
function score_name(manguan) {
    return (manguan >= 4) ? yakuman(Math.floor(manguan / 4))
         : (manguan >= 3) ? t('game.score.sanbaiman')
         : (manguan >= 2) ? t('game.score.baiman')
         : (manguan >= 1.5) ? t('game.score.haneman')
         : (manguan >= 1) ? t('game.score.mangan')
         :                  null;
}

function score_text(defen) {
    return formatNumber(defen);
}

function names_text(names) {
    return names.join(t('list.separator'));
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
        this._r_hupai = $('.row-hupai', root).eq(0);
        this._r_defen = $('.row-defen', root).eq(0);
        this.hide();

        this._pai = pai;

        this._model     = model;
        this._viewpoint = viewpoint
    }

    /* The dialog's fixed labels follow the page's locale each time it shows,
     * and it drops the lang a locale switch left on it while it was open. */
    relabel() {
        this._node.root.removeAttr('lang');
        applyStaticText(this._node.root[0]);
    }

    hule(hule) {

        hide(this._node.root);
        this.relabel();
        hide(this._node.pingju);
        show(this._node.hule);

        let page = hule.page ? ` (${hule.page.number}/${hule.page.count})` : '';
        let title = hule.baojia == null
                ? t('game.result.tsumo_title', { winner: this.name(hule.l) })
                : t('game.result.ron_title', { winner: this.name(hule.l),
                                               loser:  this.name(hule.baojia) });
        this._node.title.text(title + page);
        show(this._node.title);

        let notes = [];
        if (hule.pao != null)
            notes.push(t('game.result.pao', { player: this.name(hule.pao) }));
        if (hule.headBumped && hule.headBumped.length)
            notes.push(t('game.result.head_bump', {
                players: names_text(hule.headBumped.map(l => this.name(l))) }));
        $('.note', this._node.hule).empty().append(
                notes.map(note => $('<span class="note-item">').text(note)));

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
                $('.name',   r_hupai).text(yakuName(h.yi, h.variant));
                $('.fanshu', r_hupai).text(fanshu_text(h.fanshu));
                hupai.append(show(r_hupai));
            }
            let manguan = hule.defen / (hule.l == 0 ? 6 : 4) / 2000;
            let text = [
                hule.damanguan ? null : t('game.result.fu_han',
                                        { fu: hule.fu, han: hule.fanshu }),
                score_name(manguan),
                t('game.result.points', { count: hule.defen }),
            ].filter(part => part != null).join(' ');
            let r_defen = this._r_defen.clone();
            $('.defen', r_defen).text(text);
            hupai.append(r_defen);
        }
        else {
            let r_hupai = this._r_hupai.clone();
            hupai.append(hide(r_hupai));
            let r_defen = this._r_defen.clone();
            $('.defen', r_defen).text(t('game.result.no_yaku'));
            hupai.append(r_defen);
        }

        $('.jicun .changbang', this._node.hule).text(this._model.changbang);
        $('.jicun .lizhibang', this._node.hule).text(this._model.lizhibang);

        if (hule.fenpei) this.fenpei(hule.fenpei);

        this._node.root.attr('aria-label', t('game.result.win_label'))
        fadeIn(this._node.root);
        return this;
    }

    pingju(pingju) {

        hide(this._node.root);
        this.relabel();
        hide(this._node.hule);
        hide(this._node.title);
        show(this._node.pingju);

        $('.name', this._node.pingju).text(drawName(pingju.code));
        let players = names_text((pingju.players || []).map(l => this.name(l)));
        let role = player_role[pingju.code];
        $('.players', this._node.pingju)
                .text(players && role ? t(role, { players }) : players);

        if (pingju.fenpei) this.fenpei(pingju.fenpei, pingju.tenpai);

        this._node.root.attr('aria-label', t('game.result.draw_label'))
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
                                .text(t(tenpai[l] ? 'game.state.tenpai'
                                                  : 'game.state.noten')));
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
