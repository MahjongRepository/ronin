import { TILE_BACK, TILE_HEIGHT, TILE_WIDTH } from "@/tile-config";
import { html, svg } from "lit-html";
import type { TileName } from "@/tile-utils";
import backSvgRaw from "@/assets/tiles/backs/classic-yellow.svg?raw";
import sprite from "@/assets/tiles/sprites/fluffy-stuff.svg?raw";

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

/** Render the full back SVG image (wall tiles, face-down stacks). */
function TileBack() {
    return html`<span class="tile tile-back" aria-label="back"
      style="display:inline-block;width:${TILE_WIDTH}px;height:${TILE_HEIGHT}px"
      .innerHTML=${backSvg}></span>`;
}

/** Render a solid color rectangle for the tile back (other players' hand peek). */
function TileBackColor() {
    return html`<span class="tile tile-back-color" aria-label="back"
      style="display:inline-block;width:${TILE_WIDTH}px;height:${TILE_HEIGHT}px;background:${TILE_BACK.color}"></span>`;
}

/**
 * Render a mahjong tile by name.
 *
 * Face tiles ("1m", "5p", "7z", etc.) reference the sprite.
 * "back" renders the full back SVG image.
 */
function Tile(name: TileName) {
    if (name === "back") {
        return TileBack();
    }
    injectSprite();
    return html`<span class="tile" style="display:inline-block;width:${TILE_WIDTH}px;height:${TILE_HEIGHT}px">${svg`<svg width="${TILE_WIDTH}" height="${TILE_HEIGHT}" viewBox="0 0 300 400" aria-label="${name}"><use href="#tile-${name}"/></svg>`}</span>`;
}

export { Tile, TileBack, TileBackColor, injectSprite };
