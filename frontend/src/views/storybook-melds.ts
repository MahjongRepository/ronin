import { type TemplateResult, html } from "lit-html";

import { Meld, type MeldTileDisplay, type TileFace } from "@/entities/tile";
import { storybookNav } from "@/views/storybook-nav";

type Direction = "left" | "across" | "right";

function directionToIndex(from: Direction, rightIdx = 2): number {
    if (from === "left") {
        return 0;
    }
    if (from === "across") {
        return 1;
    }
    return rightIdx;
}

function chiTiles(): MeldTileDisplay[] {
    return [
        { face: "2m", kind: "sideways" },
        { face: "3m", kind: "upright" },
        { face: "4m", kind: "upright" },
    ];
}

function ponTiles(from: Direction): MeldTileDisplay[] {
    const faces: TileFace[] = ["0p", "5p", "5p"];
    const sidewaysIdx = directionToIndex(from);
    return faces.map((face, i) =>
        i === sidewaysIdx
            ? { face, kind: "sideways" as const }
            : { face, kind: "upright" as const },
    );
}

function openKanTiles(from: Direction): MeldTileDisplay[] {
    const faces: TileFace[] = ["7z", "7z", "7z", "7z"];
    const sidewaysIdx = directionToIndex(from, 3);
    return faces.map((face, i) =>
        i === sidewaysIdx
            ? { face, kind: "sideways" as const }
            : { face, kind: "upright" as const },
    );
}

function closedKanTiles(): MeldTileDisplay[] {
    return [
        { face: "1z", kind: "facedown" },
        { face: "1z", kind: "upright" },
        { face: "1z", kind: "upright" },
        { face: "1z", kind: "facedown" },
    ];
}

function addedKanTiles(from: Direction): MeldTileDisplay[] {
    const stackedIdx = directionToIndex(from);
    const tiles: MeldTileDisplay[] = [];
    for (let i = 0; i < 3; i++) {
        if (i === stackedIdx) {
            tiles.push({ bottom: "6s", kind: "stacked", top: "6s" });
        } else {
            tiles.push({ face: "6s", kind: "upright" });
        }
    }
    return tiles;
}

function storybookMeldsView(): TemplateResult {
    return html`
        <div class="storybook">
            ${storybookNav("/play/storybook/melds")}

            <section>
                <h2>Chi (チー)</h2>
                <div class="storybook-meld-row">
                    ${Meld(chiTiles())}
                </div>
            </section>

            <section>
                <h2>Pon (ポン)</h2>
                <div class="storybook-meld-row">
                    ${Meld(ponTiles("left"))}
                    ${Meld(ponTiles("across"))}
                    ${Meld(ponTiles("right"))}
                </div>
            </section>

            <section>
                <h2>Open Kan (大明槓)</h2>
                <div class="storybook-meld-row">
                    ${Meld(openKanTiles("left"))}
                    ${Meld(openKanTiles("across"))}
                    ${Meld(openKanTiles("right"))}
                </div>
            </section>

            <section>
                <h2>Closed Kan (暗槓)</h2>
                <div class="storybook-meld-row">
                    ${Meld(closedKanTiles())}
                </div>
            </section>

            <section>
                <h2>Added Kan (加槓)</h2>
                <div class="storybook-meld-row">
                    ${Meld(addedKanTiles("left"))}
                    ${Meld(addedKanTiles("across"))}
                    ${Meld(addedKanTiles("right"))}
                </div>
            </section>
        </div>
    `;
}

export { storybookMeldsView };
