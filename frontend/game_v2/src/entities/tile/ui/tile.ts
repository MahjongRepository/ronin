import { pageTileLabels } from "@ronin/shared/tile-labels";
import { html, nothing, svg } from "lit-html";

import {
    BODY_VIEW_WIDTH,
    FACE_ART_VIEW,
    type FaceBox,
    type FaceSuit,
    STANDING_BODY,
    type SeatTurn,
    type StandingBackEnd,
    type TileBody,
    type TileLay,
    type TileSlot,
    faceArtViewBox,
    lyingSlot,
    standingFaceBox,
    tileBody,
} from "@/entities/tile/lib/tile-body";
import { tileLabel } from "@/entities/tile/lib/tile-labels";
import { type TileFace, spokenTileName } from "@/entities/tile/lib/tile-utils";
import { type WindScript, t } from "@/shared/i18n";

const HONOR_FACES = ["東", "南", "西", "北", "白", "發", "中"] as const;
const RED_DRAGON: TileFace = "7z";

/**
 * Put the tile sprite's symbols in the document, in one hidden container, and mark the root so tiles stop showing
 * their names in place of the faces. Throws on markup holding no tile symbol, such as an error page served in its
 * place.
 */
function injectTileSprite(sprite: string): void {
    const container = document.createElement("div");
    container.innerHTML = sprite;
    if (container.querySelector('symbol[id^="tile-"]') === null) {
        throw new Error("the tile sprite holds no tile symbol");
    }
    container.style.display = "none";
    container.setAttribute("aria-hidden", "true");
    document.body.prepend(container);
    document.documentElement.dataset.tileSprite = "ready";
}

function injectTileBodies(bodies: string): void {
    const container = document.createElement("div");
    container.innerHTML = bodies;
    const sprite = container.querySelector("svg");
    if (sprite === null || sprite.querySelector('symbol[id^="body-"]') === null) {
        throw new Error("the tile body sprite holds no body symbol");
    }
    sprite.setAttribute("aria-hidden", "true");
    Object.assign(sprite.style, {
        height: "0",
        overflow: "hidden",
        position: "absolute",
        width: "0",
    });
    document.body.prepend(sprite);
}

function placeholderFace(face: TileFace): string {
    const [rank, suit] = face;
    if (suit === "z") {
        return HONOR_FACES[Number(rank) - 1];
    }
    return `${rank === "0" ? "5" : rank}${suit}`;
}

function TileBack(layout: TileLayout = {}) {
    const body = bodyOf("back", layout);
    const width = inBodyUnits(body.across);
    const height = inBodyUnits(body.top + body.edge);
    const uncovered =
        body.uncoveredId === null
            ? nothing
            : svg`<use class="tile__uncovered" href="#${body.uncoveredId}" width="${width}" height="${height}"/>`;
    return html`<span class="tile tile-back" style=${bodyStyle(body, layout)} aria-label=${t("tile.hidden")}>${svg`<svg class="tile__body" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">${uncovered}<use href="#${body.id}" width="${width}" height="${height}"/></svg>`}</span>`;
}

/**
 * Render a mahjong tile with a face identity and a display mode.
 *
 * "face" renders the tile's face sprite over its short name, which the stylesheet hides once the sprite is in the
 * document, so a tile stays readable while the sprite loads or when it never does.
 * "back" renders the tile's back (the face identity is preserved but not visible).
 * `labels` is the script of the face's corner label, the page's setting unless given; null draws none.
 */
function Tile(face: TileFace, show: "face" | "back", options: TileOptions = {}) {
    if (show === "back") {
        return TileBack(options);
    }
    const body = bodyOf("face", options);
    const labels = options.labels === undefined ? pageTileLabels() : options.labels;
    return html`<span class="tile" style=${bodyStyle(body, options)}>${FaceBody(face, body, labels)}</span>`;
}

function FaceBody(face: TileFace, body: TileBody, labels: WindScript | null) {
    const box = body.face;
    if (box === null) {
        throw new Error("A face-up tile's body must hold a face box");
    }
    const width = inBodyUnits(body.across);
    const height = inBodyUnits(body.top + body.edge);
    const view = faceArtViewBox(faceSuit(face));
    const spread = spreadFaceOverBody(box, artViewBox(view, body.artTurn), {
        across: body.across,
        down: body.top + body.edge,
        surface: { height: body.top, left: 0, top: 0, width: body.across },
        turn: body.artTurn,
    });
    return svg`<svg class="tile__body" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="${spokenTileName(face)}"><use href="#${body.id}" width="${width}" height="${height}"/><svg class="tile__face" x="0" y="0" width="${width}" height="${height}" viewBox="${viewBoxOf(spread.viewBox)}" preserveAspectRatio="none"><g transform="${ART_TURNS[body.artTurn](view)}">${FaceArt(face, view, { labels, room: spread.labelRoom })}</g></svg></svg>`;
}

const BODY_VIEW_HEIGHT = BODY_VIEW_WIDTH * STANDING_BODY.height;
const FACE_LABEL_INSET = { baseline: 128, right: 19 } as const;
const SUITS_BUT_HONORS: readonly FaceSuit[] = ["m", "p", "s"];

function faceSuit(face: TileFace): FaceSuit {
    return SUITS_BUT_HONORS.find((suit) => face.endsWith(suit)) ?? "z";
}

function inBodyUnits(share: number): string {
    return String(Math.round(share * BODY_VIEW_WIDTH * 10_000) / 10_000);
}

function viewBoxOf({ height, left, top, width }: FaceBox): string {
    return [left, top, width, height]
        .map((length) => Math.round(length * 10_000) / 10_000)
        .join(" ");
}

interface TileLayout {
    readonly end?: StandingBackEnd;
    readonly joined?: boolean;
    readonly lay?: TileLay;
    readonly sideways?: boolean;
    readonly turn?: SeatTurn;
}

interface TileOptions extends TileLayout {
    readonly labels?: WindScript | null;
}

function bodyOf(material: "back" | "face", layout: TileLayout): TileBody {
    return tileBody({
        end: layout.end ?? "shown",
        joined: layout.joined === true,
        lay: layout.lay ?? "lying",
        material,
        sideways: layout.sideways === true,
        turn: layout.turn ?? 0,
    });
}

function bodyStyle(body: TileBody, layout: TileLayout): string {
    return [
        `--body-across: ${roundShare(body.across)}`,
        `--body-top: ${roundShare(body.top)}`,
        `--body-down: ${roundShare(body.top + body.edge)}`,
        `--body-turn: ${-(layout.turn ?? 0)}deg`,
        slotStyle(body.slot),
    ].join("; ");
}

function slotStyle({ across, down }: TileSlot): string {
    return `--slot-across-share: ${roundShare(across)}; --slot-down-share: ${roundShare(down)}`;
}

function lyingSlotStyle(layout: TileLayout): string {
    return slotStyle(lyingSlot(layout.turn ?? 0));
}

function roundShare(share: number): string {
    return String(Math.round(share * 10_000) / 10_000);
}

const ART_TURNS: Readonly<Record<SeatTurn, (view: FaceBox) => string>> = {
    0: () => "",
    180: ({ height, left, top, width }) => `rotate(180 ${left + width / 2} ${top + height / 2})`,
    270: ({ left, top, width }) => `translate(0 ${width}) rotate(-90) translate(${-left} ${-top})`,
    90: ({ height, left, top }) => `translate(${height} 0) rotate(90) translate(${-left} ${-top})`,
};

function artViewBox(view: FaceBox, turn: SeatTurn): FaceBox {
    if (turn % 180 === 0) {
        return view;
    }
    return { height: view.width, left: 0, top: 0, width: view.height };
}

interface FaceSpreadFrame {
    readonly across: number;
    readonly down: number;
    readonly surface: FaceBox;
    readonly turn: SeatTurn;
}

interface LabelRoom {
    readonly right: number;
    readonly top: number;
}

interface FaceSpread {
    readonly labelRoom: LabelRoom;
    readonly viewBox: FaceBox;
}

/**
 * Widen the face's viewport from its art box to the whole body at the same art scale, so nothing drawn past the art
 * box is clipped by it, and measure the face surface's room past the art box's top and right in the art's own frame.
 */
function spreadFaceOverBody(box: FaceBox, art: FaceBox, frame: FaceSpreadFrame): FaceSpread {
    const perAcross = art.width / box.width;
    const perDown = art.height / box.height;
    const { surface } = frame;
    const room = {
        bottom: (surface.top + surface.height - box.top - box.height) * perDown,
        left: (box.left - surface.left) * perAcross,
        right: (surface.left + surface.width - box.left - box.width) * perAcross,
        top: (box.top - surface.top) * perDown,
    };
    return {
        labelRoom: LABEL_ROOM_BY_TURN[frame.turn](room),
        viewBox: {
            height: frame.down * perDown,
            left: art.left - box.left * perAcross,
            top: art.top - box.top * perDown,
            width: frame.across * perAcross,
        },
    };
}

type SurfaceRoom = Readonly<Record<"bottom" | "left" | "right" | "top", number>>;

const LABEL_ROOM_BY_TURN: Readonly<Record<SeatTurn, (room: SurfaceRoom) => LabelRoom>> = {
    0: ({ right, top }) => ({ right, top }),
    180: ({ bottom, left }) => ({ right: left, top: bottom }),
    270: ({ left, top }) => ({ right: top, top: left }),
    90: ({ bottom, right }) => ({ right: bottom, top: right }),
};

interface FaceLabelling {
    readonly labels: WindScript | null;
    readonly room: LabelRoom;
}

function FaceArt(face: TileFace, view: FaceBox, { labels, room }: FaceLabelling) {
    const red = face.startsWith("0") ? " tile__name--red" : "";
    const onRedArt = face.startsWith("0") || face === RED_DRAGON;
    const label = labels === null ? null : tileLabel(face, labels);
    const labelMark =
        label === null
            ? nothing
            : svg`<text class="tile__label${onRedArt ? " tile__label--on-red-art" : ""}" x="${view.left + view.width + room.right - FACE_LABEL_INSET.right}" y="${view.top - room.top + FACE_LABEL_INSET.baseline}" aria-hidden="true">${label}</text>`;
    return svg`<g class="tile__art"><text class="tile__name${red}" x="150" y="200" aria-hidden="true">${placeholderFace(face)}</text><use href="#tile-${face}" width="${FACE_ART_VIEW.width}" height="${FACE_ART_VIEW.height}"/></g>${labelMark}`;
}

function StandingTile(face: TileFace, labels: WindScript | null = pageTileLabels()) {
    const box = standingFaceBox();
    const view = faceArtViewBox(faceSuit(face));
    const spread = spreadFaceOverBody(box, view, {
        across: 1,
        down: STANDING_BODY.height,
        surface: {
            height: STANDING_BODY.footStart - STANDING_BODY.frontStart,
            left: 0,
            top: STANDING_BODY.frontStart,
            width: 1,
        },
        turn: 0,
    });
    return html`<span class="tile tile--standing">${svg`<svg viewBox="0 0 ${BODY_VIEW_WIDTH} ${BODY_VIEW_HEIGHT}" aria-label="${spokenTileName(face)}"><use href="#body-standing" width="${BODY_VIEW_WIDTH}" height="${BODY_VIEW_HEIGHT}"/><svg class="tile__face" x="0" y="0" width="${BODY_VIEW_WIDTH}" height="${BODY_VIEW_HEIGHT}" viewBox="${viewBoxOf(spread.viewBox)}" preserveAspectRatio="none">${FaceArt(face, view, { labels, room: spread.labelRoom })}</svg></svg>`}</span>`;
}

export { StandingTile, Tile, TileBack, injectTileBodies, injectTileSprite, lyingSlotStyle };
export type { TileLayout, TileOptions };
