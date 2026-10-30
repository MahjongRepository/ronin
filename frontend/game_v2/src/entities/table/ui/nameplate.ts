import { type TemplateResult, html, nothing } from "lit-html";

import {
    type BoardNameplate,
    SEAT_POSITIONS,
    type SeatPosition,
} from "@/entities/table/model/board-types";

import { PlayerName } from "./player-name";

/**
 * The plate whose score the other plates show their differences from, pinned by a tap or a press, and where a pin
 * or an unpin goes. Hovering a plate shows the same differences without pinning it.
 */
interface ScoreDiffPin {
    readonly pinned: SeatPosition | null;
    readonly onPin: (seat: SeatPosition | null) => void;
}

interface NameplateProps {
    readonly plate: BoardNameplate;
    readonly position: SeatPosition;
    /** The pinned plate, when another one is: this plate's label then reads its difference from it. */
    readonly pinnedOther: { readonly position: SeatPosition; readonly name: string } | null;
    readonly pressed: boolean;
    readonly onToggle: () => void;
}

/** A robot's head: an AI player plays the seat. */
function RobotIcon(): TemplateResult {
    return html`<svg
        viewBox="0 0 16 16"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        stroke-linejoin="round"
    >
        <rect x="2.5" y="5" width="11" height="8.5" rx="2" />
        <path d="M8 5V2.5M6 9.5h0M10 9.5h0" />
    </svg>`;
}

/** A struck-through plug: the seat's human is away, and an AI player holds the seat for them. */
function UnpluggedIcon(): TemplateResult {
    return html`<svg
        viewBox="0 0 16 16"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        stroke-linejoin="round"
    >
        <path d="M6 1.5v3M10 1.5v3M4.5 4.5h7v2.5a3.5 3.5 0 0 1-7 0zM8 10.5v4" />
        <path d="M2 14 14 2" />
    </svg>`;
}

/**
 * What a screen reader hears for a plate: what it shows, its whole name, whose turn it is, the difference from the
 * pinned plate in place of the score, and why an AI player is marked.
 */
function nameplateLabel({ pinnedOther, plate }: NameplateProps): string {
    const seat = plate.isDealer ? `${plate.windName}, dealer` : plate.windName;
    const points =
        pinnedOther === null
            ? `${plate.score} points`
            : `${plate.scoreDiffs[pinnedOther.position]} from ${pinnedOther.name}`;
    const marks = [
        plate.isCurrent ? "to play" : null,
        points,
        plate.isRiichi ? "riichi" : null,
        plate.aiMark?.words ?? null,
    ].filter((mark) => mark !== null);
    return [plate.name, seat, ...marks].join(", ");
}

/**
 * A seat's nameplate, one shape on every side: its wind (the dealer's marked), its player's name, then its AI and
 * riichi marks; whose turn it is lights it up. Its score is the centre's, on the seat's side. It is a button: pressing
 * it pins it, so the centre shows the other seats' scores as differences from its own, and pressing it again unpins
 * it; its label reads the score, or the difference from the pinned plate.
 */
function Nameplate(props: NameplateProps): TemplateResult {
    const { onToggle, plate, position, pressed } = props;
    const classes = [
        "nameplate",
        `nameplate--${position}`,
        plate.isCurrent ? "nameplate--current" : "",
        plate.isDealer ? "nameplate--dealer" : "",
    ]
        .filter(Boolean)
        .join(" ");
    const { aiMark } = plate;
    return html`<button
        type="button"
        class=${classes}
        title=${plate.name}
        aria-label=${nameplateLabel(props)}
        aria-pressed=${String(pressed)}
        @click=${onToggle}
    >
        <span class="nameplate__wind">${plate.wind}</span>
        ${PlayerName(plate.name, "nameplate__name")}
        ${
            aiMark === null
                ? nothing
                : html`<span class="nameplate__ai nameplate__ai--${aiMark.tag.toLowerCase()}"
                      >${aiMark.tag === "Away" ? UnpluggedIcon() : RobotIcon()}</span
                  >`
        }
        ${plate.isRiichi ? html`<span class="nameplate__riichi">Riichi</span>` : nothing}
    </button>`;
}

/** The four seats' nameplates, by board position, each pinning itself or, pinned already, unpinning. */
function Nameplates(
    plates: readonly [BoardNameplate, BoardNameplate, BoardNameplate, BoardNameplate],
    pin: ScoreDiffPin,
): Readonly<Record<SeatPosition, TemplateResult>> {
    const pinnedIndex = pin.pinned === null ? -1 : SEAT_POSITIONS.indexOf(pin.pinned);
    const pinnedPlate = plates[pinnedIndex];
    const [bottom, right, top, left] = SEAT_POSITIONS.map((position, index) => {
        const pressed = pin.pinned === position;
        const pinnedOther =
            pin.pinned === null || pressed || pinnedPlate === undefined
                ? null
                : { name: pinnedPlate.name, position: pin.pinned };
        return Nameplate({
            onToggle: () => pin.onPin(pressed ? null : position),
            pinnedOther,
            plate: plates[index],
            position,
            pressed,
        });
    });
    return { bottom, left, right, top };
}

export { Nameplates };
export type { ScoreDiffPin };
