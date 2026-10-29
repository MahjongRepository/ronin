import { html, svg } from "lit-html";

import backSvgRaw from "@/assets/tiles/backs/classic-yellow.svg?raw";
import { type TileFace } from "@/entities/tile/lib/tile-utils";

// Strip fixed width/height so the SVG scales to its container via viewBox.
const backSvg = backSvgRaw.replace(/ width="\d+"/, "").replace(/ height="\d+"/, "");

const HONOR_NAMES = ["E", "S", "W", "N", "Wh", "Gr", "Rd"] as const;

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

/** A face's short name, which a tile shows until the sprite draws it: `5m`, a red five's `5m` too, `E`, `Rd`. */
function tileName(face: TileFace): string {
    const [rank, suit] = face;
    if (suit === "z") {
        return HONOR_NAMES[Number(rank) - 1];
    }
    return `${rank === "0" ? "5" : rank}${suit}`;
}

/** Render the back of a tile: a hidden tile, or one whose face the view does not know. */
function TileBack() {
    return html`<span class="tile tile-back" aria-label="back"
          .innerHTML=${backSvg}></span>`;
}

/**
 * Render a mahjong tile with a face identity and a display mode.
 *
 * "face" renders the tile's face sprite over its short name, which the stylesheet hides once the sprite is in the
 * document, so a tile stays readable while the sprite loads or when it never does.
 * "back" renders the full back SVG image (the face identity is preserved but not visible).
 */
function Tile(face: TileFace, show: "face" | "back") {
    if (show === "back") {
        return TileBack();
    }
    const red = face.startsWith("0") ? " tile__name--red" : "";
    return html`<span class="tile">${svg`<svg width="100%" height="100%" viewBox="0 0 300 400" aria-label="${face}"><text class="tile__name${red}" x="150" y="200" aria-hidden="true">${tileName(face)}</text><use href="#tile-${face}"/></svg>`}</span>`;
}

export { Tile, TileBack, injectTileSprite };
