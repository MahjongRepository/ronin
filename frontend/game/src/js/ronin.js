"use strict";

import $ from 'jquery';

import Shadow from './ronin/shadow.js';
import Translate from './ronin/translate.js';
import Reply from './ronin/reply.js';
import RoninPlayer from './ronin/player.js';
import RoninSession from './ronin/session.js';
import { showChat } from './ronin/chat.js';
import wire from './ronin/wire.js';

const { scale } = Majiang.UI.Util;

/**
 * A sound the browser refuses to autoplay before the page's first user gesture (a page reloaded mid-game) is skipped
 * instead of rejecting unhandled.
 */
function withoutBlockedPlayback(loadAudio) {
    return name => {
        const sound = loadAudio(name);
        const play = sound.play.bind(sound);
        sound.play = () => play().catch(error => {
            if (error.name != 'NotAllowedError') throw error;
        });
        return sound;
    };
}

export default function startGame(gameId, { wsUrl, gameTicket: ticket }) {

    const pai   = Majiang.UI.pai($('#loaddata'));
    const audio = withoutBlockedPlayback(Majiang.UI.audio($('#loaddata')));

    const player = new RoninPlayer($('#board'), pai, audio);
    player.view  = new Majiang.UI.Board($('#board .board'), pai, audio, player.model);
    player._view.no_player_name = false;

    const gameCtl = new Majiang.UI.GameCtl($('#board'), 'Majiang.pref',
                                            null, player, player._view);

    scale($('#board'), $('#space'));
    $(window).on('resize', ()=>scale($('#board'), $('#space')));

    const shadow    = new Shadow();
    const translate = new Translate(player, shadow);
    const session   = new RoninSession({
        wsUrl, gameId, gameTicket: ticket,
        onEvent:        msg => translate.handle(msg),
        onSessionError: (code, message) => toast('エラー: ' + message),
        onChat:         (name, text) => chat(name, text),
        onPlayerStatus: (name, connected) => {
            const seat = shadow.names.indexOf(name);
            if (seat >= 0) {
                shadow.playersConnected[seat] = connected;
                player._view.players(shadow.playersConnected);
            }
        },
        onReconnected:  (msg) => { toast('再接続しました'); translate.reconnect(msg); },
    });
    const reply = new Reply(shadow, obj => session.send(obj), () => session.goLobby());

    translate.onDecision  = (kind, r) => reply.decide(kind, r);
    translate.onGameError = (code, message) => {
        if (code != wire.GAME_ERROR.STALE_ACTION) toast('操作が拒否されました: ' + message);
    };

    function chat(name, text) {
        const seat = shadow.names.indexOf(name);
        if (seat < 0 || ! showChat(player._view, shadow.l(seat), text)) toast(name + ': ' + text);
    }

    function toast(text) {
        let el = $('#ronin-toast');
        if (! el.length) {
            el = $('<div id="ronin-toast">').css({
                position: 'fixed', bottom: '16px', left: '50%',
                transform: 'translateX(-50%)', zIndex: 1000,
                background: 'rgba(0,0,0,.8)', color: '#fff',
                padding: '8px 16px', borderRadius: '8px',
                fontSize: '16px', whiteSpace: 'pre-wrap',
                maxWidth: '80%',
            }).appendTo('body');
        }
        el.text(text).show();
        clearTimeout(el.data('t'));
        el.data('t', setTimeout(() => el.fadeOut(600), 4000));
    }

    session.connect();

    window.addEventListener('pagehide', () => session.close());
}
