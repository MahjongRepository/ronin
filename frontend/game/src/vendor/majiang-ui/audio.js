/*
 *  Majiang.UI.audio
 */
"use strict";

import $ from 'jquery';

export default function(loaddata) {

    const audio = {};

    $('audio', loaddata).each(function(){
        let name = $(this).data('name');
        audio[name] = $(this);
    });

    return function(name){
        let new_audio = audio[name].clone()[0];
        let volume    = audio[name].attr('volume');
        if (volume) {
            new_audio.oncanplaythrough = ()=>{
                new_audio.volume = + volume;
                new_audio.oncanplaythrough = null;
            };
        }
        return new_audio;
    }
}
