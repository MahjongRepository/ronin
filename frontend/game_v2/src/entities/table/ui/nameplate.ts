import { type TemplateResult, html, nothing } from "lit-html";

import {
    type BoardNameplate,
    SEAT_POSITIONS,
    type SeatPosition,
} from "@/entities/table/model/board-types";

import { PlayerName } from "./player-name";
import { RiichiStickIcon } from "./riichi-stick-icon";

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
 * A seat's badge, one shape on every side: its wind (the dealer's marked), its player's name, then its AI and riichi
 * marks, quiet; whose turn it is underlines it. Its score is the centre's, on the seat's side. It is a button: pressing
 * it pins it, so the centre shows the other seats' scores as differences from its own, and pressing it again unpins
 * it; its label reads the score, or the difference from the pinned badge.
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
        <span class="nameplate__pill">
            <span class="nameplate__wind">${plate.wind}</span>
            ${PlayerName(plate.name, "nameplate__name")}
            ${
                aiMark === null
                    ? nothing
                    : html`<span class="nameplate__ai nameplate__ai--${aiMark.tag.toLowerCase()}"
                          >${aiMark.tag}</span
                      >`
            }
            ${plate.isRiichi ? html`<span class="nameplate__riichi">${RiichiStickIcon()}</span>` : nothing}
        </span>
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
