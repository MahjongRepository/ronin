"use strict";

import fadein from '../../vendor/majiang-ui/fadein.js';

const { show, fadeOut } = fadein;

export const CHAT_SHOWN_MS = 4000;

/**
 * Show a chat line in round seat l's speech bubble on a majiang-ui Board for a few seconds, and return whether it is
 * shown. A call bubble (Board.say) owns the node: a chat does not cover one, and a call made or a bubble cleared by the
 * board while the chat shows is left as the board set it.
 */
export function showChat(board, l, text) {
    const node = board._view.say[l];
    if (! node || board._say[l]) return false;
    clearTimeout(node.data('chat'));
    show(node.text(text));
    node.data('chat', setTimeout(() => {
        if (! board._say[l] && node.text() == text) fadeOut(node);
    }, CHAT_SHOWN_MS));
    return true;
}
