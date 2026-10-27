/*
 *  Majiang.UI.GameCtl
 */
"use strict";

import $ from 'jquery';

import fadein from './fadein.js';
const { hide, show } = fadein;

export default class GameCtl {

    constructor(root, storage, game, ...view) {
        this._node = {
            controller: $('.controller', root),
            download:   $('.download', root),
        };
        this._game = game;
        this._view = view;

        this._storage = storage;
        this._pref = localStorage.getItem(storage)
                        ? JSON.parse(localStorage.getItem(storage))
                        : { sound_on: true };
        delete this._pref.speed;

        if (game) game._view.no_player_name = true;
        this.redraw();
    }

    redraw() {
        this.sound(this._pref.sound_on);
        this.menu(false);
        this.set_handler();
    }

    sound(on) {
        this._view.forEach(v => v.sound_on = on);
        $('.sound', this._node.controller)
            .attr('aria-checked', String(on))
            .find('.state').text(on ? 'ON' : 'OFF');
        this._pref.sound_on = on;
        localStorage.setItem(this._storage, JSON.stringify(this._pref));
        return false;
    }

    menu(open) {
        this._menu_open = open;
        $('.settings-toggle', this._node.controller)
            .attr('aria-expanded', String(open));
        $('.settings-menu', this._node.controller).toggleClass('hide', ! open);
    }

    set_handler() {

        this.clear_handler();

        const ctl = this._node.controller;
        const toggle = $('.settings-toggle', ctl);
        toggle.on('click', ()=>this.menu(! this._menu_open));
        $('.sound', ctl).on('click', ()=>this.sound(! this._pref.sound_on));
        ctl.on('click.controler', (ev)=>ev.stopPropagation());

        $(document).on('click.controler', (ev)=>{
            if (this._menu_open && ! ctl.has(ev.target).length) this.menu(false);
        });
        $(window).on('keydown.controler', (ev)=>{
            if (ev.key != 'Escape' || ! this._menu_open) return;
            ev.stopImmediatePropagation();
            const focused = ctl.has(document.activeElement).length;
            this.menu(false);
            if (focused) toggle.trigger('focus');
        });
        $(window).on('keyup.controler', (ev)=>{
            if (ev.key == 'a') this.sound(! this._pref.sound_on);
        });
    }

    clear_handler() {
        $('.settings-toggle, .sound', this._node.controller).off('click');
        this._node.controller.off('.controler');
        $(document).off('.controler');
        $(window).off('.controler');
    }

    stop() {
        this._game.stop();
        let blob  = new Blob([ JSON.stringify(this._game._paipu) ],
                             { type: 'application/json' });
        $('a', this._node.download)
            .attr('href', URL.createObjectURL(blob))
            .attr('download', '牌譜.json');
        show(this._node.download);
        this.stoped = true;
    }

    start() {
        this.stoped = false;
        hide(this._node.download);
        this._game.start();
    }

    shoupai() {
        const game = this._game;
        if (game._status == 'hule')   return true;
        if (game._status == 'pingju') return true;
        if (game._status == 'jieju')  return true;
        game._view.open_shoupai = ! game._view.open_shoupai;
        game._view.redraw();
        return false;
    }
}
