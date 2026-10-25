"use strict";

import fadein from '../../vendor/majiang-ui/fadein.js';

const { show, fadeOut } = fadein;

export const CHAT_SHOWN_MS = 4000;

function isTableCovered(board) {
    return $('> .hule-dialog, > .summary', board._root).not('.hide').length > 0;
}

/**
 * Show a chat line in round seat l's chat bubble on a majiang-ui Board for a few seconds, and return whether it is
 * shown. The chat bubble is its own node beside the seat's nameplate, apart from the call bubble (Board.say), so a chat
 * never reads as a call and both can show at once. While a result dialog or the final standings cover the table the
 * line is not shown, so the caller can show it elsewhere. The text goes in as text, never as markup.
 */
export function showChat(board, l, text) {
    const node = board._view.chat[l];
    if (! node?.length || isTableCovered(board)) return false;
    clearTimeout(node.data('chat'));
    show(node.empty().attr('title', text).append($('<span>').text(text)));
    node.data('chat', setTimeout(() => fadeOut(node), CHAT_SHOWN_MS));
    return true;
}
