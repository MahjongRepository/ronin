import { type TemplateResult, html } from "lit-html";

import { TILE_FACES, TILE_FACES_SET, Tile } from "@/entities/tile";
import { STORYBOOK_INDEX, storybookNav } from "@/views/storybook-nav";

function storybookTilesView(): TemplateResult {
    return html`
        <div class="storybook">
            ${storybookNav(STORYBOOK_INDEX)}

            <section>
                <h2>"${TILE_FACES_SET}" tiles set</h2>
                <div class="storybook-tile-row">
                    ${TILE_FACES.map(
                        (id) => html`
                            <div class="storybook-tile-cell">
                                ${Tile(id, "face")}
                                <small>${id}</small>
                            </div>
                        `,
                    )}
                </div>
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
