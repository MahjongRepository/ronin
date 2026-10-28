"use strict";

import { tCode } from '../../i18n/index.js';

/**
 * What a toast says of a refused action, by the server's GameErrorCode; the server's English message is for logs and
 * bots, never shown. A code the client does not know shows the generic refusal and is reported.
 */
function gameErrorText(code) {
    return tCode('game.error.', code, 'game.error.unknown');
}

/** What a toast says of a session error, by the server's SessionErrorCode, as gameErrorText does. */
function sessionErrorText(code) {
    return tCode('game.session_error.', code, 'game.session_error.unknown');
}

export { gameErrorText, sessionErrorText };
