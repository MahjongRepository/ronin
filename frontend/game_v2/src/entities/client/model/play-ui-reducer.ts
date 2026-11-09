import { assertNever } from "@/shared/lib";

import { boardNotices } from "./board-notices";
import { choosingTiles, pickingRiichi } from "./decision-controls";
import { decisionOf } from "./pending";
import { type PlayCommand, type PlayUi, type PlayUiInput, type TileChoiceKind } from "./play-ui";
import { resultRound } from "./result-controls";
import { stepSettingsMenu } from "./settings-menu";
import { type LiveClient, type LocalIntent } from "./types";

/** The view's `ui` once the client state moved on: a sheet with no notice left closes, so it never reopens. */
function settledPlayUi(state: LiveClient, ui: PlayUi): PlayUi {
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

/** The view's `ui` after one of the open decision's steps: an armed tile, the riichi toggle, a call's choice of tiles, a step back. */
function steppedDecision(
    state: LiveClient,
    ui: PlayUi,
    command: Extract<
        PlayCommand,
        { kind: "arm_tile" | "toggle_riichi_pick" | "toggle_tile_choice" | "step_back" }
    >,
): PlayUi {
    if (command.kind === "arm_tile") {
        return armedTileUi(state, ui, command.tileId);
    }
    if (command.kind === "toggle_riichi_pick") {
        return toggledRiichiPick(state, ui);
    }
    return command.kind === "toggle_tile_choice"
        ? toggledTileChoice(state, ui, command.offer)
        : steppedBack(state, ui);
}

type PageControlCommand = Extract<
    PlayCommand,
    {
        kind:
            | "ask_leave"
            | "cancel_leave"
            | "show_notice"
            | "close_notice"
            | "toggle_settings"
            | "close_settings"
            | "toggle_sound"
            | "toggle_animations";
    }
>;

/**
 * The page's own controls: the leave question asked or taken back, a notice opened whole in its sheet or the sheet
 * closed, either of which closes the settings menu; the settings menu opened or closed; the sound or animations turned on or off.
 */
function pageControlsUi(ui: PlayUi, command: PageControlCommand): PlayUi {
    switch (command.kind) {
        case "ask_leave":
        case "cancel_leave": {
            return { ...ui, confirmingLeave: command.kind === "ask_leave", settingsOpen: false };
        }
        case "show_notice":
        case "close_notice": {
            const noticeSheet = command.kind === "show_notice" ? command.notice : null;
            return { ...ui, noticeSheet, settingsOpen: false };
        }
        default: {
            const { menu } = stepSettingsMenu(
                { animationsOn: ui.animationsOn, open: ui.settingsOpen, soundOn: ui.soundOn },
                command.kind,
            );
            return {
                ...ui,
                animationsOn: menu.animationsOn,
                settingsOpen: menu.open,
                soundOn: menu.soundOn,
            };
        }
    }
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

/** An intent ends an armed tile, so a refused answer asks for both taps again; the game's last result reopens on its first page. */
function uiAfterIntent(ui: PlayUi, intent: LocalIntent): PlayUi {
    const unarmed = { ...ui, armedTile: null };
    return intent.type === "show_last_result" ? { ...unarmed, resultPage: null } : unarmed;
}

/** A tile armed for the open decision's second finger tap, or none. */
function armedTileUi(state: LiveClient, ui: PlayUi, tileId: number | null): PlayUi {
    const waitId = decisionOf(state)?.waitId;
    return {
        ...ui,
        armedTile: tileId === null || waitId === undefined ? null : { tileId, waitId },
    };
}

/**
 * The view's `ui` after a command, before it settles: picking riichi's discard, or choosing a call's tiles, turns on or off for the open
 * decision, each turning the other off, and an answered decision keeps both as they were; stepping back leaves the
 * choice of tiles, else the riichi pick; the result's panel turns to a page of the result showing, and the game's last
 * result reopens on its first; a nameplate is pinned, or none; the play switches' names show or hide; a notice opens whole in its sheet, or the sheet closes;
 * the settings menu opens or closes, and closes as the leave question or a notice's sheet opens; the sound turns on
 * or off.
 */
function commandedPlayUi(state: LiveClient, ui: PlayUi, command: PlayCommand): PlayUi {
    switch (command.kind) {
        case "toggle_right_click": {
            return { ...ui, rightClick: !ui.rightClick };
        }
        case "intent":
        case "enter_fullscreen":
        case "reload": {
            return command.kind === "intent" ? uiAfterIntent(ui, command.intent) : ui;
        }
        case "ask_leave":
        case "cancel_leave":
        case "show_notice":
        case "close_notice":
        case "toggle_settings":
        case "close_settings":
        case "toggle_sound":
        case "toggle_animations": {
            return pageControlsUi(ui, command);
        }
        case "arm_tile":
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
        case "toggle_switch_names": {
            return { ...ui, switchNames: !ui.switchNames };
        }
        default: {
            return assertNever(command);
        }
    }
}

/**
 * The view's `ui` after one step of the page, settled on the client state that step left (`state`): a page control
 * (an intent once the dispatcher stepped it), the client stepping on its own (a message, a tick, a failure) or the
 * tile sprite's load moving on. Every driver calls it after each step, so the board it draws is a function of the
 * client state and this `ui` alone.
 */
export function stepPlayUi(state: LiveClient, ui: PlayUi, input: PlayUiInput): PlayUi {
    switch (input.kind) {
        case "client_stepped": {
            return settledPlayUi(state, ui);
        }
        case "tile_sprite": {
            return settledPlayUi(state, { ...ui, tileSprite: input.status });
        }
        case "browser_bars": {
            return settledPlayUi(state, { ...ui, browserBars: input.shown });
        }
        default: {
            return settledPlayUi(state, commandedPlayUi(state, ui, input));
        }
    }
}
