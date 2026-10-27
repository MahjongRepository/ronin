/*
 *  scale.js
 */
"use strict";

import $ from 'jquery';

/** The room the gear's top-right corner HUD takes from the stage, with its inset on every side. */
function topRight(stage) {
    let controller = $('.controller', stage)[0];
    if (! controller) return { width: 0, height: 0 };
    let box = stage[0].getBoundingClientRect();
    let hud = controller.getBoundingClientRect();
    let gap = box.right - hud.right;
    return { width: box.right - hud.left + gap, height: hud.bottom - box.top + gap };
}

/** The room the auto switches' bottom-left corner HUD takes from the stage, with its inset on every side. */
function bottomLeft(stage) {
    let autoplay = $('.autoplay', stage)[0];
    if (! autoplay) return { width: 0, height: 0 };
    let box = stage[0].getBoundingClientRect();
    let hud = autoplay.getBoundingClientRect();
    let gap = hud.left - box.left;
    return { width: hud.right - box.left + gap, height: box.bottom - hud.top + gap };
}

/**
 * The table's own felt left of the left player's hand, in table pixels: the hand's box runs the table's whole height,
 * its melds included, so the switches may cover what lies outside it.
 */
function leftMargin(table) {
    let hand = $('.shoupai.shangjia', table)[0];
    let box  = table[0].getBoundingClientRect();
    if (! hand || ! box.width) return 0;
    let left = hand.getBoundingClientRect().left;
    return Math.max(0, (left - box.left) * table.outerWidth() / box.width);
}

/**
 * Fit the table to the stage beside its corner HUDs, the switches over the felt left of the left player's hand: when
 * the side felt is too narrow for them, the table either narrows to leave it, or keeps a strip above for the gear and
 * one below for the switches, whichever keeps it larger.
 */
function scale(board, space = $()) {

    let hidden = space.outerHeight() || 0;
    let top    = board.offset().top - hidden;
    let width  = document.documentElement.clientWidth;
    let height = window.innerHeight - top;
    board.css('height', height);

    let table   = $('> .board', board);
    let tw      = table.outerWidth();
    let th      = table.outerHeight();
    let gear    = topRight(board);
    let autoplay = bottomLeft(board);
    let margin  = leftMargin(table);
    let fits    = s => (width - tw * s) / 2 >= gear.width
                    && (width - tw * s) / 2 + margin * s >= autoplay.width;
    let scale   = Math.min(width / tw, height / th);
    let above   = 0;
    let below   = 0;
    if (! fits(scale)) {
        let beside = Math.min((width - 2 * gear.width) / tw,
                              (width / 2 - autoplay.width) / (tw / 2 - margin),
                              height / th);
        let strips = Math.min(width / tw, (height - gear.height - autoplay.height) / th);
        if (strips > beside) {
            above = gear.height;
            below = autoplay.height;
        }
        scale = Math.max(beside, strips);
    }
    let thumb  = window.matchMedia('(pointer: coarse) and (orientation: portrait)')
                        .matches;
    let x      = (width - tw * scale) / 2;
    let y      = Math.min(height - below - th * scale,
                          Math.max(above, (height - th * scale) * (thumb ? 1 : 0.5)));
    table.css('transform', `translate(${x}px, ${y}px) scale(${scale})`);

    if (hidden) $(window).scrollTop(hidden);
}

export default { scale: scale };
