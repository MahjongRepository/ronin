import { takesIntent } from "./intents";
import { decisionOf, roundConfirmOf } from "./pending";
import { type PlayOverlay } from "./play-display";
import {
    type EscapeStep,
    type PlayCommand,
    type PlayUi,
    escapeFocusKey,
    intentCommand,
} from "./play-ui";
import { SETTINGS_FOCUS_KEY } from "./settings-menu";
import { type LiveClient, type LocalIntent } from "./types";

export interface PlayShortcut {
    readonly command: PlayCommand;
    readonly focusKey: string | null;
}

export interface PlayShortcuts {
    readonly scope: string;
    readonly escape: PlayShortcut | null;
    readonly rightClick: PlayShortcut | null;
    readonly rightClickEnabled: boolean;
}

function shortcut(command: PlayCommand, focusKey: string | null = null): PlayShortcut {
    return { command, focusKey };
}

function closeShortcut(ui: PlayUi, overlay: PlayOverlay | null): PlayShortcut | null {
    if (overlay?.panel.kind === "leave") {
        return shortcut({ kind: "cancel_leave" });
    }
    if (overlay?.panel.kind === "notice_sheet") {
        return shortcut({ kind: "close_notice" });
    }
    if (overlay?.blocksBoard) {
        return null;
    }
    if (ui.settingsOpen) {
        return shortcut({ kind: "close_settings" }, SETTINGS_FOCUS_KEY);
    }
    return ui.pinnedNameplate === null ? null : shortcut({ kind: "pin_nameplate", seat: null });
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

export function playShortcuts(
    state: LiveClient,
    ui: PlayUi,
    { overlay, step }: { readonly overlay: PlayOverlay | null; readonly step: EscapeStep | null },
): PlayShortcuts {
    const close = closeShortcut(ui, overlay);
    const back = step === null ? null : shortcut(step.command, escapeFocusKey(step));
    const escape = close ?? (overlay === null ? (back ?? passShortcut(state)) : null);
    const rightClick = escape ?? (overlay === null ? discardShortcut(state) : null);
    const decision = decisionOf(state);
    const confirm = roundConfirmOf(state);
    return {
        escape,
        rightClick,
        rightClickEnabled: ui.rightClick,
        scope: JSON.stringify([
            decision?.waitId,
            decision?.status.kind === "submitted",
            confirm?.kind === "owed" ? confirm.waitId : confirm?.kind,
            overlay?.panel.kind,
            overlay?.panel.kind === "result" ? overlay.panel.display.page : null,
            escape,
            rightClick,
            ui.rightClick,
        ]),
    };
}
