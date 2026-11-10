import { type TemplateResult, html, nothing } from "lit-html";

import {
    type BoardNameplate,
    SEAT_POSITIONS,
    type SeatPosition,
} from "@/entities/table/model/board-types";
import { t } from "@/shared/i18n";

import { PlayerName } from "./player-name";
import { RiichiStickIcon } from "./riichi-stick-icon";

/** Views the table from a seat, where pressing its plate does (a replay's); a live game's plates take no press. */
type SeatView = (seat: SeatPosition) => void;

interface NameplateProps {
    readonly plate: BoardNameplate;
    readonly position: SeatPosition;
    readonly onView: SeatView | null;
}

/**
 * What a screen reader hears for a plate: its whole name, its seat's wind (shown in the centre), whose turn it is, its
 * score, why an AI player is marked, and where pressing it views from its seat, that.
 */
function nameplateLabel({ onView, plate, position }: NameplateProps): string {
    const seat = plate.isDealer
        ? t("game.nameplate.dealer", { wind: plate.windName })
        : plate.windName;
    const marks = [
        plate.isCurrent ? t("game.nameplate.to_play") : null,
        t("game.result.points", { count: Number(plate.score) }),
        plate.isRiichi ? t("game.nameplate.riichi") : null,
        plate.aiMark?.words ?? null,
        onView === null ? null : viewWords(position),
    ].filter((mark) => mark !== null);
    return [plate.name, seat, ...marks].join(t("list.separator"));
}

/** Where pressing a plate views from its seat: the bottom plate's is the seat viewed from, any other's is a choice. */
function viewWords(position: SeatPosition): string {
    return t(position === "bottom" ? "game.nameplate.viewing" : "game.nameplate.view");
}

/**
 * A seat's badge: its player's name, its AI and riichi marks quiet on a line under it (beside it on the own badge, whose
 * lane is wide and short); a bar along its bottom edge marks whose turn it is. Its score is the centre's, on
 * the seat's side, which shows the other seats' scores as differences from its own while a pointer hovers the badge.
 * Where pressing it views the table from its seat (a replay's), it is a button; a live game's badge takes no press.
 */
function Nameplate(props: NameplateProps): TemplateResult {
    const { onView, plate, position } = props;
    const classes = [
        "nameplate",
        `nameplate--${position}`,
        plate.isCurrent ? "nameplate--current" : "",
    ]
        .filter(Boolean)
        .join(" ");
    const pill = html`<span class="nameplate__pill">${PlayerName(plate.name, "nameplate__name")}${NameplateMarks(plate)}</span>`;
    if (onView === null) {
        return html`<div class=${classes} role="group" title=${plate.name} aria-label=${nameplateLabel(props)}>
            ${pill}
        </div>`;
    }
    return html`<button
        type="button"
        class=${classes}
        title=${plate.name}
        aria-label=${nameplateLabel(props)}
        @click=${() => onView(position)}
    >
        ${pill}
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
                : html`<span class="nameplate__ai nameplate__ai--${aiMark.kind}">${aiMark.tag}</span>`
        }${isRiichi ? html`<span class="nameplate__riichi">${RiichiStickIcon("across")}</span>` : nothing}</span
    >`;
}

/** The four seats' nameplates, by board position, each viewing from its own seat where a press views from one. */
function Nameplates(
    plates: readonly [BoardNameplate, BoardNameplate, BoardNameplate, BoardNameplate],
    onView: SeatView | null,
): Readonly<Record<SeatPosition, TemplateResult>> {
    const [bottom, right, top, left] = SEAT_POSITIONS.map((position, index) =>
        Nameplate({ onView, plate: plates[index], position }),
    );
    return { bottom, left, right, top };
}

export { Nameplates };
export type { SeatView };
