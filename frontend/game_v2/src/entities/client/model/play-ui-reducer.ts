import { assertNever } from "@/shared/lib";

import { boardNotices } from "./board-notices";
import { choosingTiles, pickingRiichi } from "./decision-controls";
import { decisionOf } from "./pending";
import { type PlayCommand, type PlayUi, type TileChoiceKind } from "./play-ui";
import { resultRound } from "./result-controls";
import { type LiveClient, type LocalIntent } from "./types";

/** The view's `ui` once the client state moved on: a sheet with no notice left closes, so it never reopens. */
export function settledPlayUi(state: LiveClient, ui: PlayUi): PlayUi {
    if (ui.noticeSheet === null || boardNotices(state, ui).length > 0) {
        return ui;
    }
    return { ...ui, noticeSheet: null };
}

/** Whether the open decision was answered, so its steps stay as they were while the server answers. */
function answeredDecision(state: LiveClient): boolean {
    return decisionOf(state)?.status.kind === "submitted";
}

/** Picking riichi's discard turned on (for the open decision, closing a choice of tiles) or off. */
function toggledRiichiPick(state: LiveClient, ui: PlayUi): PlayUi {
    if (answeredDecision(state)) {
        return ui;
    }
    const waitId = decisionOf(state)?.waitId ?? null;
    const riichiPickWaitId = pickingRiichi(state, ui) ? null : waitId;
    return { ...ui, riichiPickWaitId, tileChoice: null };
}

/** A call's choice of tiles opened (for the open decision, turning the riichi pick off) or closed. */
function toggledTileChoice(state: LiveClient, ui: PlayUi, kind: TileChoiceKind): PlayUi {
    const decision = decisionOf(state);
    if (decision === null || answeredDecision(state)) {
        return ui;
    }
    const tileChoice = choosingTiles(state, ui) === kind ? null : { kind, waitId: decision.waitId };
    return { ...ui, riichiPickWaitId: null, tileChoice };
}

/** The view's `ui` after one of the open decision's steps: the riichi toggle, a call's choice of tiles, a step back. */
function steppedDecision(
    state: LiveClient,
    ui: PlayUi,
    command: Extract<
        PlayCommand,
        { kind: "toggle_riichi_pick" | "toggle_tile_choice" | "step_back" }
    >,
): PlayUi {
    if (command.kind === "toggle_riichi_pick") {
        return toggledRiichiPick(state, ui);
    }
    return command.kind === "toggle_tile_choice"
        ? toggledTileChoice(state, ui, command.offer)
        : steppedBack(state, ui);
}

/** One step back: out of a call's choice of tiles, else the riichi pick off. */
function steppedBack(state: LiveClient, ui: PlayUi): PlayUi {
    if (answeredDecision(state)) {
        return ui;
    }
    if (choosingTiles(state, ui) !== null) {
        return { ...ui, tileChoice: null };
    }
    return { ...ui, riichiPickWaitId: null };
}

/** The game's last result reopens on its first page; any other intent leaves the view's `ui` as it was. */
function uiAfterIntent(ui: PlayUi, intent: LocalIntent): PlayUi {
    return intent.type === "show_last_result" ? { ...ui, resultPage: null } : ui;
}

/**
 * The view's `ui` after a command: picking riichi's discard, or choosing a call's tiles, turns on or off for the open
 * decision, each turning the other off, and an answered decision keeps both as they were; stepping back leaves the
 * choice of tiles, else the riichi pick; the result's panel turns to a page of the result showing, and the game's last
 * result reopens on its first; a nameplate is pinned, or none; a notice opens whole in its sheet, or the sheet closes.
 */
export function nextPlayUi(state: LiveClient, ui: PlayUi, command: PlayCommand): PlayUi {
    switch (command.kind) {
        case "intent":
        case "reload": {
            return command.kind === "intent" ? uiAfterIntent(ui, command.intent) : ui;
        }
        case "ask_leave": {
            return { ...ui, confirmingLeave: true };
        }
        case "cancel_leave": {
            return { ...ui, confirmingLeave: false };
        }
        case "show_notice":
        case "close_notice": {
            return { ...ui, noticeSheet: command.kind === "show_notice" ? command.notice : null };
        }
        case "toggle_riichi_pick":
        case "toggle_tile_choice":
        case "step_back": {
            return steppedDecision(state, ui, command);
        }
        case "show_result_page": {
            const round = resultRound(state.table);
            return { ...ui, resultPage: round === null ? null : { page: command.page, round } };
        }
        case "pin_nameplate": {
            return { ...ui, pinnedNameplate: command.seat };
        }
        default: {
            return assertNever(command);
        }
    }
}
