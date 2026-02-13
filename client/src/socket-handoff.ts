import { type GameSocket, type MessageHandler, type StatusHandler } from "./websocket";

/**
 * Manages WebSocket socket ownership across room-to-game view transitions.
 *
 * The room view owns the socket initially. When `game_starting` is received,
 * it calls `beginHandoff()` to mark the socket for transfer and install a
 * buffering handler so messages arriving before the game view binds its own
 * handlers are not lost.  The game view calls `consumeHandoff()` to take
 * ownership, rebind handlers, and replay any buffered messages.
 */

interface HandoffState {
    socket: GameSocket;
    roomId: string;
    bufferedMessages: Record<string, unknown>[];
}

let activeSocket: GameSocket | null = null;
let pendingHandoff: HandoffState | null = null;

/** Store the active socket for the current phase owner. */
export function setActiveSocket(newSocket: GameSocket): void {
    activeSocket = newSocket;
}

/**
 * Mark the socket for handoff from room to game view.
 * Called by the room view when `game_starting` is received.
 *
 * Installs a temporary buffering handler on the socket so any messages
 * arriving between now and consumeHandoff() are captured and replayed.
 */
export function beginHandoff(roomId: string): void {
    if (!activeSocket) {
        return;
    }
    const state: HandoffState = { bufferedMessages: [], roomId, socket: activeSocket };
    activeSocket.setHandlers(
        (message) => {
            state.bufferedMessages.push(message);
        },
        () => {},
    );
    pendingHandoff = state;
    activeSocket = null;
}

/**
 * Consume the pending handoff in the game view.
 * Returns the socket if the roomId matches, otherwise null.
 * The caller should rebind handlers and then call `replayBufferedMessages`
 * to process any messages that arrived during the handoff window.
 */
export function consumeHandoff(roomId: string): GameSocket | null {
    if (!pendingHandoff || pendingHandoff.roomId !== roomId) {
        clearHandoff();
        return null;
    }
    const { socket } = pendingHandoff;
    // Keep pendingHandoff alive until drainBufferedMessages is called
    activeSocket = socket;
    return socket;
}

/**
 * Drain and return any messages buffered during the handoff window.
 * Must be called after consumeHandoff and after the game view has
 * rebound its handlers on the socket.
 */
export function drainBufferedMessages(): Record<string, unknown>[] {
    if (!pendingHandoff) {
        return [];
    }
    const messages = pendingHandoff.bufferedMessages;
    pendingHandoff = null;
    return messages;
}

/** Clear any pending handoff state. */
export function clearHandoff(): void {
    pendingHandoff = null;
}

/** Check if a handoff is pending for a specific room. */
export function isHandoffPending(roomId: string): boolean {
    return pendingHandoff !== null && pendingHandoff.roomId === roomId;
}

export type { MessageHandler, StatusHandler };
