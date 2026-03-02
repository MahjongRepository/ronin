import { type TemplateResult, html } from "lit-html";

import { meldToDisplay } from "@/entities/table/lib/meld-display";
import { type PlayerState } from "@/entities/table/model/types";
import {
    type DiscardTile,
    Discards,
    Hand,
    type HandTile,
    Meld,
    tile136toString,
} from "@/entities/tile";

function formatScore(score: number): string {
    return score.toLocaleString("en-US");
}

function toHandTile(tileId: number): HandTile {
    return { face: tile136toString(tileId), show: "face" };
}

function separateDrawnTile(
    tiles: number[],
    drawnTileId: number,
): { baseTiles: HandTile[]; drawnTile: HandTile } {
    const baseTiles: HandTile[] = [];
    let drawnFiltered = false;
    let drawnTile: HandTile = toHandTile(drawnTileId);
    for (const tileId of tiles) {
        if (!drawnFiltered && tileId === drawnTileId) {
            drawnFiltered = true;
            drawnTile = toHandTile(tileId);
        } else {
            baseTiles.push(toHandTile(tileId));
        }
    }
    return { baseTiles, drawnTile };
}

function buildHandTiles(player: PlayerState): {
    baseTiles: HandTile[];
    drawnTile: HandTile | undefined;
} {
    if (player.drawnTileId !== null) {
        return separateDrawnTile(player.tiles, player.drawnTileId);
    }
    return { baseTiles: player.tiles.map(toHandTile), drawnTile: undefined };
}

function buildDiscardTiles(player: PlayerState): DiscardTile[] {
    return player.discards.map((d) => ({
        face: tile136toString(d.tileId),
        grayed: d.claimed,
        riichi: d.isRiichi,
    }));
}

/**
 * Render a single player panel showing name, score, hand, melds, and discards.
 * Filter out drawnTileId from base tiles to avoid duplicate rendering in the hand row.
 */
function PlayerPanel(player: PlayerState, isDealer: boolean, isCurrent: boolean): TemplateResult {
    const { baseTiles, drawnTile } = buildHandTiles(player);
    const discardTiles = buildDiscardTiles(player);
    const currentClass = isCurrent ? " player-panel--current" : "";

    return html`<div class="player-panel${currentClass}">
        <div class="player-panel__header">
            <span class="player-panel__name">${player.name}</span>
            <span class="player-panel__score">${formatScore(player.score)}</span>
            ${
                isDealer
                    ? html`
                          <span class="player-panel__badge player-panel__badge--dealer">Dealer</span>
                      `
                    : ""
            }
            ${
                player.isRiichi
                    ? html`
                          <span class="player-panel__badge player-panel__badge--riichi">Riichi</span>
                      `
                    : ""
            }
        </div>
        <div class="player-panel__hand">${Hand(baseTiles, drawnTile)}</div>
        ${
            player.melds.length > 0
                ? html`<div class="player-panel__melds">
                  ${player.melds.map((m) => Meld(meldToDisplay(m)))}
              </div>`
                : ""
        }
        <div class="player-panel__discards">${Discards(discardTiles)}</div>
    </div>`;
}

export { PlayerPanel };
