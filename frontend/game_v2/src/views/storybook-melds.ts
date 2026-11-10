import { type TemplateResult, html } from "lit-html";

import {
    FIVE_RED_MAN,
    FIVE_RED_PIN,
    FIVE_RED_SOU,
    Meld,
    type MeldInput,
    meldTiles,
} from "@/entities/tile";
import { storybookNav } from "@/views/storybook-nav";

type Direction = "left" | "across" | "right";

const FROM_SEAT_MAP: Record<Direction, number> = { across: 2, left: 3, right: 1 };

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

function closedKanAkaMeld(tileIds: readonly number[]): MeldInput {
    return { calledTileId: null, callerSeat: 0, fromSeat: null, meldType: "closed_kan", tileIds };
}

const CLOSED_KAN_AKA_TILE_IDS: readonly (readonly number[])[] = [
    [FIVE_RED_MAN, 17, 18, 19],
    [53, 54, 55, FIVE_RED_PIN],
    [89, FIVE_RED_SOU, 90, 91],
];

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

type AkaRole = "called" | "hand" | "added";

const ADDED_KAN_AKA_IDS: Record<AkaRole, { calledTileId: number; addedTileId: number }> = {
    added: { addedTileId: FIVE_RED_PIN, calledTileId: 54 },
    called: { addedTileId: 55, calledTileId: FIVE_RED_PIN },
    hand: { addedTileId: 55, calledTileId: 54 },
};

function addedKanAkaMeld(role: AkaRole, from: Direction): MeldInput {
    return {
        ...ADDED_KAN_AKA_IDS[role],
        callerSeat: 0,
        fromSeat: FROM_SEAT_MAP[from],
        meldType: "added_kan",
        tileIds: [FIVE_RED_PIN, 53, 54, 55],
    };
}

function meldRow(label: string, melds: MeldInput[]): TemplateResult {
    return html`
        <h2 class="storybook-melds__label">${label}</h2>
        <div class="storybook-melds__row">${melds.map((meld) => Meld(meldTiles(meld)))}</div>
    `;
}

const DIRECTIONS: Direction[] = ["left", "across", "right"];

function storybookMeldsView(): TemplateResult {
    return html`
        <div class="storybook">
            ${storybookNav("/play/storybook/melds")}
            <div class="storybook-melds">
                ${meldRow("Chi", [chiMeld()])}
                ${meldRow("Pon", DIRECTIONS.map(ponMeld))}
                ${meldRow("Open Kan", DIRECTIONS.map(openKanMeld))}
                ${meldRow("Closed Kan", [closedKanMeld()])}
                ${meldRow("Closed Kan, aka 5", CLOSED_KAN_AKA_TILE_IDS.map(closedKanAkaMeld))}
                ${meldRow("Added Kan", DIRECTIONS.map(addedKanMeld))}
                ${meldRow(
                    "Added Kan, aka 5 called",
                    DIRECTIONS.map((from) => addedKanAkaMeld("called", from)),
                )}
                ${meldRow(
                    "Added Kan, aka 5 from hand",
                    DIRECTIONS.map((from) => addedKanAkaMeld("hand", from)),
                )}
                ${meldRow(
                    "Added Kan, aka 5 added",
                    DIRECTIONS.map((from) => addedKanAkaMeld("added", from)),
                )}
            </div>
        </div>
    `;
}

export { storybookMeldsView };
