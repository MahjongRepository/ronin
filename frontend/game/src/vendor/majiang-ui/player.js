/*
 *  Majiang.UI.Player
 */
"use strict";

import $ from 'jquery';
import Majiang from '../majiang-core/index.js';

import fadein   from './fadein.js';
import selector from './selector.js';
const { hide, show, fadeIn }         = fadein;
const { setSelector, clearSelector } = selector;

export const BEEP_SECONDS = 5;

import mianzi from './mianzi.js';

export default class Player extends Majiang.Player {

    constructor(root, pai, audio) {
        super();
        this._node = {
            root:   root,
            timer:  $('.timer', root),
            button: $('.player-button', root),
            mianzi: $('.select-mianzi', root),
            dapai:  $('.shoupai.main .bingpai', root),
        };
        this._mianzi = mianzi(pai);

        this.sound_on = true;
        this._audio   = { beep: audio('beep') };

        this.clear_handler();
    }

    clear_handler() {
        this.clear_button();
        this.clear_mianzi();
        this.clear_dapai();
        clearTimeout(this._dialog_timeout);
        clearSelector('kaiju');
        clearSelector('dialog');
        $('.kaiju', this._node.root).off('.kaiju');
        $('.hule-dialog', this._node.root).off('.dialog');
        $('.summary .exit', this._node.root).off('.summary');
    }

    set_dialog_timeout(setup) {
        clearTimeout(this._dialog_timeout);
        this._dialog_timeout = setTimeout(setup, 800);
    }

    callback(reply) {
        this.clear_timer();
        this.clear_handler();
        this._callback(reply);
        return false;
    }

    set_button(type, callback) {
        show($(`.${type}`, this._node.button)
                .attr('tabindex', 0)
                .on('click.button', callback));
        this._show_button = true;
        this._buttons.push([type, callback]);
    }

    /**
     * A prompt's buttons beside ×, which skips them and runs callback; a click elsewhere on the board does nothing,
     * so a stray click never passes a call. On the seat's own turn (skip false) there is no ×: callback opens the
     * discard at once, a discard declines the buttons, and the arrow keys stay on the hand.
     */
    show_button(callback = ()=>{}, skip = true) {
        this.show_timer();
        if (! this._show_button) return callback();
        this._button_callback = callback;
        this._button_skip = skip;
        if (skip) {
            const handler = ()=>{ this.clear_button(); callback() };
            show($('.cansel', this._node.button)
                    .attr('tabindex', 0)
                    .on('click.button', handler));
        }
        else callback();

        show(this._node.button.width($(this._node.dapai).width()));
        const buttons = $('.button[tabindex]', this._node.button);
        const win = buttons.filter('.zimo, .rong');
        const focus = win.length ? buttons.index(win) : skip ? 0 : null;
        setSelector(buttons, 'button', skip ? {focus: focus, touch: false}
                    : {focus: focus, prev: null, next: null, touch: false});
    }

    clear_button() {
        hide($('.button', this._node.button));
        clearSelector('button');
        hide(this._node.button);
        this._node.root.off('.button');
        this._show_button = false;
        this._buttons = [];
    }

    select_mianzi(mianzi) {
        const buttons = this._buttons;
        const callback = this._button_callback;
        const skip = this._button_skip;
        const default_reply = this._default_reply;
        this.clear_button();
        this.clear_dapai();
        this._node.mianzi.empty();
        const back = $('<span class="back" title="戻る [Esc]" aria-label="戻る">戻る</span>')
                .on('click.mianzi', ()=>{
                    this.clear_mianzi();
                    this._default_reply = default_reply;
                    for (const [type, cb] of buttons) this.set_button(type, cb);
                    this.show_button(callback, skip);
                    return false;
                });
        for (let m of mianzi) {
            let msg = m.match(/\d/g).length == 4 ? {gang: m} : {fulou: m}
            if (! this._default_reply) this._default_reply = msg;
            this._node.mianzi.append(
                    this._mianzi(m, true)
                        .on('click.mianzi',()=>this.callback(msg)));
        }
        this._node.mianzi.append(back);
        clearTimeout(this._mianzi_timeout);
        show(this._node.mianzi.width($(this._node.dapai).width()));
        setSelector($('.mianzi, .back', this._node.mianzi), 'mianzi',
                    {touch: false});
        $(window).on('keyup.mianzi', (ev)=>{
            if (ev.key != 'Escape') return;
            back.trigger('click');
            return false;
        });
        return false;
    }

    clear_mianzi() {
        clearTimeout(this._mianzi_timeout);
        this._mianzi_timeout = setTimeout(()=>hide(this._node.mianzi), 400);
        clearSelector('mianzi');
    }

    select_dapai(lizhi) {

        if (lizhi) this._default_reply = { dapai: lizhi[0] + '*' };

        for (let p of lizhi || this.get_dapai(this.shoupai)) {
            let pai = $(p.slice(-1) == '_'
                            ? `.zimo .pai[data-pai="${p.slice(0,2)}"]`
                            : `> .pai[data-pai="${p}"]`,
                        this._node.dapai);
            if (lizhi) {
                pai.addClass('blink');
                p += '*';
            }
            pai.attr('tabindex', 0).attr('role','button')
                .on('click.dapai', (ev)=>{
                    $(ev.target).addClass('dapai');
                    this.callback({dapai: p});
                });
        }

        setSelector($('.pai[tabindex]', this._node.dapai),
                    'dapai', {focus: -1});
    }

    clear_dapai() {
        $('.pai', this._node.dapai).removeClass('blink');
        clearSelector('dapai');
    }

    set_timer(limit, allowed = 0, audio) {

        delete this._default_reply;

        let limit_ms   = Math.round(limit * 1000);
        let allowed_ms = Math.round(allowed * 1000);
        let bank       = Math.round(allowed);
        let time_limit = Date.now() + limit_ms + allowed_ms;

        if (this._timer_id) clearInterval(this._timer_id);
        let last_time;
        const tick = ()=>{
            let rest_ms = time_limit - Date.now();
            if (rest_ms <= 0) {
                this.timeout();
                return;
            }
            let time = Math.ceil(rest_ms / 1000);
            let in_base = rest_ms > allowed_ms;
            let base = Math.ceil((rest_ms - allowed_ms) / 1000);
            let text = ! in_base ? `${time}`
                     : bank      ? `${base}+${bank}`
                     :             `${base}`;
            if (text == this._node.timer.text()) return;
            if (this.sound_on && audio && time <= BEEP_SECONDS && time != last_time) {
                audio.currentTime = 0;
                audio.play();
            }
            last_time = time;
            this._node.timer.text(text)
                .toggleClass('bank', bank > 0 && ! in_base);
        };
        tick();
        this._timer_id = setInterval(tick, 200);
    }

    timeout() {
        this.callback(this._default_reply);
    }

    show_timer() {
        show(this._node.timer.width($(this._node.dapai).width() + 64));
    }

    clear_timer() {
        this._timer_id = clearInterval(this._timer_id);
        hide(this._node.timer.text(''));
    }

    action(msg, callback) {
        let limit, allowed;
        if (msg.timer) [ limit, allowed ] = msg.timer;
        let audio = ! (msg.kaiju || msg.hule || msg.pingju) && this._audio.beep;
        if (limit) this.set_timer(limit, allowed, audio);

        super.action(msg, callback);
    }

    action_kaiju(kaiju) {
        if (! this._view) this.callback();
        $('.kaiju', this._node.root).off('click')
                                    .on('click.kaiju', ()=>this.callback());
        this.set_dialog_timeout(()=>{
            setSelector($('.kaiju', this._node.root), 'kaiju',
                        { touch: false });
        });
    }

    action_qipai(qipai) { this.callback() }

    action_zimo(zimo, gangzimo) {
        if (zimo.l != this._menfeng) return this.callback();

        if (this.allow_hule(this.shoupai, null, gangzimo)) {
            this.set_button('zimo', ()=>this.callback({hule: '-'}));
        }

        if (this.allow_pingju(this.shoupai)) {
            this.set_button('pingju', ()=>this.callback({daopai: '-'}));
        }

        let gang_mianzi = this.get_gang_mianzi(this.shoupai);
        if (gang_mianzi.length == 1) {
            this.set_button('gang', ()=>this.callback({gang: gang_mianzi[0]}));
        }
        else if (gang_mianzi.length > 1) {
            this.set_button('gang', ()=>this.select_mianzi(gang_mianzi));
        }

        if (this.shoupai.lizhi && ! this._show_button) {
            return this.callback({dapai: zimo.p + '_'});
        }

        let lizhi_dapai = this.allow_lizhi(this.shoupai);
        if (lizhi_dapai.length) {
            this.set_button('lizhi', ()=>{
                this.clear_handler();
                this.select_dapai(lizhi_dapai);
            });
        }

        this.show_button(()=>this.select_dapai(), false);
    }

    action_dapai(dapai) {

        if (this.allow_no_daopai(this.shoupai)) {
            this.set_button('daopai', ()=>this.callback());
        }

        if (dapai.l == this._menfeng) {

            if (! this._show_button) return this.callback();

            setTimeout(()=>{
                this.show_button(()=>this.callback({daopai: '-'}))
            }, 500);
            return;
        }

        let d = ['','+','=','-'][(4 + this._model.lunban - this._menfeng) % 4];
        let p = dapai.p + d;

        if (this.allow_hule(this.shoupai, p)) {
            this.set_button('rong', ()=>this.callback({hule: '-'}));
        }

        let gang_mianzi = this.get_gang_mianzi(this.shoupai, p);
        if (gang_mianzi.length == 1) {
            this.set_button('gang', ()=>this.callback({fulou: gang_mianzi[0]}));
        }

        let peng_mianzi = this.get_peng_mianzi(this.shoupai, p);
        if (peng_mianzi.length == 1) {
            this.set_button('peng', ()=>this.callback({fulou: peng_mianzi[0]}));
        }
        else if (peng_mianzi.length > 1) {
            this.set_button('peng', ()=>this.select_mianzi(peng_mianzi));
        }

        let chi_mianzi = this.get_chi_mianzi(this.shoupai, p);
        if (chi_mianzi.length == 1) {
            this.set_button('chi', ()=>this.callback({fulou: chi_mianzi[0]}));
        }
        else if (chi_mianzi.length > 1) {
            this.set_button('chi', ()=>this.select_mianzi(chi_mianzi));
        }

        this.show_button(()=>{
            if (this._model.shan.paishu == 0
                && Majiang.Util.xiangting(this.shoupai) == 0)
                    this.callback({daopai: '-'});
            else    this.callback();
        });
    }

    action_fulou(fulou) {
        if (fulou.l != this._menfeng) return this.callback();
        if (fulou.m.match(/^[mpsz]\d{4}/)) return this.callback();

        this.show_button(()=>this.select_dapai());
    }

    action_gang(gang) {
        if (gang.l == this._menfeng) return this.callback();
        if (gang.m.match(/^[mpsz]\d{4}$/)) return this.callback();

        let d = ['','+','=','-'][(4 + this._model.lunban - this._menfeng) % 4];
        let p = gang.m[0] + gang.m.slice(-1) + d;

        if (this.allow_hule(this.shoupai, p, true)) {
            this.set_button('rong', ()=>this.callback({hule: '-'}));
        }

        this.show_button(()=>this.callback());
    }

    action_hule() {
        $('.hule-dialog', this._node.root).off('click')
                                    .on('click.dialog', ()=>this.callback());
        this.set_dialog_timeout(()=>{
            setSelector($('.hule-dialog', this._node.root), 'dialog',
                        { touch: false, focus: null });
            $('.hule-dialog .next', this._node.root).trigger('focus');
        });
    }

    action_pingju() {
        this.action_hule();
    }

    action_jieju(jieju) {
        const exit = $('.summary .exit', this._node.root);
        exit.off('.summary').on('click.summary', ()=>this.callback());
        this.set_dialog_timeout(()=>exit.trigger('focus'));
    }
}
