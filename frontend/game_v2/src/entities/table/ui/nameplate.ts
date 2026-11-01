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
    readonly kind: "pin";
    readonly pinned: SeatPosition | null;
    readonly onPin: (seat: SeatPosition | null) => void;
}

/** A replay's plates and centre scores: pressing another seat's views the table from it; hovering still diffs. */
interface SeatViewPress {
    readonly kind: "view";
    readonly onView: (seat: SeatPosition) => void;
}

/** What pressing a plate does: pin its score differences, or view the table from its seat. */
type PlatePress = ScoreDiffPin | SeatViewPress;

/** The plate pinned for the others' score differences, or null: always null where a press views from a seat. */
function pinnedPlate(press: PlatePress): SeatPosition | null {
    return press.kind === "pin" ? press.pinned : null;
}

interface NameplateProps {
    readonly plate: BoardNameplate;
    readonly position: SeatPosition;
    /** The pinned plate, when another one is: this plate's label then reads its difference from it. */
    readonly pinnedOther: { readonly position: SeatPosition; readonly name: string } | null;
    /** Whether the plate is pinned, or null where pressing it views from its seat, which is no toggle. */
    readonly pressed: boolean | null;
    readonly onToggle: () => void;
}

/**
 * What a screen reader hears for a plate: its whole name, its seat's wind (shown in the centre), whose turn it is, the
 * difference from the pinned plate in place of the score, why an AI player is marked, and where pressing it views from its seat, that.
 */
function nameplateLabel({ pinnedOther, plate, position, pressed }: NameplateProps): string {
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
        viewWords(position, pressed),
    ].filter((mark) => mark !== null);
    return [plate.name, seat, ...marks].join(", ");
}

/** Where pressing a plate views from its seat: the bottom plate's is the seat viewed from, any other's is a choice. */
function viewWords(position: SeatPosition, pressed: boolean | null): string | null {
    if (pressed !== null) {
        return null;
    }
    return position === "bottom" ? "viewing from this seat" : "view from this seat";
}

/**
 * A seat's badge: its player's name, its AI and riichi marks quiet on a line under it (beside it on the own badge, whose
 * lane is wide and short); a bar along its bottom edge marks whose turn it is. Its score is the centre's, on
 * the seat's side. It is a button: pressing it pins it, so the centre shows the other seats' scores as differences from
 * its own, and pressing it again unpins it, or on a replay views the table from its seat; its label reads the score, or
 * the difference from the pinned badge.
 */
function Nameplate(props: NameplateProps): TemplateResult {
    const { onToggle, plate, position, pressed } = props;
    const classes = [
        "nameplate",
        `nameplate--${position}`,
        plate.isCurrent ? "nameplate--current" : "",
    ]
        .filter(Boolean)
        .join(" ");
    return html`<button
        type="button"
        class=${classes}
        title=${plate.name}
        aria-label=${nameplateLabel(props)}
        aria-pressed=${pressed === null ? nothing : String(pressed)}
        @click=${onToggle}
    >
        <span class="nameplate__pill">${PlayerName(plate.name, "nameplate__name")}${NameplateMarks(plate)}</span>
    </button>`;
}

/**
 * A plate's quiet marks, AI or Away and riichi: on a line under the name, so the name keeps the plate's width, or
 * beside it on the own plate.
 */
function NameplateMarks({ aiMark, isRiichi }: BoardNameplate): TemplateResult | typeof nothing {
    if (aiMark === null && !isRiichi) {
        return nothing;
    }
    return html`<span class="nameplate__marks"
        >${
            aiMark === null
                ? nothing
                : html`<span class="nameplate__ai nameplate__ai--${aiMark.tag.toLowerCase()}">${aiMark.tag}</span>`
        }${isRiichi ? html`<span class="nameplate__riichi">${RiichiStickIcon("across")}</span>` : nothing}</span
    >`;
}

/**
 * The four seats' nameplates, by board position, each pinning itself or, pinned already, unpinning; or, where a press
 * views from a seat, each viewing from its own.
 */
function Nameplates(
    plates: readonly [BoardNameplate, BoardNameplate, BoardNameplate, BoardNameplate],
    press: PlatePress,
): Readonly<Record<SeatPosition, TemplateResult>> {
    if (press.kind === "view") {
        const [bottom, right, top, left] = SEAT_POSITIONS.map((position, index) =>
            Nameplate({
                onToggle: () => press.onView(position),
                pinnedOther: null,
                plate: plates[index],
                position,
                pressed: null,
            }),
        );
        return { bottom, left, right, top };
    }
    const { pinned } = press;
    const pinnedIndex = pinned === null ? -1 : SEAT_POSITIONS.indexOf(pinned);
    const pinnedBadge = plates[pinnedIndex];
    const [bottom, right, top, left] = SEAT_POSITIONS.map((position, index) => {
        const pressed = pinned === position;
        const pinnedOther =
            pinned === null || pressed || pinnedBadge === undefined
                ? null
                : { name: pinnedBadge.name, position: pinned };
        return Nameplate({
            onToggle: () => press.onPin(pressed ? null : position),
            pinnedOther,
            plate: plates[index],
            position,
            pressed,
        });
    });
    return { bottom, left, right, top };
}

export { Nameplates, pinnedPlate };
export type { PlatePress, ScoreDiffPin, SeatViewPress };
