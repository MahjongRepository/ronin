/*
 *  scale.js
 */
"use strict";

import $ from 'jquery';

function corner(stage) {
    let controller = $('.controller', stage)[0];
    if (! controller) return { width: 0, height: 0 };
    let box = stage[0].getBoundingClientRect();
    let hud = controller.getBoundingClientRect();
    let gap = box.right - hud.right;
    return { width: box.right - hud.left + gap, height: hud.bottom - box.top + gap };
}

function scale(board, space = $()) {

    let hidden = space.outerHeight() || 0;
    let top    = board.offset().top - hidden;
    let width  = document.documentElement.clientWidth;
    let height = window.innerHeight - top;
    board.css('height', height);

    let table   = $('> .board', board);
    let tw      = table.outerWidth();
    let th      = table.outerHeight();
    let hud     = corner(board);
    let scale   = Math.min(width / tw, height / th);
    let reserve = 0;
    if ((width - tw * scale) / 2 < hud.width) {
        let beside = Math.min((width - 2 * hud.width) / tw, height / th);
        let below  = Math.min(width / tw, (height - hud.height) / th);
        if (below > beside) reserve = hud.height;
        scale = Math.max(beside, below);
    }
    let thumb  = window.matchMedia('(pointer: coarse) and (orientation: portrait)')
                        .matches;
    let x      = (width - tw * scale) / 2;
    let y      = Math.max(reserve, (height - th * scale) * (thumb ? 1 : 0.5));
    table.css('transform', `translate(${x}px, ${y}px) scale(${scale})`);

    if (hidden) $(window).scrollTop(hidden);
}

export default { scale: scale };
