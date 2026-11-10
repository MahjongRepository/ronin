import { type DecisionAction } from "./decision-controls";
import { takesIntent } from "./intents";
import { decisionOf, roundConfirmOf } from "./pending";
import { type PlayOverlay, type PlayPanel } from "./play-display";
import { type EscapeStep, type PlayCommand, type PlayUi, intentCommand } from "./play-ui";
import { SETTINGS_FOCUS_KEY } from "./settings-menu";
import { type LiveClient, type LocalIntent, type PlayIntent } from "./types";

export interface PlayShortcut {
    readonly command: PlayCommand;
    readonly focusKey: string | null;
}

export interface PlayShortcuts {
    readonly scope: string;
    readonly escape: PlayShortcut | null;
    /** What Enter or Space does outside a focused control: the opening screen's OK while it shows. */
    readonly confirm: PlayShortcut | null;
    readonly rightClick: PlayShortcut | null;
    readonly rightClickEnabled: boolean;
    /** The digit keys' decision controls, while nothing shows over the board and the settings menu is closed. */
    readonly digits: ReadonlyMap<number, PlayShortcut>;
}

function shortcut(command: PlayCommand, focusKey: string | null = null): PlayShortcut {
    return { command, focusKey };
}

const PANEL_CLOSE: Partial<Readonly<Record<PlayPanel["kind"], PlayCommand>>> = {
    controls: { kind: "close_controls" },
    leave: { kind: "cancel_leave" },
    notice_sheet: { kind: "close_notice" },
};

function closeShortcut(ui: PlayUi, overlay: PlayOverlay | null): PlayShortcut | null {
    const panelClose = overlay === null ? undefined : PANEL_CLOSE[overlay.panel.kind];
    if (panelClose !== undefined) {
        return shortcut(panelClose);
    }
    if (overlay?.blocksBoard) {
        return null;
    }
    return ui.settingsOpen ? shortcut({ kind: "close_settings" }, SETTINGS_FOCUS_KEY) : null;
}

const CONFIRM_OPENING: PlayIntent = { type: "confirm_opening" };

/** The opening screen's OK, while it shows unblocked and the settings menu is closed. */
function openingShortcut(
    state: LiveClient,
    ui: PlayUi,
    overlay: PlayOverlay | null,
): PlayShortcut | null {
    if (overlay?.panel.kind !== "seating" || overlay.blocksBoard || ui.settingsOpen) {
        return null;
    }
    return takesIntent(state, CONFIRM_OPENING) ? shortcut(intentCommand(CONFIRM_OPENING)) : null;
}

function passShortcut(state: LiveClient): PlayShortcut | null {
    const intent: LocalIntent = { type: "pass" };
    return takesIntent(state, intent) ? shortcut(intentCommand(intent)) : null;
}

function discardShortcut(state: LiveClient): PlayShortcut | null {
    const viewer = state.table.players.find((player) => player.seat === state.viewerSeat);
    const tileId = viewer?.drawnTileId;
    if (tileId === undefined || tileId === null) {
        return null;
    }
    const intent: LocalIntent = { tileId, type: "discard" };
    return takesIntent(state, intent) ? shortcut(intentCommand(intent)) : null;
}

/**
 * Whether the board's own keys (pass, discard, back, tile arrows) reach it under the overlay: with none, or under the
 * opening screen's seating, which leaves the turn or call beneath it playable.
 */
export function leavesBoardKeys(overlay: PlayOverlay | null): boolean {
    return overlay === null || overlay.panel.kind === "seating";
}

/** The decision controls' digit keys; none under any panel (the opening screen's included) or the settings menu. */
function digitShortcuts(
    ui: PlayUi,
    overlay: PlayOverlay | null,
    actions: readonly DecisionAction[],
): ReadonlyMap<number, PlayShortcut> {
    if (overlay !== null || ui.settingsOpen) {
        return new Map();
    }
    return new Map(
        actions.flatMap((action) =>
            action.digit === null ? [] : [[action.digit, shortcut(action.command)] as const],
        ),
    );
}

export function playShortcuts(
    state: LiveClient,
    ui: PlayUi,
    {
        actions,
        overlay,
        step,
    }: {
        readonly actions: readonly DecisionAction[];
        readonly overlay: PlayOverlay | null;
        readonly step: EscapeStep | null;
    },
): PlayShortcuts {
    const close = closeShortcut(ui, overlay);
    const back = step === null ? null : shortcut(step.command, step.focusKey);
    const boardKeys = leavesBoardKeys(overlay);
    const escape =
        close ?? (boardKeys ? (back ?? passShortcut(state) ?? discardShortcut(state)) : null);
    const rightClick = escape;
    const confirm = openingShortcut(state, ui, overlay);
    const digits = digitShortcuts(ui, overlay, actions);
    const decision = decisionOf(state);
    const roundConfirm = roundConfirmOf(state);
    return {
        confirm,
        digits,
        escape,
        rightClick,
        rightClickEnabled: ui.rightClick,
        scope: JSON.stringify([
            decision?.waitId,
            decision?.status.kind === "submitted",
            roundConfirm?.kind === "owed" ? roundConfirm.waitId : roundConfirm?.kind,
            overlay?.panel.kind,
            overlay?.panel.kind === "result" ? overlay.panel.display.page : null,
            escape,
            confirm,
            rightClick,
            ui.rightClick,
            [...digits],
        ]),
    };
}
