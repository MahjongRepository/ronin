/*
 *  summary
 */
"use strict";

import $ from 'jquery';

import Majiang from '../majiang-core/index.js';

const LIZHI_DEPOSIT = 1000;

function score_text(score) {
    return (''+score).replace(/(\d)(\d{3})$/,'$1,$2');
}

function diff_text(diff) {
    return diff > 0 ? '+' + score_text(diff) : score_text(diff);
}

export default function(root, paipu, viewpoint) {

    let player = $('.row-player .player', root);
    for (let i = 0; i < 4; i++) {
        let id = (viewpoint + i) % 4;
        let name = paipu.player[id].replace(/\n.*$/,'');
        player.eq(i).text(name).attr('title', name);
    }

    let rank = $('.row-rank .rank', root);
    for (let i = 0; i < 4; i++) {
        let id = (viewpoint + i) % 4;
        rank.eq(i).text(paipu.rank[id] ? `${paipu.rank[id]}位` : '')
                  .toggleClass('top', paipu.rank[id] == 1);
    }

    let r_diff = $('.row-diff', root).eq(0).clone();
    let body   = $('.body', root).empty();
    let any_lizhi = false;
    for (let log of paipu.log) {

        if (log.length == 0) continue;

        let qipai = log[0].qipai;

        let last = [], lizhi = [0,0,0,0], lunban = null;
        for (let data of log) {
            if (lunban != null) {
                if (data.hule)  lunban = null;
                else if (data.pingju && data.pingju.name.match(/^三家和/))
                                lunban = null;
                else            lizhi[lunban] = 1;
            }
            if (data.dapai && data.dapai.p.slice(-1) == '*')
                                lunban = data.dapai.l;
            if (data.hule || data.pingju) last.push(data);
        }

        r_diff = r_diff.clone();
        $('.jushu', r_diff).text(['東','南','西','北'][qipai.zhuangfeng]
                               + ['一','二','三','四'][qipai.jushu] + '局');
        $('.changbang', r_diff).text(`${qipai.changbang}本場`);
        $('.last', r_diff).text(
              last.length == 0            ? '−'
            : last[0].pingju              ? '流局'
            : last[0].hule.baojia == null ? 'ツモ'
            :                               'ロン'
        );
        $('.back',  r_diff).removeClass('zhuangjia');
        $('.diff',  r_diff).removeClass('baojia hule even').text('');
        $('.lizhi', r_diff).text('');

        let diff = [0,0,0,0];
        for (let data of last) {
            let fenpei = (data.hule || data.pingju).fenpei;
            for (let l = 0; l < 4; l++) diff[l] += fenpei[l];
        }
        for (let l = 0; l < 4; l++) diff[l] -= lizhi[l] * LIZHI_DEPOSIT;
        let even = last.length > 0 && diff.every(d => d == 0);
        let tenpai = even && last[0].pingju && last[0].pingju.tenpai;

        for (let i = 0; i < 4; i++) {

            let l = (viewpoint + 4 - paipu.qijia + 4 - qipai.jushu + i) % 4;

            if (l == 0) $('.back', r_diff).eq(i).addClass('zhuangjia');

            if (last.length == 0) continue;

            if (lizhi[l]) {
                $('.lizhi', r_diff).eq(i).text('リ');
                any_lizhi = true;
            }

            for (let data of last) {
                if (! data.hule) continue;
                if (data.hule.baojia == l)
                        $('.diff', r_diff).eq(i).addClass('baojia');
                if (data.hule.l      == l)
                        $('.diff', r_diff).eq(i).addClass('hule');
            }
            $('.diff', r_diff).eq(i).toggleClass('even', even).text(
                  tenpai      ? (tenpai[l] ? 'テンパイ' : 'ノーテン')
                : even        ? '±0'
                : diff[l]     ? diff_text(diff[l])
                :               '');
        }

        body.append(r_diff);
    }

    let gongtuo = paipu.gongtuo || [0,0,0,0];
    if (gongtuo.some(d => d)) {
        let r_gongtuo = $('<tr class="row-gongtuo">')
                            .append($('<th colspan="3">').text('残り供託'));
        for (let i = 0; i < 4; i++) {
            let id = (viewpoint + i) % 4;
            r_gongtuo.append($('<td>').append($('<span class="diff">')
                    .toggleClass('hule', gongtuo[id] > 0)
                    .text(gongtuo[id] ? diff_text(gongtuo[id]) : '')));
        }
        body.append(r_gongtuo);
    }

    $('.legend-lizhi', root).toggleClass('hide', ! any_lizhi);

    let defen = $('.row-defen .defen', root);
    for (let i = 0; i < 4; i++) {
        defen.eq(i).removeClass('plus minus');
        let id = (viewpoint + i) % 4;
        defen.eq(i).text(score_text(paipu.defen[id] ?? ''));
        if (paipu.rank[id] == 1) defen.eq(i).addClass('plus');
        if (paipu.defen[id] < 0) defen.eq(i).addClass('minus');
    }

    let point = $('.row-point .point', root);
    for (let i = 0; i < 4; i++) {
        point.eq(i).removeClass('plus minus');
        let id = (viewpoint + i) % 4;
        point.eq(i).text((paipu.point[id] > 0 ? '+' : '')
                            + (paipu.point[id] ?? '−'));
        if (paipu.point[id] > 0) point.eq(i).addClass('plus');
        if (paipu.point[id] < 0) point.eq(i).addClass('minus');
    }

    return root;
}
