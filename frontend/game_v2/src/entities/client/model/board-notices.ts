import { type SessionState, hasLostSeat } from "@/entities/session";
import { type BoardNotice, type TableState } from "@/entities/table";
import { type TileSpriteStatus } from "@/entities/tile";
import { type LoadStatus } from "@/shared/lib";
import { GAME_ERROR_CODE, SESSION_ERROR_CODE } from "@/shared/protocol";

import { type DecisionCountdown, pendingCountdown } from "./countdown";
import { desyncOf } from "./desync";
import { type NoticeKind, type PlayCommand, type PlayUi } from "./play-ui";
import { failureDisplay } from "./session-end";
import { type LiveClient, type TimedNotice } from "./types";

/** A notice over the table, with what it tells and the one control it may offer. */
export interface PlayNotice extends Omit<BoardNotice, "action" | "id" | "onShowAll"> {
    readonly kind: NoticeKind;
    readonly action?: { readonly label: string; readonly command: PlayCommand };
}

/**
 * The notices opened whole from the "Show all" of the one `opener` names, and the countdown of the decision or round
 * confirm that goes on beneath them.
 */
export interface NoticeSheetDisplay {
    readonly notices: readonly PlayNotice[];
    readonly opener: NoticeKind;
    readonly countdown: DecisionCountdown | null;
}

/**
 * The connection's notice while it is not holding the seat: finding the game; the seat this page held, lost to a
 * drop and being retried; or a connection that has failed since the page opened, being retried. The words stay the
 * same across the retries, so the live region reads them once. A page that only resumes its seat (a reload) shows
 * none.
 */
function connectionNotice(session: SessionState): PlayNotice | null {
    if (session.status === "ended" || session.status === "playing") {
        return null;
    }
    if (session.status === "recovering") {
        return { kind: "connection", text: "Finding your game…", tone: "info" };
    }
    if (hasLostSeat(session)) {
        return { kind: "connection", text: "Connection lost. Reconnecting…", tone: "warning" };
    }
    if (session.attempts.transport > 0) {
        return { kind: "connection", text: "Cannot reach the game. Retrying…", tone: "warning" };
    }
    return null;
}

function refusalText(code: string): string {
    if (code === SESSION_ERROR_CODE.RATE_LIMITED) {
        return "Too fast. Try that again";
    }
    if (code === GAME_ERROR_CODE.NOT_YOUR_TURN) {
        return "Not your turn";
    }
    return "That move was refused";
}

function timedNotice(notice: TimedNotice | null): PlayNotice | null {
    if (notice?.kind === "reconnected") {
        return { kind: "reconnected", text: "Reconnected", tone: "success" };
    }
    if (notice?.kind === "refused") {
        return { kind: "refused", text: refusalText(notice.code), tone: "warning" };
    }
    return null;
}

/** The messages the client could not read since the last snapshot: what that means for the table, and that play goes on. */
function unreadNotice(count: number): PlayNotice | null {
    if (count === 0) {
        return null;
    }
    const messages = count === 1 ? "a message" : `${count} messages`;
    return {
        kind: "unread",
        text: `The game server sent ${messages} this page could not read, so the table may be wrong until the server sends it again; play goes on.`,
        tone: "error",
    };
}

/**
 * The tile faces' notice once a load of the sprite failed, until one succeeds: the tiles show their names meanwhile,
 * and a reload is the player's way to try at once. The words stay the same across the retries.
 */
function tileSpriteNotice(status: TileSpriteStatus): PlayNotice | null {
    if (status !== "retrying" && status !== "failed") {
        return null;
    }
    return {
        action: { command: { kind: "reload" }, label: "Reload" },
        kind: "tile_sprite",
        text: "Tile images did not load; tiles show their names",
        tone: "warning",
    };
}

/**
 * The final standings' notice once the game ended and every try at loading them failed: the board shows no panel
 * meanwhile, and a reload is the player's way to try at once.
 */
function standingsNotice(table: TableState, status: LoadStatus): PlayNotice | null {
    if (table.phase !== "game_ended" || status !== "failed") {
        return null;
    }
    return {
        action: { command: { kind: "reload" }, label: "Reload" },
        kind: "standings",
        text: "The final standings did not load",
        tone: "error",
    };
}

/** The notices over the table, ongoing conditions before acknowledgements (`NoticeKind`); none while a failure blocks it. */
export function boardNotices(state: LiveClient, ui: PlayUi): PlayNotice[] {
    if (failureDisplay(state.session) !== null) {
        return [];
    }
    return [
        connectionNotice(state.session),
        unreadNotice(desyncOf(state)?.unreadMessages ?? 0),
        tileSpriteNotice(ui.tileSprite),
        standingsNotice(state.table, ui.standings),
        timedNotice(state.notice),
    ].filter((notice) => notice !== null);
}

/**
 * The notices opened whole, while any notice shows and nothing above the sheet in the overlay's precedence (an end,
 * the leave question) takes its place; with the "Show all" that opened them, where the focus goes back, and the
 * countdown of the decision or round confirm that goes on beneath it.
 */
export function noticeSheet(
    state: LiveClient,
    ui: PlayUi,
    notices: readonly PlayNotice[],
): NoticeSheetDisplay | null {
    const opener = ui.noticeSheet;
    if (opener === null || notices.length === 0 || ui.confirmingLeave) {
        return null;
    }
    return { countdown: pendingCountdown(state), notices, opener };
}
