import { type TemplateResult, html, nothing } from "lit-html";

import { type TileFace } from "@/entities/tile/lib/tile-utils";

import { Tile, TileBack } from "./tile";

/**
 * Where a tile of the player's own hand stands: one it may play now, the one its submitted answer played, one the
 * open decision does not take, or one waiting for a decision that would.
 */
type PlayableState = "selectable" | "selected" | "disabled" | "waiting";

/**
 * A tile in a hand: one the view knows, with its tile id when it came from a table, shown face up or as a back by
 * the display's choice; one of the player's own, face up with its id, that a decision may play; or a concealed
 * one, known only by its hand's count, which is always a back.
 */
type HandTile =
    | {
          readonly face: TileFace;
          readonly show: "face" | "back";
          readonly tileId?: number;
          readonly state?: undefined;
      }
    | {
          readonly face: TileFace;
          readonly show: "face";
          readonly tileId: number;
          readonly state: PlayableState;
      }
    | {
          readonly face?: undefined;
          readonly show: "concealed";
          readonly tileId?: undefined;
          readonly state?: undefined;
      };

interface HandProps {
    readonly tiles: readonly HandTile[];
    readonly drawnTile?: HandTile;
    /** Called with a selectable tile's id when the player taps it or presses Enter or Space on it. */
    readonly onTile?: (tileId: number) => void;
    /** What playing a selectable tile does, read out before its face (`Discard 5p`). */
    readonly tileAction?: string;
}

function TileFaceView(tile: HandTile): TemplateResult {
    return tile.show === "face" ? Tile(tile.face, "face") : TileBack();
}

/**
 * One slot of the hand. A tile of the player's own is always a native button, so it takes focus, Enter and Space,
 * and a turn never moves focus out of the hand: only a selectable one acts, the others say so with `aria-disabled`
 * (and the selected one, the tile its answer played, with `aria-pressed`) and ignore a press.
 */
function HandSlot(tile: HandTile, extraClass: string, props: HandProps): TemplateResult {
    const slotClass = `hand-tile${extraClass}`;
    if (tile.state === undefined) {
        return html`<span class="${slotClass}">${TileFaceView(tile)}</span>`;
    }
    const { state, tileId } = tile;
    const acts = state === "selectable";
    function press(): void {
        if (acts) {
            props.onTile?.(tileId);
        }
    }
    return html`<button
        type="button"
        class="${slotClass} hand-tile--${state}"
        aria-label=${`${props.tileAction ?? "Play"} ${tile.face}`}
        aria-disabled=${acts ? nothing : "true"}
        aria-pressed=${state === "selected" ? "true" : nothing}
        @click=${press}
    >${TileFaceView(tile)}</button>`;
}

/** Render a horizontal row of mahjong tiles with an optional drawn tile separated by a gap. */
function Hand(props: HandProps): TemplateResult {
    const { drawnTile, tiles } = props;
    return html`<span class="hand"
        >${tiles.map((tile) => HandSlot(tile, "", props))}${
            drawnTile ? HandSlot(drawnTile, " hand-drawn-gap", props) : ""
        }</span
    >`;
}

export { Hand };
export type { HandProps, HandTile, PlayableState };
