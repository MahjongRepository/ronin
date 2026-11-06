import { type TemplateResult, html } from "lit-html";

import { Hand, type HandTile, type TileFace } from "@/entities/tile";
import { storybookNav } from "@/views/storybook-nav";

function makeTiles(faces: TileFace[], show: "face" | "back"): HandTile[] {
    return faces.map((face) => ({ face, show }));
}

const THIRTEEN_FACES: TileFace[] = [
    "1m",
    "2m",
    "3m",
    "4m",
    "5m",
    "6m",
    "7m",
    "8m",
    "9m",
    "1p",
    "2p",
    "3p",
    "4p",
];

/** A turn's hand: the tiles kuikae blocks disabled, the rest selectable, and one tile its answer played selected. */
const PLAYED_TILES: readonly HandTile[] = THIRTEEN_FACES.map((face, index) => {
    const tileId = index * 4;
    if (index === 6) {
        return { face, show: "face", state: "selected", tileId };
    }
    return { face, show: "face", state: index < 3 ? "disabled" : "selectable", tileId };
});

function storybookHandView(): TemplateResult {
    return html`
        <div class="storybook">
            ${storybookNav("/play/storybook/hand")}

            <section>
                <h2>Face Up Hand</h2>
                <div class="storybook-meld-row">
                    ${Hand({ tiles: makeTiles(THIRTEEN_FACES, "face") })}
                </div>
            </section>

            <section>
                <h2>Face Down Hand</h2>
                <div class="storybook-meld-row">
                    ${Hand({ tiles: makeTiles(THIRTEEN_FACES, "back") })}
                </div>
            </section>

            <section>
                <h2>Hand with Drawn Tile</h2>
                <div class="storybook-meld-row">
                    ${Hand({
                        drawnTile: { face: "5p", show: "face" },
                        tiles: makeTiles(THIRTEEN_FACES, "face"),
                    })}
                </div>
            </section>

            <section>
                <h2>Hand in Play (selectable, disabled, selected)</h2>
                <div class="storybook-meld-row">
                    ${Hand({ drawnTile: { face: "5p", show: "face", state: "selectable", tileId: 53 }, tileAction: "discard", tiles: PLAYED_TILES })}
                </div>
            </section>

            <section>
                <h2>Small Hand</h2>
                <div class="storybook-meld-row">
                    ${Hand({
                        drawnTile: { face: "5p", show: "face" },
                        tiles: makeTiles(["1m", "2m", "3m", "5p"], "face"),
                    })}
                </div>
            </section>
        </div>
    `;
}

export { storybookHandView };
