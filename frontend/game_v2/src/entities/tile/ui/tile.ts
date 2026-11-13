import { html, nothing, svg } from "lit-html";

import {
    BODY_VIEW_WIDTH,
    FACE_ART_VIEW,
    type FaceBox,
    type FaceSuit,
    STANDING_BODY,
    faceArtViewBox,
    standingFaceBox,
} from "@/entities/tile/lib/tile-body";
import { pageTileLabels, tileLabel } from "@/entities/tile/lib/tile-labels";
import { type TileFace, spokenTileName } from "@/entities/tile/lib/tile-utils";
import { type WindScript, t } from "@/shared/i18n";

const HONOR_FACES = ["東", "南", "西", "北", "白", "發", "中"] as const;

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

/** Render the back of a tile, a hidden tile or one whose face the view does not know: the stylesheet draws it whole. */
function TileBack() {
    return html`<span class="tile tile-back" aria-label=${t("tile.hidden")}></span>`;
}

/**
 * Render a mahjong tile with a face identity and a display mode.
 *
 * "face" renders the tile's face sprite over its short name, which the stylesheet hides once the sprite is in the
 * document, so a tile stays readable while the sprite loads or when it never does.
 * "back" renders the tile's back (the face identity is preserved but not visible).
 * `labels` is the script of the face's corner label, the page's setting unless given; null draws none.
 */
function Tile(face: TileFace, show: "face" | "back", labels: WindScript | null = pageTileLabels()) {
    if (show === "back") {
        return TileBack();
    }
    const red = face.startsWith("0") ? " tile__name--red" : "";
    const label = labels === null ? null : tileLabel(face, labels);
    const labelMark =
        label === null
            ? nothing
            : svg`<text class="tile__label${red === "" ? "" : " tile__label--red"}" x="341" y="-47" aria-hidden="true">${label}</text>`;
    return html`<span class="tile">${svg`<svg width="100%" height="100%" viewBox="0 0 300 400" aria-label="${spokenTileName(face)}"><text class="tile__name${red}" x="150" y="200" aria-hidden="true">${placeholderFace(face)}</text><use href="#tile-${face}"/>${labelMark}</svg>`}</span>`;
}

const BODY_VIEW_HEIGHT = BODY_VIEW_WIDTH * STANDING_BODY.height;
const FACE_LABEL_INSET = 10;
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

function StandingTile(face: TileFace, labels: WindScript | null = pageTileLabels()) {
    const red = face.startsWith("0") ? " tile__name--red" : "";
    const label = labels === null ? null : tileLabel(face, labels);
    const box = standingFaceBox();
    const view = faceArtViewBox(faceSuit(face));
    const labelMark =
        label === null
            ? nothing
            : svg`<text class="tile__label${red === "" ? "" : " tile__label--red"}" x="${view.left + view.width - FACE_LABEL_INSET}" y="${view.top + FACE_LABEL_INSET}" aria-hidden="true">${label}</text>`;
    return html`<span class="tile tile--standing">${svg`<svg viewBox="0 0 ${BODY_VIEW_WIDTH} ${BODY_VIEW_HEIGHT}" aria-label="${spokenTileName(face)}"><use href="#body-standing" width="${BODY_VIEW_WIDTH}" height="${BODY_VIEW_HEIGHT}"/><svg class="tile__face" x="${inBodyUnits(box.left)}" y="${inBodyUnits(box.top)}" width="${inBodyUnits(box.width)}" height="${inBodyUnits(box.height)}" viewBox="${viewBoxOf(view)}" preserveAspectRatio="none"><g class="tile__art"><text class="tile__name${red}" x="150" y="200" aria-hidden="true">${placeholderFace(face)}</text><use href="#tile-${face}" width="${FACE_ART_VIEW.width}" height="${FACE_ART_VIEW.height}"/></g>${labelMark}</svg></svg>`}</span>`;
}

export { StandingTile, Tile, TileBack, injectTileBodies, injectTileSprite };
