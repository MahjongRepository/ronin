/*
 *  Majiang.UI.pai
 */
"use strict";

import $ from 'jquery';

export default function(loaddata) {

    const pai = {};

    $('.pai', loaddata).each(function(){
        let p = $(this).data('pai');
        pai[p] = $(this);
    });

    return function(p){
        return pai[p.slice(0,2)].clone();
    }
}
