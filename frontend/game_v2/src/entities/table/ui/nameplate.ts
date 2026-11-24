import { type TemplateResult, html } from "lit-html";

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
 * score, its riichi, why its player is away, and where pressing it views from its seat, that.
 */
function nameplateLabel({ onView, plate, position }: NameplateProps): string {
    const seat = plate.isDealer
        ? t("game.nameplate.dealer", { wind: plate.windName })
        : plate.windName;
    const marks = [
        plate.isCurrent ? t("game.nameplate.to_play") : null,
        t("game.result.points", { count: Number(plate.score) }),
        plate.isRiichi ? t("game.nameplate.riichi") : null,
        plate.away,
        onView === null ? null : viewWords(position),
    ].filter((mark) => mark !== null);
    return [plate.name, seat, ...marks].join(t("list.separator"));
}

/** Where pressing a plate views from its seat: the bottom plate's is the seat viewed from, any other's is a choice. */
function viewWords(position: SeatPosition): string {
    return t(position === "bottom" ? "game.nameplate.viewing" : "game.nameplate.view");
}

/**
 * A seat's badge: its player's name alone, its states each on its own channel so any of them combine: the
 * name's ink red while its player is away (the reason in its title and label), a rim in the riichi stick's ivory after
 * a riichi, a bar along its bottom edge whose turn it is. Its score is the centre's, on the seat's side, which shows
 * the other seats' scores as differences from its own while a pointer hovers the badge. Where pressing it views the
 * table from its seat (a replay's), it is a button; a live game's badge takes no press.
 */
function Nameplate(props: NameplateProps): TemplateResult {
    const { onView, plate, position } = props;
    const classes = [
        "nameplate",
        `nameplate--${position}`,
        plate.isCurrent ? "nameplate--current" : "",
        plate.isRiichi ? "nameplate--riichi" : "",
        plate.away === null ? "" : "nameplate--away",
    ]
        .filter(Boolean)
        .join(" ");
    const title =
        plate.away === null
            ? plate.name
            : t("game.nameplate.away_title", { name: plate.name, reason: plate.away });
    const pill = html`<span class="nameplate__pill"
        >${PlayerName(plate.name, "nameplate__name")}<span class="nameplate__stick"
            >${RiichiStickIcon("across")}</span
        ></span
    >`;
    if (onView === null) {
        return html`<div class=${classes} role="group" title=${title} aria-label=${nameplateLabel(props)}>
            ${pill}
        </div>`;
    }
    return html`<button
        type="button"
        class=${classes}
        title=${title}
        aria-label=${nameplateLabel(props)}
        @click=${() => onView(position)}
    >
        ${pill}
    </button>`;
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
