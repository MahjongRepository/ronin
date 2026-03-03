import { type TemplateResult, html } from "lit-html";

import { Meld, type MeldInput } from "@/entities/tile";
import { storybookNav } from "@/views/storybook-nav";

type Direction = "left" | "across" | "right";

const FROM_SEAT_MAP: Record<Direction, number> = { across: 2, left: 1, right: 3 };

function chiMeld(): MeldInput {
    return {
        calledTileId: 4,
        callerSeat: 0,
        fromSeat: 3,
        meldType: "chi",
        tileIds: [4, 8, 12],
    };
}

function ponMeld(from: Direction): MeldInput {
    return {
        calledTileId: 54,
        callerSeat: 0,
        fromSeat: FROM_SEAT_MAP[from],
        meldType: "pon",
        tileIds: [52, 53, 54],
    };
}

function openKanMeld(from: Direction): MeldInput {
    return {
        calledTileId: 133,
        callerSeat: 0,
        fromSeat: FROM_SEAT_MAP[from],
        meldType: "open_kan",
        tileIds: [132, 133, 134, 135],
    };
}

function closedKanMeld(): MeldInput {
    return {
        calledTileId: null,
        callerSeat: 0,
        fromSeat: null,
        meldType: "closed_kan",
        tileIds: [108, 109, 110, 111],
    };
}

function addedKanMeld(from: Direction): MeldInput {
    return {
        addedTileId: 87,
        calledTileId: 86,
        callerSeat: 0,
        fromSeat: FROM_SEAT_MAP[from],
        meldType: "added_kan",
        tileIds: [84, 85, 86, 87],
    };
}

function storybookMeldsView(): TemplateResult {
    return html`
        <div class="storybook">
            ${storybookNav("/play/storybook/melds")}

            <section>
                <h2>Chi (チー)</h2>
                <div class="storybook-meld-row">
                    ${Meld(chiMeld())}
                </div>
            </section>

            <section>
                <h2>Pon (ポン)</h2>
                <div class="storybook-meld-row">
                    ${Meld(ponMeld("left"))}
                    ${Meld(ponMeld("across"))}
                    ${Meld(ponMeld("right"))}
                </div>
            </section>

            <section>
                <h2>Open Kan (大明槓)</h2>
                <div class="storybook-meld-row">
                    ${Meld(openKanMeld("left"))}
                    ${Meld(openKanMeld("across"))}
                    ${Meld(openKanMeld("right"))}
                </div>
            </section>

            <section>
                <h2>Closed Kan (暗槓)</h2>
                <div class="storybook-meld-row">
                    ${Meld(closedKanMeld())}
                </div>
            </section>

            <section>
                <h2>Added Kan (加槓)</h2>
                <div class="storybook-meld-row">
                    ${Meld(addedKanMeld("left"))}
                    ${Meld(addedKanMeld("across"))}
                    ${Meld(addedKanMeld("right"))}
                </div>
            </section>
        </div>
    `;
}

export { storybookMeldsView };
