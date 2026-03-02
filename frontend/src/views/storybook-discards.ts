import { type TemplateResult, html } from "lit-html";

import { type DiscardTile, Discards, type TileFace } from "@/entities/tile";
import { storybookNav } from "@/views/storybook-nav";

function makeTiles(faces: TileFace[]): DiscardTile[] {
    return faces.map((face) => ({ face }));
}

const SIX_FACES: TileFace[] = ["1m", "2m", "3m", "4m", "5m", "6m"];

const TWELVE_FACES: TileFace[] = [
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
];

const TWENTY_FACES: TileFace[] = [
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
    "5p",
    "6p",
    "7p",
    "8p",
    "9p",
    "1s",
    "2s",
];

function grayedTiles(): DiscardTile[] {
    return [
        { face: "1m" },
        { face: "3m", grayed: true },
        { face: "5m" },
        { face: "7m", grayed: true },
        { face: "9m" },
        { face: "2p", grayed: true },
    ];
}

function riichiTiles(): DiscardTile[] {
    return [
        { face: "1m" },
        { face: "3m" },
        { face: "5m" },
        { face: "7m" },
        { face: "9m" },
        { face: "2p", riichi: true },
        { face: "4p" },
        { face: "6p" },
    ];
}

function mixedTiles(): DiscardTile[] {
    return [
        { face: "1m" },
        { face: "4m" },
        { face: "9m", grayed: true },
        { face: "2p" },
        { face: "5p" },
        { face: "7p" },
        { face: "3s", riichi: true },
        { face: "6s" },
        { face: "8s" },
        { face: "1z", grayed: true },
        { face: "3z" },
        { face: "5z" },
        { face: "7z" },
    ];
}

function storybookDiscardsView(): TemplateResult {
    return html`
        <div class="storybook">
            ${storybookNav("/play/storybook/discards")}

            <section>
                <h2>Basic Discards (6 tiles)</h2>
                <div class="storybook-meld-row">
                    ${Discards(makeTiles(SIX_FACES))}
                </div>
            </section>

            <section>
                <h2>Two Rows (12 tiles)</h2>
                <div class="storybook-meld-row">
                    ${Discards(makeTiles(TWELVE_FACES))}
                </div>
            </section>

            <section>
                <h2>Overflow Row (20 tiles)</h2>
                <div class="storybook-meld-row">
                    ${Discards(makeTiles(TWENTY_FACES))}
                </div>
            </section>

            <section>
                <h2>Grayed Out Tiles</h2>
                <div class="storybook-meld-row">
                    ${Discards(grayedTiles())}
                </div>
            </section>

            <section>
                <h2>Riichi Tile</h2>
                <div class="storybook-meld-row">
                    ${Discards(riichiTiles())}
                </div>
            </section>

            <section>
                <h2>Mixed</h2>
                <div class="storybook-meld-row">
                    ${Discards(mixedTiles())}
                </div>
            </section>
        </div>
    `;
}

export { storybookDiscardsView };
