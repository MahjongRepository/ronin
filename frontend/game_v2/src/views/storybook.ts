import { type TemplateResult, html } from "lit-html";

import { TILE_FACES, TILE_FACES_SET, Tile, type TileFace } from "@/entities/tile";
import { storybookNav } from "@/views/storybook-nav";

function storybookView(): TemplateResult {
    return html`
        <div class="storybook">
            ${storybookNav("/play/storybook")}

            <!-- Tile faces -->
            <section>
                <h2>"${TILE_FACES_SET}" tiles set</h2>
                <div class="storybook-tile-row">
                    ${TILE_FACES.map(
                        (id) => html`
                            <div class="storybook-tile-cell">
                                ${Tile(id as TileFace, "face")}
                                <small>${id}</small>
                            </div>
                        `,
                    )}
                </div>
            </section>

            <!-- Back tiles -->
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

            <!-- Connection status indicators -->
            <section>
                <h2>Connection Status Indicators</h2>
                <div style="display:flex;gap:1rem;flex-wrap:wrap;">
                    ${["connected", "connecting", "disconnected", "error"].map(
                        (s) => html`
                            <div>
                                <p><small>${s}</small></p>
                                <span class="connection-status status-${s}"
                                    >${s}</span
                                >
                            </div>
                        `,
                    )}
                </div>
            </section>
        </div>
    `;
}

export { storybookView };
