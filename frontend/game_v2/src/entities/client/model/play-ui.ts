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
 * nameplate (or none) for the others' score differences, ask to leave mid-game or take that back, open a notice whole
 * in its sheet or close it, or reload the page after a failure.
 */
export type PlayCommand =
    | { readonly kind: "intent"; readonly intent: LocalIntent }
    | { readonly kind: "toggle_riichi_pick" }
    | { readonly kind: "toggle_tile_choice"; readonly offer: TileChoiceKind }
    | { readonly kind: "step_back" }
    | { readonly kind: "show_result_page"; readonly page: number }
    | { readonly kind: "pin_nameplate"; readonly seat: SeatPosition | null }
    | { readonly kind: "ask_leave" }
    | { readonly kind: "cancel_leave" }
    | { readonly kind: "show_notice"; readonly notice: NoticeKind }
    | { readonly kind: "close_notice" }
    | { readonly kind: "reload" };

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
 * viewer's seat stays at the bottom; that the player asked to leave mid-game and has yet to confirm it; and where the
 * tile sprite's load stands, which the page's IO owns.
 */
export interface PlayUi {
    readonly riichiPickWaitId: number | null;
    readonly tileChoice: { readonly waitId: number; readonly kind: TileChoiceKind } | null;
    readonly resultPage: { readonly round: string; readonly page: number } | null;
    readonly pinnedNameplate: SeatPosition | null;
    readonly confirmingLeave: boolean;
    /** The notice the player opened whole in its sheet, while it shows. */
    readonly noticeSheet: NoticeKind | null;
    readonly tileSprite: TileSpriteStatus;
}

export const NO_PLAY_UI: PlayUi = {
    confirmingLeave: false,
    noticeSheet: null,
    pinnedNameplate: null,
    resultPage: null,
    riichiPickWaitId: null,
    tileChoice: null,
    tileSprite: "loading",
};

export function intentCommand(intent: LocalIntent): PlayCommand {
    return { intent, kind: "intent" };
}
