"use strict";

import * as codec from './codec.js';
import wire  from './wire.js';

const MAX_RECONNECT_TRIES = 15;
const SERVER_SILENCE_LIMIT_MS = 90000;
const SILENCE_CHECK_INTERVAL_MS = 5000;

const E = wire.SESSION_ERROR;

const LOBBY_CODES = new Set([
    E.INTERNAL_ERROR,
    E.NOT_IN_GAME,
    E.INVALID_TICKET,
    E.RECONNECT_NO_SESSION,
    E.RECONNECT_GAME_MISMATCH,
    E.RECONNECT_ALREADY_ACTIVE,
    E.JOIN_GAME_NOT_FOUND,
    E.JOIN_GAME_NO_SESSION,
]);

/**
 * The game socket: joins with the ticket, resumes the seat with the same ticket after a drop, and leaves for the lobby
 * on a permanent error. The client sends nothing on its own, so a socket whose peer vanished (a FIN lost while the
 * device slept) never closes by itself: a server silent for longer than any legitimate wait counts as a drop, checked
 * on the wall clock so the first check after a wake sees the whole gap.
 */
class RoninSession {

    constructor({ wsUrl, gameId, gameTicket,
                  onEvent, onSessionError, onPlayerStatus, onReconnected }) {
        this.wsUrl   = wsUrl;
        this.gameId  = gameId;
        this.ticket  = gameTicket;
        this.onEvent = onEvent || (() => {});
        this.onSessionError = onSessionError || (() => {});
        this.onPlayerStatus = onPlayerStatus || (() => {});
        this.onReconnected = onReconnected || (() => {});

        this.ws = null;
        this.joined = false;
        this.gameEnded = false;
        this.manualClose = false;
        this.reconnectTries = 0;
        this.reconnectTimer = null;
        this.watchdog = null;
        this.lastFrameAt = 0;
    }

    connect() {
        const ws = new WebSocket(this.wsUrl);
        this.ws = ws;
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
            if (this.ws !== ws) return;
            this.startWatchdog(ws);
            this.send({ t: this.joined ? wire.T.RECONNECT : wire.T.JOIN_GAME, game_ticket: this.ticket });
        };
        ws.onmessage = (ev) => {
            if (this.ws !== ws) return;
            this.lastFrameAt = Date.now();
            let msg;
            try { msg = codec.decode(new Uint8Array(ev.data)); }
            catch (e) { console.error('[ronin] decode error:', e); return; }
            this.handle(msg);
        };
        ws.onclose = () => {
            if (this.ws !== ws) return;
            this.dropSocket();
        };
        ws.onerror = () => {};
    }

    startWatchdog(ws) {
        this.stopWatchdog();
        this.lastFrameAt = Date.now();
        this.watchdog = setInterval(() => {
            if (this.ws !== ws || Date.now() - this.lastFrameAt <= SERVER_SILENCE_LIMIT_MS) return;
            ws.onclose = null;
            ws.close();
            this.dropSocket();
        }, SILENCE_CHECK_INTERVAL_MS);
    }

    stopWatchdog() {
        if (this.watchdog) clearInterval(this.watchdog);
        this.watchdog = null;
    }

    dropSocket() {
        this.stopWatchdog();
        this.ws = null;
        if (this.manualClose || this.gameEnded) return;
        this.scheduleRetry(() => this.connect());
    }

    handle(msg) {
        const type = msg.type;
        if (type == null) {
            if (! this.joined) { this.joined = true; this.reconnectTries = 0; }
            if (msg.t == wire.E.GAME_END) this.gameEnded = true;
            this.onEvent(msg);
            return;
        }
        switch (type) {
        case wire.SESSION.ERROR:
            this.handleError(msg.code || '', msg.message || '');
            break;
        case wire.SESSION.PLAYER_LEFT:
            this.onPlayerStatus(msg.player_name, false);
            break;
        case wire.SESSION.PLAYER_RECONNECTED:
            this.onPlayerStatus(msg.player_name, true);
            break;
        case wire.SESSION.GAME_RECONNECTED:
            this.joined = true;
            this.reconnectTries = 0;
            this.onReconnected(msg);
            break;
        default:
            console.warn('[ronin] unknown session message:', msg);
        }
    }

    handleError(code, message) {
        if (code == E.JOIN_GAME_ALREADY_STARTED) {
            this.joined = true;
            this.send({ t: wire.T.RECONNECT, game_ticket: this.ticket });
            return;
        }
        if (code == E.RECONNECT_RETRY_LATER) {
            this.scheduleRetry(() => this.send({ t: wire.T.RECONNECT, game_ticket: this.ticket }));
            return;
        }
        if (LOBBY_CODES.has(code)) {
            console.warn('[ronin] leaving for the lobby on session error:', code, message);
            this.goLobby();
            return;
        }
        console.warn('[ronin] session error:', code, message);
        this.onSessionError(code, message);
    }

    scheduleRetry(retry) {
        if (this.reconnectTries >= MAX_RECONNECT_TRIES) { this.goLobby(); return; }
        const delay = Math.min(1000 * 2 ** this.reconnectTries, 15000);
        this.reconnectTries++;
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            if (! this.manualClose) retry();
        }, delay);
    }

    send(obj) {
        if (this.ws && this.ws.readyState == WebSocket.OPEN) {
            this.ws.send(codec.encode(obj));
            return true;
        }
        return false;
    }

    close() {
        this.manualClose = true;
        this.stopWatchdog();
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
        if (this.ws) { try { this.ws.close(); } catch (e) {} }
    }

    goLobby() {
        this.close();
        try { sessionStorage.removeItem('game_session:' + this.gameId); } catch (e) {}
        window.location.href = '/';
    }
}

export default RoninSession;
