import { type SeatPosition } from "@/entities/table";
import { type TileFace, type TileSpriteStatus } from "@/entities/tile";

import { DEFAULT_INPUT_SETTING } from "./input-setting";
import { DEFAULT_MOTION_SETTING } from "./motion-setting";
import { type LocalIntent } from "./types";

/**
 * What a notice tells, in the stack's order: the ongoing conditions (the connection, messages the client could not
 * read, tile faces) that stay until they recover, then the acknowledgements (the seat back, a refused
 * move) that leave on their own.
 */
export type NoticeKind =
    | "connection"
    | "unread"
    | "tile_sprite"
    | "browser_bars"
    | "reconnected"
    | "refused";

/**
 * What a control of the page does: send the client an intent, turn picking riichi's discard on or off, step back
 * from it (Escape), arm a tile for a second finger tap (or none), turn the round result's panel to a page, pin a
 * nameplate (or none) for the others' score differences, show or hide the play switches' names, ask to leave mid-game
 * or take that back, open a notice whole in its sheet or close it, open or close the controls' help, open or close the
 * settings menu, turn the sound on or off, or reload the page after a failure.
 */
export type PlayCommand =
    | { readonly kind: "intent"; readonly intent: LocalIntent }
    | { readonly kind: "toggle_riichi_pick" }
    | { readonly kind: "step_back" }
    | { readonly kind: "show_result_page"; readonly page: number }
    | { readonly kind: "arm_tile"; readonly tileId: number | null }
    | { readonly kind: "pin_nameplate"; readonly seat: SeatPosition | null }
    | { readonly kind: "toggle_switch_names" }
    | { readonly kind: "ask_leave" }
    | { readonly kind: "cancel_leave" }
    | { readonly kind: "show_notice"; readonly notice: NoticeKind }
    | { readonly kind: "close_notice" }
    | { readonly kind: "show_controls" }
    | { readonly kind: "close_controls" }
    | { readonly kind: "toggle_settings" }
    | { readonly kind: "close_settings" }
    | { readonly kind: "toggle_sound" }
    | { readonly kind: "toggle_animations" }
    | { readonly kind: "toggle_right_click" }
    | { readonly kind: "toggle_key_hints" }
    | { readonly kind: "reload" }
    | { readonly kind: "enter_fullscreen" };

/**
 * What moves the view's `ui` in one step: a page control, the client stepping on its own, the tile sprite's load
 * moving on, the browser's bars shown or collapsed over the page, or the socket's round trip measured, or forgotten
 * as a new socket opens.
 */
export type PlayUiInput =
    | PlayCommand
    | { readonly kind: "client_stepped" }
    | { readonly kind: "tile_sprite"; readonly status: TileSpriteStatus }
    | { readonly kind: "browser_bars"; readonly shown: boolean }
    | { readonly kind: "round_trip"; readonly roundTripMs: number | null };

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
 * What the view holds beside the client state: that the player is picking riichi's discard, or that a first finger tap armed a tile, for the decision of this wait id, so a newer decision never inherits any; the page of a round's result the player turned to, for
 * the round it names, so a newer result opens on its first page while a reconnect's copy of the same one keeps it;
 * the nameplate pinned for the others' score differences, which stays pinned until the player unpins it, since the
 * viewer's seat stays at the bottom; that the player opened the play switches' names beside their letters, which stay
 * open until the player closes them; that the player asked to leave mid-game and has yet to confirm it; that the
 * settings menu is open; whether the game plays its sounds, a setting the page keeps in this browser; where the
 * tile sprite's load stands, which the page's IO owns; and whether the browser's bars take part of the screen a swipe
 * would give the table (a phone browser's box shorter than its display), which the page measures, and whether this
 * browser can put the page in full screen instead; and the current socket's round trip, which its pings measure.
 */
export interface PlayUi {
    readonly riichiPickWaitId: number | null;
    readonly armedTile: { readonly waitId: number; readonly tileId: number } | null;
    readonly resultPage: { readonly round: string; readonly page: number } | null;
    readonly pinnedNameplate: SeatPosition | null;
    readonly switchNames: boolean;
    readonly confirmingLeave: boolean;
    /** The notice the player opened whole in its sheet, while it shows. */
    readonly noticeSheet: NoticeKind | null;
    /** The player opened the controls' help over the board from the settings menu. */
    readonly controlsHelp: boolean;
    readonly settingsOpen: boolean;
    readonly soundOn: boolean;
    readonly animationsOn: boolean;
    readonly rightClick: boolean;
    /** The decision controls show their digit keys, a setting the page keeps in this browser. */
    readonly keyHints: boolean;
    readonly tileSprite: TileSpriteStatus;
    readonly browserBars: boolean;
    readonly canEnterFullscreen: boolean;
    /** The current socket's round trip in milliseconds; null until its first pong. */
    readonly roundTripMs: number | null;
}

export const NO_PLAY_UI: PlayUi = {
    animationsOn: DEFAULT_MOTION_SETTING.animations,
    armedTile: null,
    browserBars: false,
    canEnterFullscreen: false,
    confirmingLeave: false,
    controlsHelp: false,
    keyHints: DEFAULT_INPUT_SETTING.keyHints,
    noticeSheet: null,
    pinnedNameplate: null,
    resultPage: null,
    rightClick: DEFAULT_INPUT_SETTING.rightClick,
    riichiPickWaitId: null,
    roundTripMs: null,
    settingsOpen: false,
    soundOn: true,
    switchNames: false,
    tileSprite: "loading",
};

export function intentCommand(intent: LocalIntent): PlayCommand {
    return { intent, kind: "intent" };
}

const RIICHI_PICK_FOCUS_KEY = "riichi-pick";

/** What Escape does while riichi's discard is picked: its command, and the key of the toggle it focuses back. */
export interface EscapeStep {
    readonly command: PlayCommand;
    readonly focusKey: string;
}

export const RIICHI_PICK_STEP_BACK: EscapeStep = {
    command: { kind: "step_back" },
    focusKey: RIICHI_PICK_FOCUS_KEY,
};

/** The key the riichi toggle renders, by its command, so Escape focuses it back; null for any other control. */
export function commandFocusKey(command: PlayCommand): string | null {
    return command.kind === "toggle_riichi_pick" ? RIICHI_PICK_FOCUS_KEY : null;
}
