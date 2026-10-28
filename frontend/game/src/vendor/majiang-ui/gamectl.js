/*
 *  Majiang.UI.GameCtl
 */
"use strict";

import $ from 'jquery';

/* The stored settings, or the defaults when storage is blocked or holds
 * something else than a settings object. */
function read_pref(storage) {
    try {
        const pref = JSON.parse(localStorage.getItem(storage));
        if (pref && typeof pref == 'object' && ! Array.isArray(pref)) return pref;
    }
    catch (e) {
        console.warn('[ronin] settings unreadable, using the defaults:', e);
    }
    return { sound_on: true };
}

export default class GameCtl {

    /** Whether the boards a controller of `storage` drives will play sound, before one is built. */
    static sound_on(storage) {
        return !! read_pref(storage).sound_on;
    }

    constructor(root, storage, ...view) {
        this._node = {
            controller: $('.controller', root),
        };
        this._view = view;

        this._storage = storage;
        this._pref = read_pref(storage);
        delete this._pref.speed;

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
        try {
            localStorage.setItem(this._storage, JSON.stringify(this._pref));
        }
        catch (e) {
            console.warn('[ronin] settings not saved:', e);
        }
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
        this.set_sound_key();
    }

    /* [a] toggles the sound: the live game's key. The replay page leaves it
     * out, for keys of its own. */
    set_sound_key() {
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
}
