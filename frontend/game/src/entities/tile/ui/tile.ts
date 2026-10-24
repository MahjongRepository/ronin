import { html, svg } from "lit-html";

import backSvgRaw from "@/assets/tiles/backs/classic-yellow.svg?raw";
import sprite from "@/assets/tiles/sprites/fluffy-stuff.svg?raw";
import { type TileFace } from "@/entities/tile/lib/tile-utils";

// Strip fixed width/height so the SVG scales to its container via viewBox.
const backSvg = backSvgRaw.replace(/ width="\d+"/, "").replace(/ height="\d+"/, "");

let spriteInjected = false;

/**
 * Inject the tile sprite SVG into the document body.
 * Uses a static import -- the sprite string is available synchronously.
 * Safe to call multiple times; only injects once.
 */
function injectSprite(): void {
    if (spriteInjected) {
        return;
    }

    const container = document.createElement("div");
    container.innerHTML = sprite;
    container.style.display = "none";
    container.setAttribute("aria-hidden", "true");
    document.body.prepend(container);
    spriteInjected = true;
}

/**
 * Render a mahjong tile with a face identity and a display mode.
 *
 * "face" renders the tile's face sprite.
 * "back" renders the full back SVG image (the face identity is preserved but not visible).
 */
function Tile(face: TileFace, show: "face" | "back") {
    if (show === "back") {
        return html`<span class="tile tile-back" aria-label="back"
          .innerHTML=${backSvg}></span>`;
    }
    injectSprite();
    return html`<span class="tile">${svg`<svg width="100%" height="100%" viewBox="0 0 300 400" aria-label="${face}"><use href="#tile-${face}"/></svg>`}</span>`;
}

export { Tile, injectSprite };
