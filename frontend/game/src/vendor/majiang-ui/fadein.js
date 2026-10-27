/*
 *  fadein.js
 */
"use strict";

import $ from 'jquery';

/* A fade-in still on its way is cancelled by any later hide, show or fade
 * of the node, so a node hidden meanwhile stays hidden. */
function cancel_fadein(node) {
    return node.each((i, el)=>clearTimeout($.data(el, 'fadein')));
}

function later(node, delay, step) {
    const timer = setTimeout(step, delay);
    node.each((i, el)=>$.data(el, 'fadein', timer));
}

export default {

    show: node => cancel_fadein(node).off('transitionend').removeClass('hide fadeout'),

    hide: node => cancel_fadein(node).addClass('hide fadeout'),

    fadeIn: node =>{
        cancel_fadein(node).addClass('hide fadeout');
        later(node, 100, ()=>{
            node.removeClass('hide');
            later(node, 20, ()=>
                    node.off('transitionend')
                        .removeClass('fadeout'));
        });
        return node;
    },

    fadeOut: node =>
        cancel_fadein(node).on('transitionend', ()=>
                    node.off('transitionend')
                        .addClass('hide'))
            .addClass('fadeout'),
}
