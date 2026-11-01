import { type SeatPosition } from "@/entities/table";
import { type TileFace, type TileSpriteStatus } from "@/entities/tile";

import { type LocalIntent } from "./types";

/** A call whose offers of one kind differ by their tiles (which chi, which kan), taken in two steps. */
export type TileChoiceKind = "chi" | "kan";

/**
 * What a notice tells, in the stack's order: the ongoing conditions (the connection, messages the client could not
 * read, tile faces) that stay until they recover, then the acknowledgements (the seat back, a refused
 * move) that leave on their own.
 */
export type NoticeKind = "connection" | "unread" | "tile_sprite" | "reconnected" | "refused";

/**
 * What a control of the page does: send the client an intent, turn picking riichi's discard on or off, open or close
 * a call's choice of tiles, step back from either (Back, Escape), turn the round result's panel to a page, pin a
 * nameplate (or none) for the others' score differences, show or hide the play switches' names, ask to leave mid-game
 * or take that back, open a notice whole in its sheet or close it, open or close the settings menu, turn the sound on
 * or off, or reload the page after a failure.
 */
export type PlayCommand =
    | { readonly kind: "intent"; readonly intent: LocalIntent }
    | { readonly kind: "toggle_riichi_pick" }
    | { readonly kind: "toggle_tile_choice"; readonly offer: TileChoiceKind }
    | { readonly kind: "step_back" }
    | { readonly kind: "show_result_page"; readonly page: number }
    | { readonly kind: "pin_nameplate"; readonly seat: SeatPosition | null }
    | { readonly kind: "toggle_switch_names" }
    | { readonly kind: "ask_leave" }
    | { readonly kind: "cancel_leave" }
    | { readonly kind: "show_notice"; readonly notice: NoticeKind }
    | { readonly kind: "close_notice" }
    | { readonly kind: "toggle_settings" }
    | { readonly kind: "close_settings" }
    | { readonly kind: "toggle_sound" }
    | { readonly kind: "reload" };

/**
 * What moves the view's `ui` in one step: a page control, the client stepping on its own, or the tile sprite's load
 * moving on.
 */
export type PlayUiInput =
    | PlayCommand
    | { readonly kind: "client_stepped" }
    | { readonly kind: "tile_sprite"; readonly status: TileSpriteStatus };

export const CLIENT_STEPPED: PlayUiInput = { kind: "client_stepped" };

/** A button of the open decision: its label and the tiles that tell it from another of its kind (two chi). */
export interface PlayAction {
    readonly label: string;
    readonly tiles: readonly TileFace[];
    readonly command: PlayCommand;
    /** For a toggle, whether it is on; null for a plain button. */
    readonly pressed: boolean | null;
}

/**
 * What the view holds beside the client state: that the player is picking riichi's discard, or choosing a call's
 * tiles, for the decision of this wait id, so a newer decision never inherits either; the page of a round's result the player turned to, for
 * the round it names, so a newer result opens on its first page while a reconnect's copy of the same one keeps it;
 * the nameplate pinned for the others' score differences, which stays pinned until the player unpins it, since the
 * viewer's seat stays at the bottom; that the player opened the play switches' names beside their letters, which stay
 * open until the player closes them; that the player asked to leave mid-game and has yet to confirm it; that the
 * settings menu is open; whether the game plays its sounds, a setting the page keeps in this browser; and where the
 * tile sprite's load stands, which the page's IO owns.
 */
export interface PlayUi {
    readonly riichiPickWaitId: number | null;
    readonly tileChoice: { readonly waitId: number; readonly kind: TileChoiceKind } | null;
    readonly resultPage: { readonly round: string; readonly page: number } | null;
    readonly pinnedNameplate: SeatPosition | null;
    readonly switchNames: boolean;
    readonly confirmingLeave: boolean;
    /** The notice the player opened whole in its sheet, while it shows. */
    readonly noticeSheet: NoticeKind | null;
    readonly settingsOpen: boolean;
    readonly soundOn: boolean;
    readonly tileSprite: TileSpriteStatus;
}

export const NO_PLAY_UI: PlayUi = {
    confirmingLeave: false,
    noticeSheet: null,
    pinnedNameplate: null,
    resultPage: null,
    riichiPickWaitId: null,
    settingsOpen: false,
    soundOn: true,
    switchNames: false,
    tileChoice: null,
    tileSprite: "loading",
};

export function intentCommand(intent: LocalIntent): PlayCommand {
    return { intent, kind: "intent" };
}

/** A control that opens a step of the decision Escape steps back from: the riichi toggle or a call's choice of tiles. */
export type StepOpener = Extract<
    PlayCommand,
    { kind: "toggle_riichi_pick" | "toggle_tile_choice" }
>;

/** What Escape does while a step of the decision is open: its command, and the control that opened the step. */
export interface EscapeStep {
    readonly command: PlayCommand;
    readonly opener: StepOpener;
}

function stepOpenerKey(opener: StepOpener): string {
    return opener.kind === "toggle_riichi_pick" ? "riichi-pick" : `tile-choice-${opener.offer}`;
}

/** The key a step's opener renders, by its command, so Escape focuses it back; null for any other control. */
export function commandFocusKey(command: PlayCommand): string | null {
    return command.kind === "toggle_riichi_pick" || command.kind === "toggle_tile_choice"
        ? stepOpenerKey(command)
        : null;
}

/** The key of the control that opened the step Escape steps back from. */
export function escapeFocusKey(escape: EscapeStep): string {
    return stepOpenerKey(escape.opener);
}
