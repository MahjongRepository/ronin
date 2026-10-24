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

function storybookHandView(): TemplateResult {
    return html`
        <div class="storybook">
            ${storybookNav("/play/storybook/hand")}

            <section>
                <h2>Face Up Hand</h2>
                <div class="storybook-meld-row">
                    ${Hand(makeTiles(THIRTEEN_FACES, "face"))}
                </div>
            </section>

            <section>
                <h2>Face Down Hand</h2>
                <div class="storybook-meld-row">
                    ${Hand(makeTiles(THIRTEEN_FACES, "back"))}
                </div>
            </section>

            <section>
                <h2>Hand with Drawn Tile</h2>
                <div class="storybook-meld-row">
                    ${Hand(makeTiles(THIRTEEN_FACES, "face"), {
                        face: "5p",
                        show: "face",
                    })}
                </div>
            </section>

            <section>
                <h2>Small Hand</h2>
                <div class="storybook-meld-row">
                    ${Hand(makeTiles(["1m", "2m", "3m", "5p"], "face"), {
                        face: "5p",
                        show: "face",
                    })}
                </div>
            </section>
        </div>
    `;
}

export { storybookHandView };
