import { type TemplateResult, html } from "lit-html";

import { TILE_FACES, TILE_FACES_SET, Tile, type TileFace } from "@/entities/tile";
import { type WindScript } from "@/shared/i18n";
import { STORYBOOK_INDEX, storybookNav } from "@/views/storybook-nav";

const HONOR_FACES: readonly TileFace[] = ["1z", "2z", "3z", "4z", "5z", "6z", "7z"];

function tileRow(faces: readonly TileFace[], labels: WindScript | null): TemplateResult {
    return html`<div class="storybook-tile-row">
        ${faces.map(
            (id) => html`
                <div class="storybook-tile-cell">
                    ${Tile(id, "face", labels)}
                    <small>${id}</small>
                </div>
            `,
        )}
    </div>`;
}

function storybookTilesView(): TemplateResult {
    return html`
        <div class="storybook">
            ${storybookNav(STORYBOOK_INDEX)}

            <section>
                <h2>"${TILE_FACES_SET}" tiles set</h2>
                ${tileRow(TILE_FACES, null)}
            </section>

            <section>
                <h2>Corner indices</h2>
                ${tileRow(TILE_FACES, "latin")}
                <h3>Honors: cyrillic</h3>
                ${tileRow(HONOR_FACES, "cyrillic")}
            </section>

            <section>
                <h2>Back tiles</h2>
                <h3>Classic Yellow</h3>
                <div class="storybook-tile-row">
                    <div class="storybook-tile-cell">
                        ${Tile("1m", "back")}
                        <small>image</small>
                    </div>
                </div>
            </section>
        </div>
    `;
}

export { storybookTilesView };
