import { type TemplateResult, html, nothing } from "lit-html";

import { type SeatTurn, type StandingBackEnd } from "@/entities/tile/lib/tile-body";
import { type TileFace, spokenTileName } from "@/entities/tile/lib/tile-utils";
import { type MessageKey, t } from "@/shared/i18n";

import { StandingTile, Tile, TileBack } from "./tile";

/**
 * Where a tile of the player's own hand stands: one it may play now (declaring riichi, while the riichi toggle is on;
 * armed, once a first finger tap lifted it for the second that discards it), the one its submitted answer played, one
 * the open decision holds back, or one waiting for a decision that would.
 */
type PlayableState = "selectable" | "armed" | "declaring" | "selected" | "disabled" | "waiting";

type TileAction = "discard" | "riichi_discard";

const TILE_ACTION_LABELS: Readonly<Record<TileAction, MessageKey>> = {
    discard: "game.hand.discard_tile",
    riichi_discard: "game.hand.riichi_discard_tile",
};

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
    /** Called with a selectable or declaring tile's id when the player taps it or presses Enter or Space on it. */
    readonly onTile?: (tileId: number) => void;
    readonly tileAction?: TileAction;
    readonly standing?: boolean;
    readonly turn?: SeatTurn;
}

function tileLabel(face: TileFace, action: TileAction | undefined): string {
    const key = action === undefined ? "game.hand.play_tile" : TILE_ACTION_LABELS[action];
    return t(key, { tile: spokenTileName(face) });
}

function TileFaceView(tile: HandTile, end: StandingBackEnd, props: HandProps): TemplateResult {
    const { standing, turn } = props;
    if (tile.show !== "face") {
        return TileBack(turn === undefined ? {} : { end, lay: "standing", turn });
    }
    return standing === true ? StandingTile(tile.face) : Tile(tile.face, "face", { turn });
}

interface SlotPlace {
    readonly end: StandingBackEnd;
    readonly extraClass: string;
    readonly paint: string | typeof nothing;
}

function slotPaint(props: HandProps, fromEnd: number): string | typeof nothing {
    return props.turn === 270 ? `z-index: ${fromEnd}` : nothing;
}

function runSlotPlace(props: HandProps, index: number, count: number): SlotPlace {
    const lowestOnScreen = props.turn === 270 ? 0 : props.tiles.length - 1;
    return {
        end: index === lowestOnScreen ? "shown" : "covered",
        extraClass: "",
        paint: slotPaint(props, count - index),
    };
}

function drawnSlotPlace(props: HandProps): SlotPlace {
    return { end: "shown", extraClass: " hand-drawn-gap", paint: slotPaint(props, 1) };
}

/** The focus key every tile of the player's own hand holds. */
export const HAND_TILE_FOCUS_KEY = "hand-tile";
export const PLAYABLE_TILE_FOCUS_KEY = "playable-tile";

/**
 * One slot of the hand. A tile of the player's own is always a native button, so it takes focus, Enter and Space,
 * and a turn never moves focus out of the hand: only a selectable, armed or declaring one acts, the others say so with `aria-disabled`
 * (and the selected one, the tile its answer played, with `aria-pressed`, as the armed one has) and ignore a press.
 */
function HandSlot(
    tile: HandTile,
    { end, extraClass, paint }: SlotPlace,
    props: HandProps,
): TemplateResult {
    const slotClass = `hand-tile${extraClass}`;
    if (tile.state === undefined) {
        return html`<span class="${slotClass}" style=${paint} data-tile-id=${tile.tileId ?? ""}>${TileFaceView(tile, end, props)}</span>`;
    }
    const { state, tileId } = tile;
    const acts = state === "selectable" || state === "armed" || state === "declaring";
    function press(): void {
        if (acts) {
            props.onTile?.(tileId);
        }
    }
    return html`<button
        type="button"
        class="${slotClass} hand-tile--${state}"
        data-tile-id=${tileId}
        aria-label=${tileLabel(tile.face, props.tileAction)}
        aria-disabled=${acts ? nothing : "true"}
        aria-pressed=${state === "selected" || state === "armed" ? "true" : nothing}
        data-focus-key=${acts ? `${HAND_TILE_FOCUS_KEY} ${PLAYABLE_TILE_FOCUS_KEY}` : HAND_TILE_FOCUS_KEY}
        @click=${press}
    >${TileFaceView(tile, end, props)}</button>`;
}

/** Render a horizontal row of mahjong tiles with an optional drawn tile separated by a gap. */
function Hand(props: HandProps): TemplateResult {
    const { drawnTile, tiles } = props;
    const count = tiles.length + (drawnTile === undefined ? 0 : 1);
    return html`<span class="hand"
        >${tiles.map((tile, index) => HandSlot(tile, runSlotPlace(props, index, count), props))}${
            drawnTile ? HandSlot(drawnTile, drawnSlotPlace(props), props) : ""
        }</span
    >`;
}

export { Hand };
export type { HandProps, HandTile, PlayableState, TileAction };
