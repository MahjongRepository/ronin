"use strict";

import $ from 'jquery';
import { finishLoading } from './loading.js';
import { GAME_PREF_KEY } from './game-prefs.js';
import { withoutBlockedPlayback } from './game-audio.js';

import Shadow from './ronin/shadow.js';
import Translate from './ronin/translate.js';
import Autoplay from './ronin/autoplay.js';
import Reply from './ronin/reply.js';
import RoninPlayer from './ronin/player.js';
import RoninSession from './ronin/session.js';
import wire from './ronin/wire.js';

const { scale } = Majiang.UI.Util;

export default function startGame(gameId, { wsUrl, gameTicket: ticket }) {

    const pai   = Majiang.UI.pai($('#loaddata'));
    const audio = withoutBlockedPlayback(Majiang.UI.audio($('#loaddata')));

    const player = new RoninPlayer($('#board'), pai, audio);
    player.view  = new Majiang.UI.Board($('#board .board'), pai, audio, player.model);

    new Majiang.UI.GameCtl($('#board'), GAME_PREF_KEY, player, player._view);

    scale($('#board'), $('#space'));
    $(window).on('resize', ()=>scale($('#board'), $('#space')));

    const shadow    = new Shadow();
    const translate = new Translate(player, shadow, new Autoplay($('#board .autoplay')));
    const session   = new RoninSession({
        wsUrl, gameId, gameTicket: ticket,
        onEvent:        msg => {
            translate.handle(msg);
            if (msg.t == wire.E.GAME_STARTED) finishLoading();
        },
        onSessionError: (code, message) => toast('エラー: ' + message),
        onPlayerStatus: (name, connected) => {
            const seat = shadow.names.indexOf(name);
            if (seat >= 0) {
                shadow.playersConnected[seat] = connected;
                player._view.players(shadow.playersConnected);
            }
        },
        onDisconnected: () => {
            translate.disconnected();
            toast('接続が切れました。再接続しています…');
        },
        onReconnected:  (msg) => {
            translate.reconnect(msg);
            finishLoading();
            toast('再接続しました');
        },
    });
    const reply = new Reply(shadow, obj => session.send(obj), () => session.goLobby());

    translate.onDecision  = (kind, r) => reply.decide(kind, r);
    translate.onGameError = (code, message) => {
        if (code != wire.GAME_ERROR.STALE_ACTION) toast('操作が拒否されました: ' + message);
    };

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
