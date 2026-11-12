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

/** A notice with its brief form for the board's field, where those words differ from its own. */
function withBrief(notice: PlayNotice, brief: string): PlayNotice {
    return brief === notice.text ? notice : { ...notice, brief };
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
            return withBrief(
                { kind: "connection", text: t("game.connection.lost"), tone: "warning" },
                t("game.connection.lost_brief"),
            );
        }
        case "unreachable": {
            return withBrief(
                { kind: "connection", text: t("game.notice.unreachable"), tone: "warning" },
                t("game.notice.unreachable_brief"),
            );
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

const REFUSAL_BRIEFS: ReadonlyMap<string, MessageKey> = new Map<string, MessageKey>([
    [SESSION_ERROR_CODE.RATE_LIMITED, "game.refusal.rate_limited_brief"],
]);

function refusalNotice(code: string): PlayNotice {
    const notice: PlayNotice = {
        kind: "refused",
        text: t(REFUSAL_TEXTS.get(code) ?? "game.refusal.refused"),
        tone: "warning",
    };
    const brief = REFUSAL_BRIEFS.get(code);
    return brief === undefined ? notice : withBrief(notice, t(brief));
}

function timedNotice(notice: TimedNotice | null): PlayNotice | null {
    if (notice?.kind === "reconnected") {
        return withBrief(
            { kind: "reconnected", text: t("game.connection.restored"), tone: "success" },
            t("game.connection.restored_brief"),
        );
    }
    if (notice?.kind === "refused") {
        return refusalNotice(notice.code);
    }
    return null;
}

/** The messages the client could not read since the last snapshot: what that means for the table, and that play goes on. */
function unreadNotice(count: number): PlayNotice | null {
    if (count === 0) {
        return null;
    }
    return withBrief(
        { kind: "unread", text: t("game.notice.unread", { count }), tone: "error" },
        t("game.notice.unread_brief", { count }),
    );
}

/**
 * The tile faces' notice once a load of the sprite failed, until one succeeds: the tiles show their names meanwhile,
 * and a reload is the player's way to try at once. The words stay the same across the retries.
 */
function tileSpriteNotice(status: TileSpriteStatus): PlayNotice | null {
    if (status !== "retrying" && status !== "failed") {
        return null;
    }
    return withBrief(
        {
            action: { command: { kind: "reload" }, label: t("common.reload") },
            kind: "tile_sprite",
            text: t("game.notice.tile_sprite"),
            tone: "warning",
        },
        t("game.notice.tile_sprite_brief"),
    );
}

/**
 * The way to a larger table while a phone browser's bars take part of the screen: full screen where the browser has
 * it, which also hides the system's bars; elsewhere a swipe, since the page stands taller than the viewport so that
 * one collapses them and the board grows into the room they leave.
 */
function browserBarsNotice(ui: PlayUi): PlayNotice | null {
    if (!ui.browserBars) {
        return null;
    }
    if (!ui.canEnterFullscreen) {
        return withBrief(
            { kind: "browser_bars", text: t("game.notice.browser_bars"), tone: "info" },
            t("game.notice.browser_bars_brief"),
        );
    }
    return withBrief(
        {
            action: {
                command: { kind: "enter_fullscreen" },
                label: t("game.notice.enter_fullscreen"),
            },
            kind: "browser_bars",
            text: t("game.notice.browser_bars_fullscreen"),
            tone: "info",
        },
        t("game.notice.browser_bars_fullscreen_brief"),
    );
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
        browserBarsNotice(ui),
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
