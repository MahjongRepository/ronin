import $ from "jquery";

import { SEAT_MARK, SEAT_MARK_TEXT } from "../../vendor/majiang-ui/board.js";
import { HISTORY_URL, isGameClientPath } from "../routes.js";
import { COARSE_POINTER_MEDIA } from "./media.js";
import { POSITION } from "./paipu.js";
import { SEATS } from "./seats.js";

/** The board's nameplates in turn order from the viewpoint's at the bottom, as majiang-ui places them. */
const NAMEPLATES = Object.freeze(["main", "xiajia", "duimian", "shangjia"]);

/** What a nameplate's title adds while an AI player holds its seat, the meaning of its mark's colour. */
const AI_TITLE = ` (${SEAT_MARK_TEXT[SEAT_MARK.AI]})`;

/**
 * Where the standings' exit leads: back to the lobby page the replay was opened from, else the game history. A page of
 * this client is never one to go back to: the finished game's page, which its standings' 牌譜を見る replaced, would
 * only bounce to the lobby.
 */
function exitUrl() {
    const referrer = document.referrer;
    if (referrer === "") {
        return HISTORY_URL;
    }
    const url = new URL(referrer);
    const isLobbyPage = url.origin === window.location.origin && !isGameClientPath(url.pathname);
    return isLobbyPage ? referrer : HISTORY_URL;
}

/** The exit's label names where it leads: the game history, or just back to another page. */
function exitLabel(url) {
    return new URL(url, window.location.origin).pathname.startsWith(HISTORY_URL)
        ? "履歴へ戻る"
        : "戻る";
}

/**
 * The links the replay adds to the board around the viewer: a nameplate views the table from its seat, each round of
 * the final standings shows that round from its deal (then `onStandingsJump` runs), and the standings' exit leaves the
 * replay. `show` keeps them in step with every viewer state, since a redraw of the board drops what they added.
 */
export class BoardLinks {
    constructor(replay, root, { onStandingsJump }) {
        this.replay = replay;
        this.root = root;
        this.onStandingsJump = onStandingsJump;
    }

    bind(viewer) {
        $("> .player", this.root)
            .off(".replay-links")
            .on("click.replay-links", (event) =>
                this.#viewFromNameplate(viewer, event.currentTarget),
            );
        $(".summary", this.root)
            .off(".replay-links")
            .on("click.replay-links", ".body .row-diff", (event) =>
                this.#seekFromStandings(viewer, event.currentTarget),
            );
        const exit = exitUrl();
        $(".summary .exit", this.root)
            .text(exitLabel(exit))
            .off(".replay-links")
            .on("click.replay-links", () => window.location.assign(exit));
    }

    show(state) {
        this.#titleNameplates(state);
        if (state.kind === POSITION.SUMMARY) {
            this.#linkStandingsRounds();
        }
    }

    #viewFromNameplate(viewer, plate) {
        const offset = NAMEPLATES.findIndex((place) => plate.classList.contains(place));
        if (offset > 0) {
            viewer.setViewpoint((viewer.state.seat + offset) % SEATS);
        }
    }

    /** The other seats' nameplates say that a click views the table from them; an AI-held seat's says what its mark means. */
    #titleNameplates({ seat: viewpoint, seatMarks }) {
        NAMEPLATES.forEach((place, offset) => {
            const plate = $(`> .player.${place}`, this.root);
            const seat = (viewpoint + offset) % SEATS;
            const name = this.replay.players[seat];
            const view = offset === 0 ? name : `View from ${name}`;
            const title = seatMarks[seat] === SEAT_MARK.AI ? `${view}${AI_TITLE}` : view;
            plate.add($(".name", plate)).attr("title", title);
        });
    }

    /**
     * Each round's name in the standings is a button to that round's deal, and a click anywhere on its row does the
     * same; a line under the table says so, a tap on a touch screen. Standings already linked are left as they are, so a
     * state change that drew nothing keeps the keyboard focus on a round's button.
     */
    #linkStandingsRounds() {
        const cells = $(".summary .body .row-diff .jushu", this.root);
        cells.not(cells.has(".replay-summary-round")).each((_, cell) => {
            const name = cell.textContent;
            $(cell)
                .empty()
                .append(
                    $('<button type="button" class="replay-summary-round">')
                        .attr("title", "Show this round from its deal")
                        .text(name),
                );
        });
        const table = $(".summary table", this.root);
        if (table.next(".replay-summary-hint").length === 0) {
            const verb = window.matchMedia(COARSE_POINTER_MEDIA).matches ? "Tap" : "Click";
            table.after(
                $('<p class="replay-summary-hint" lang="en">').text(`${verb} a round to replay it`),
            );
        }
    }

    /** The standings have a row per round, in order: a click on one shows that round from its deal. */
    #seekFromStandings(viewer, row) {
        const index = $(".summary .body .row-diff", this.root).index(row);
        viewer.seek(index, 0);
        this.onStandingsJump();
    }
}
