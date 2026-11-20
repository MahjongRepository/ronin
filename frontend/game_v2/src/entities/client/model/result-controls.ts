import { type TableState, roundEndPageAt, roundEndPageNames } from "@/entities/table";
import { type MessageKey, t } from "@/shared/i18n";

import { type DecisionCountdown, roundConfirmCountdown } from "./countdown";
import { takesIntent } from "./intents";
import { roundConfirmOf } from "./pending";
import { type PlayAction, type PlayUi, intentCommand } from "./play-ui";
import { type LiveClient, type PlayIntent, type RoundConfirm } from "./types";

/** How the viewer reads the round result shown: as the round confirm it owes or sent, or as the game's last result. */
type ResultRead = RoundConfirm | { readonly kind: "final" };

const FINAL: ResultRead = { kind: "final" };

/**
 * The round result's controls in its panel: its one primary button (the next page of a result the player still has
 * to confirm, then the confirm on its last page, or the game's last result's way to the game's end), whether the seat
 * waits for the others after confirming, and the countdown to the server's round advance while the confirm is owed.
 */
export interface ResultControls {
    readonly action: PlayAction | null;
    readonly waiting: boolean;
    readonly countdown: DecisionCountdown | null;
}

const CONFIRM_RESULT: PlayIntent = { type: "confirm_result" };
const SHOW_LAST_RESULT: PlayIntent = { type: "show_last_result" };

const CONFIRM_LABELS: Readonly<Record<"owed" | "final", MessageKey>> = {
    final: "game.result.final_scores",
    owed: "common.ok",
};

/**
 * The hand a table's result ends, which a reconnect's snapshot of it names alike: the server's deal number `n`, which
 * a snapshot of the hand's own result pending keeps, within its game.
 */
export function resultRound(table: TableState): string | null {
    if (table.roundEndResult === null) {
        return null;
    }
    return `${table.gameId}/${table.roundNumber}`;
}

/** The result page the player turned to, while its round's result shows; else the first. */
export function shownResultPage(table: TableState, ui: PlayUi): number {
    const round = resultRound(table);
    if (table.roundEndResult === null || ui.resultPage === null || ui.resultPage.round !== round) {
        return 0;
    }
    return roundEndPageAt(table.roundEndResult, ui.resultPage.page).index;
}

/** The button to a result's next page, named for whose page it is. */
function pageAction(table: TableState, page: number): PlayAction {
    const result = table.roundEndResult;
    const name =
        result === null ? undefined : roundEndPageNames({ players: table.players, result })[page];
    if (name === undefined) {
        throw new Error(`A round result has no page ${page}`);
    }
    return {
        command: { kind: "show_result_page", page },
        label: name,
        pressed: null,
        tiles: [],
    };
}

/** The confirm's button, when the dispatcher takes the confirm now. */
function confirmAction(state: LiveClient, confirm: ResultRead): PlayAction | null {
    if (
        (confirm.kind !== "owed" && confirm.kind !== "final") ||
        !takesIntent(state, CONFIRM_RESULT)
    ) {
        return null;
    }
    return {
        command: intentCommand(CONFIRM_RESULT),
        label: t(CONFIRM_LABELS[confirm.kind]),
        pressed: null,
        tiles: [],
    };
}

/**
 * The round result's controls: while the confirm is owed (or the game's last result unread), the next winner's name through every page
 * but the last and the confirm on the last, so the player reads each winner of a double ron before confirming; once
 * the seat confirmed, that it waits for the others, its pages still turning on to the last (a reconnect opens on the
 * first), with no confirm.
 */
export function resultControls(state: LiveClient, page: number): ResultControls | null {
    const { table } = state;
    const read = roundConfirmOf(state) ?? (state.showsLastResult ? FINAL : null);
    if (read === null || table.roundEndResult === null) {
        return null;
    }
    const countdown = roundConfirmCountdown(state);
    const { count, index } = roundEndPageAt(table.roundEndResult, page);
    const pageOn = index < count - 1 ? pageAction(table, index + 1) : null;
    if (read.kind === "sent" || read.kind === "confirmed") {
        return { action: pageOn, countdown, waiting: true };
    }
    return { action: pageOn ?? confirmAction(state, read), countdown, waiting: false };
}

/** The game end's button back to the game's last result, when the dispatcher takes it now. */
export function lastResultAction(state: LiveClient): PlayAction | null {
    if (!takesIntent(state, SHOW_LAST_RESULT)) {
        return null;
    }
    return {
        command: intentCommand(SHOW_LAST_RESULT),
        label: t("game.result.last_hand"),
        pressed: null,
        tiles: [],
    };
}
