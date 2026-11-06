import { type ConnectionTrouble, connectionTrouble } from "@/entities/session";
import { type Notice } from "@/entities/table";
import { type TileSpriteStatus } from "@/entities/tile";
import { type MessageKey, t } from "@/shared/i18n";
import { assertNever } from "@/shared/lib";
import { GAME_ERROR_CODE, SESSION_ERROR_CODE } from "@/shared/protocol";

import { type DecisionCountdown, pendingCountdown } from "./countdown";
import { desyncOf } from "./desync";
import { type NoticeKind, type PlayCommand, type PlayUi } from "./play-ui";
import { failureDisplay } from "./session-end";
import { type LiveClient, type TimedNotice } from "./types";

/** A notice over the table, with what it tells and the one control it may offer. */
export interface PlayNotice extends Notice {
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
function connectionNotice(trouble: ConnectionTrouble | null): PlayNotice | null {
    switch (trouble) {
        case null: {
            return null;
        }
        case "finding_game": {
            return { kind: "connection", text: t("game.notice.finding_game"), tone: "info" };
        }
        case "seat_lost": {
            return {
                kind: "connection",
                text: t("game.connection.lost"),
                tone: "warning",
            };
        }
        case "unreachable": {
            return {
                kind: "connection",
                text: t("game.notice.unreachable"),
                tone: "warning",
            };
        }
        default: {
            return assertNever(trouble);
        }
    }
}

const REFUSAL_TEXTS: ReadonlyMap<string, MessageKey> = new Map<string, MessageKey>([
    [SESSION_ERROR_CODE.RATE_LIMITED, "game.refusal.rate_limited"],
    [GAME_ERROR_CODE.NOT_YOUR_TURN, "game.refusal.not_your_turn"],
]);

function refusalText(code: string): string {
    return t(REFUSAL_TEXTS.get(code) ?? "game.refusal.refused");
}

function timedNotice(notice: TimedNotice | null): PlayNotice | null {
    if (notice?.kind === "reconnected") {
        return { kind: "reconnected", text: t("game.connection.restored"), tone: "success" };
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
    return {
        kind: "unread",
        text: t("game.notice.unread", { count }),
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
        action: { command: { kind: "reload" }, label: t("common.reload") },
        kind: "tile_sprite",
        text: t("game.notice.tile_sprite"),
        tone: "warning",
    };
}

/** The notices over the table, ongoing conditions before acknowledgements (`NoticeKind`); none while a failure blocks it. */
export function boardNotices(state: LiveClient, ui: PlayUi): PlayNotice[] {
    if (failureDisplay(state.session) !== null) {
        return [];
    }
    return [
        connectionNotice(connectionTrouble(state.session)),
        unreadNotice(desyncOf(state)?.unreadMessages ?? 0),
        tileSpriteNotice(ui.tileSprite),
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
