/*
 *  Majiang.UI.Board
 */
"use strict";

import $ from 'jquery';

import Shoupai    from './shoupai.js';
import Shan       from './shan.js';
import He         from './he.js';
import HuleDialog from './dialog.js';
import summary    from './summary.js';

import fadein from './fadein.js';
const { hide, show, fadeIn, fadeOut } = fadein;

const class_name = ['main','xiajia','duimian','shangjia'];
const feng_hanzi = ['東','南','西','北'];
const shu_hanzi  = ['一','二','三','四'];

/* A round's name as the board shows it (東一局): the replay strip's too. */
export function jushu_name(zhuangfeng, jushu) {
    return feng_hanzi[zhuangfeng] + shu_hanzi[jushu] + '局';
}

const say_text   = { chi:   'チー',
                     peng:  'ポン',
                     gang:  'カン',
                     lizhi: 'リーチ',
                     rong:  'ロン',
                     zimo:  'ツモ'    };

function format_defen(defen) {
    return ('' + defen).replace(/(\d)(\d{3})$/,'$1,$2');
}

/* A seat's nameplate: its wind, name and score, the dealer's 親, and 切断中
 * while a disconnected player's seat is played for them. */
function nameplate(plate, l, name, defen, connected) {
    plate.toggleClass('zhuangjia', l == 0)
         .empty()
         .append($('<span class="feng">').text(feng_hanzi[l]),
                 $('<span class="name">').text(name).attr('title', name),
                 $('<span class="info">').append(
                    $('<span class="defen">').text(format_defen(defen)),
                    l == 0 ? $('<span class="badge dealer">').text('親')
                           : null));
    return mark_offline(plate, ! connected);
}

function mark_offline(plate, offline) {
    $('.badge.offline', plate).remove();
    if (offline) $('.info', plate).append(
                        $('<span class="badge offline">').text('切断中'));
    return plate.toggleClass('disconnect', offline);
}

/* Whether seat l's riichi stick is down: the model holds the deposit (_lizhi)
 * until the next turn, and for good once a ron or 四風連打 voids the riichi. */
function lizhi_deposited(model, l) {
    return ! (model._lizhi && l == model.lunban);
}

class Score {

    constructor(root, model, board) {
        this._model = model;
        this._board = board;
        this._view = {
            root:      root,
            jushu:     $('.jushu', root),
            changbang: $('.changbang', root),
            lizhibang: $('.lizhibang', root),
            defen:     [],
            player:    [],
        };
        this._viewpoint = 0;
        hide(this._view.root);
    }

    redraw(viewpoint) {

        if (viewpoint != null) this._viewpoint = viewpoint;

        show(this._view.root);

        this._view.jushu.text(jushu_name(this._model.zhuangfeng,
                                         this._model.jushu));
        this._view.changbang.text(this._model.changbang);
        this._view.lizhibang.text(this._model.lizhibang);

        for (let l = 0; l < 4; l++) {
            let id = this._model.player_id[l];
            let defen = format_defen(this._model.defen[id]);
            let c = class_name[(id + 4 - this._viewpoint) % 4];
            this._view.defen[l] = $(`.defen .${c}`, this._view.root);
            this._view.defen[l].removeClass('lunban')
                               .text(`${feng_hanzi[l]}: ${defen}`);
            if (l == this._model.lunban) this._view.defen[l].addClass('lunban');
            this._view.player[l] = $(`> .player.${c}`, this._board);
            $('.defen', this._view.player[l]).text(defen);
        }
        return this;
    }

    update() {
        let lunban = this._model.lunban < 0 ? 0 : this._model.lunban;
        for (let l = 0; l < 4; l++) {
            this._view.defen[l].toggleClass('lunban', l == lunban);
            this._view.player[l].toggleClass('lunban', l == lunban);
        }
        return this;
    }
}

export default class Board {

    constructor(root, pai, audio, model) {
        this._root  = root;
        this._model = model;
        this._pai   = pai;
        this._view  = {
            score:   new Score($('.score', root), model, root),
            shan:    null,
            shoupai: [],
            he:      [],
            say:     [],
            dialog:  null,
            summary: hide($('> .summary', root)),
            kaiju:   hide($('> .kaiju', root)),
            furiten: hide($('> .furiten', root)),
        };
        this._say = [];
        this._lizhi = false;
        this._connected = [true, true, true, true];

        this.viewpoint = 0;
        this.sound_on  = true
        /* Every hand face up, through a draw's reveal too: the replay
         * viewer's; the live game shows only the viewpoint's. */
        this.open_shoupai = false;

        this._timeout_id;
        this._open_hule = null;

        this.set_audio(audio);

        $('> .player', this._root).each((i, plate)=>mark_offline($(plate), false));

        $(window).on('resize', ()=>this._view.shoupai.forEach(s=>s.adjust()));
    }

    set_audio(audio) {
        this._audio = {};
        for (let name of ['dapai','chi','peng','gang','rong','zimo','lizhi']) {
            this._audio[name] = [];
            for (let l = 0; l < 4; l++) {
                this._audio[name][l] = audio(name);
            }
        }
        this._audio.gong = audio('gong');
        return this;
    }

    redraw() {

        this._timeout_id = clearTimeout(this._timeout_id);
        this._open_hule = null;
        hide(this._view.summary);
        hide(this._view.kaiju);
        hide(this._view.furiten);

        this._view.score.redraw(this.viewpoint);

        this._view.shan = new Shan($('.score .shan', this._root), this._pai,
                                    this._model.shan).redraw();

        for (let l = 0; l < 4; l++) {
            let id   = this._model.player_id[l];
            let c    = class_name[(id + 4 - this.viewpoint) % 4];

            let name = this._model.player[id].replace(/\n.*$/,'');
            show(nameplate($(`> .player.${c}`, this._root), l, name,
                           this._model.defen[id], this._connected[id]));

            let open = this._model.player_id[l] == this.viewpoint;
            this._view.shoupai[l]
                    = new Shoupai(show($(`.shoupai.${c}`, this._root)),
                                    this._pai, this._model.shoupai[l])
                        .redraw(open || this.open_shoupai).adjust();

            this._view.he[l]
                    = new He(show($(`.he.${c}`, this._root)),
                                    this._pai, this._model.he[l])
                        .redraw(lizhi_deposited(this._model, l));

            this._view.say[l] = hide($(`.say.${c}`, this._root).text(''));
            this._say[l] = null;
        }

        this._lunban = this._model.lunban;
        /* A riichi discard drawn here deposits its stick at the next turn,
         * whose update must then refresh the scores. */
        this._lizhi = !! this._model._lizhi;
        this._view.score.update();

        this._view.dialog
            = new HuleDialog($('.hule-dialog', this._root), this._pai,
                            this._model, this.viewpoint).hide();

        return this;
    }

    /* silent plays no sound: the replay viewer's seeks show a position
     * without its sounds. */
    update(data = {}, silent = false) {

        if (this._lunban >= 0 && this._lunban != this._model.lunban) {
            if (this._say[this._lunban]) {
                fadeOut(this._view.say[this._lunban]);
                this._say[this._lunban] = null;
            }
            else {
                hide(this._view.say[this._lunban].text(''));
            }
            if (this._lizhi) {
                this._view.score.redraw();
                this._lizhi = false;
            }
            this._view.he[this._lunban].redraw();
            this._view.shoupai[this._lunban].redraw().adjust();
        }

        if (   (this._say[this._lunban] == 'lizhi')
            || (this._say[this._lunban] == 'chi'   && ! data.fulou)
            || (this._say[this._lunban] == 'peng'  && ! data.fulou)
            || (this._say[this._lunban] == 'gang'
                            && !(data.fulou || data.gang || data.kaigang)))
        {
            fadeOut(this._view.say[this._lunban]);
            this._say[this._lunban] = null;
        }

        if (data.zimo) {
            this._view.shan.update();
            this._view.shoupai[data.zimo.l].redraw().adjust();
        }
        else if (data.dapai) {
            this._view.shoupai[data.dapai.l].dapai(data.dapai.p);
            if (this.sound_on && ! silent) {
                this._audio.dapai[data.dapai.l].currentTime = 0;
                this._audio.dapai[data.dapai.l].play();
            }
            this._view.he[data.dapai.l].dapai(data.dapai.p);
            this._lizhi = data.dapai.p.slice(-1) == '*';
        }
        else if (data.fulou) {
            this._view.shoupai[data.fulou.l].redraw().adjust();
        }
        else if (data.gang) {
            this._view.shoupai[data.gang.l].redraw().adjust();
        }
        else if (data.gangzimo) {
            this._view.shan.update();
            this._view.shoupai[data.gangzimo.l].redraw().adjust();
        }
        else if (data.kaigang) {
            this._view.shan.redraw();
        }
        else if (data.hule) {
            this.hule(data.hule, silent);
        }
        else if (data.pingju) {
            this.pingju(data.pingju);
        }
        else {
            this._view.score.redraw();
        }

        this._lunban = this._model.lunban;
        if (this._lunban >= 0) this._view.score.update();

        return this;
    }

    clear_bubbles() {
        for (let l = 0; l < 4; l++) {
            fadeOut(this._view.say[l]);
            this._say[l] = null;
        }
    }

    hule(hule, silent = false) {

        this.clear_bubbles();

        const open_hule = ()=>{
            if (this._open_hule == open_hule) this._open_hule = null;
            this._view.shoupai[hule.l].redraw(true);
            this._view.dialog.hule(hule);
            if (this.sound_on && ! silent && hule.damanguan)
                                                    this._audio.gong.play();
        };
        this._open_hule = open_hule;
        this._timeout_id = setTimeout(open_hule, 400);
    }

    /* Open a win's dialog still waiting out its delay at once: the replay
     * viewer's Next while a double ron's win is on its way. */
    open_hule() {
        if (! this._open_hule) return;
        this._timeout_id = clearTimeout(this._timeout_id);
        this._open_hule();
    }

    pingju(pingju) {

        this.clear_bubbles();
        let duration = 0;
        if (pingju.name.match(/^三家和/)) {
            duration = 400;
        }
        else {
            this._view.he[this._lunban]
                .redraw(lizhi_deposited(this._model, this._lunban));
            this._view.shoupai[this._lunban].redraw().adjust();
        }

        this._open_hule = null;
        this._timeout_id = setTimeout(()=>{
            for (let l = 0; l < 4; l++) {
                let open = this._model.player_id[l] == this.viewpoint
                            || pingju.shoupai[l] || this.open_shoupai;
                this._view.shoupai[l].redraw(open);
            }
            this._view.dialog.pingju(pingju);
        }, duration);
    }

    say(name, l, silent = false) {
        if (this.sound_on && ! silent) {
            this._audio[name][l].currentTime = 0;
            this._audio[name][l].play();
        }
        show(this._view.say[l].text(say_text[name]));
        this._say[l] = name;
    }

    kaiju(viewpoint) {
        if (viewpoint != null) this.viewpoint = viewpoint;
        hide($('> *', this._root));
        let [title, ...sub] = this._model.title.split('\n');
        $('.title', this._view.kaiju).empty().append(
                $('<div>').text(title),
                sub.map(line => $('<div class="sub">').text(line)));
        for (let id = 0; id < 4; id++) {
            let c = class_name[(4 - this.viewpoint + id) % 4];
            let name = this._model.player[id].replace(/\n.*$/,'');
            $(`.player .${c}`, this._view.kaiju).text(name);
        }
        show(this._view.kaiju);
    }

    summary(paipu) {
        this._timeout_id = clearTimeout(this._timeout_id);
        this._open_hule = null;
        this._view.dialog.hide();
        this._view.summary.scrollTop(0);
        if (paipu) fadeIn(summary(this._view.summary, paipu, this.viewpoint));
        else       hide(this._view.summary);
    }

    /* The viewpoint seat's フリテン above its nameplate while it may not ron;
     * a new deal's redraw hides it. */
    furiten(on) {
        if (on) show(this._view.furiten);
        else    hide(this._view.furiten);
    }

    players(players) {
        for (let id = 0; id < 4; id++) {
            this._connected[id] = !! players[id];
            let c = class_name[(id + 4 - this.viewpoint) % 4];
            mark_offline($(`> .player.${c}`, this._root), ! players[id]);
        }
    }
}
