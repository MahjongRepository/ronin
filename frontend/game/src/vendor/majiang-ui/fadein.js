/*
 *  fadein.js
 */
"use strict";

export default {

    show: node => node.off('transitionend').removeClass('hide fadeout'),

    hide: node => node.addClass('hide fadeout'),

    fadeIn: node =>{
        node.addClass('hide fadeout');
        setTimeout(()=>{
            node.removeClass('hide');
            setTimeout(()=>
                    node.off('transitionend')
                        .removeClass('fadeout'), 20)
        }, 100);
        return node;
    },

    fadeOut: node =>
        node.on('transitionend', ()=>
                    node.off('transitionend')
                        .addClass('hide'))
            .addClass('fadeout'),
}
