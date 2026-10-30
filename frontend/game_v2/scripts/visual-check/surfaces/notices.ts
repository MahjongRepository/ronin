import { type Page } from "playwright";

import { type BoardMeasure, measureBoxes } from "../board-measure.ts";
import { type Box, contains, describeBox, intersects } from "../boxes.ts";
import { decisionCase } from "../cases.ts";
import { type BoardRun, type PageCase, type PageReport, type Surface } from "../model.ts";

const PAGES: readonly PageCase[] = [
    decisionCase("connection_lost", [
        ".board-notice--warning",
        ".game-menu__status:not(.status-connected)",
    ]),
    decisionCase("move_refused", [".board-notice--warning", ".hand-tile--selectable"]),
    decisionCase("faces_missing", [".board-notice__action", ".hand-tile--selectable"]),
];

/**
 * A notice over the table never hides a tile, a nameplate, the decision's corner or the panel over the board, however
 * long it stays.
 */
function checkNotices(notices: readonly Box[], board: BoardMeasure, report: PageReport): void {
    const covered = [
        ...board.tiles,
        ...board.nameplates,
        ...(board.decisionCorner?.buttons ?? []),
        ...(board.overlay === null ? [] : [board.overlay.box]),
    ];
    const over = notices.filter((notice) => covered.some((box) => intersects(notice, box)));
    report.expect(
        over.length === 0,
        `notice(s) over a tile, plate, decision button or panel: ${over.map(describeBox).join(", ")}`,
    );
    const outside = notices.filter((notice) => !contains(board.board, notice));
    report.expect(outside.length === 0, `${outside.length} notice(s) off the board`);
}

/** Each notice as its scrolling place shows it, for a page that names the viewport a known cut (`noticeCutAt`). */
function measureShownNotices(page: Page): Promise<readonly Box[]> {
    return page.evaluate(() =>
        [...document.querySelectorAll(".game-board .board-notice")].flatMap((notice) => {
            const own = notice.getBoundingClientRect();
            const place = notice.closest(".board-notices")?.getBoundingClientRect() ?? own;
            const left = Math.max(own.left, place.left);
            const top = Math.max(own.top, place.top);
            const width = Math.min(own.right, place.right) - left;
            const height = Math.min(own.bottom, place.bottom) - top;
            return width > 0 && height > 0
                ? [{ height, left: left + window.scrollX, top: top + window.scrollY, width }]
                : [];
        }),
    );
}

async function checkBoard({ board, options, page, report, viewport }: BoardRun): Promise<void> {
    if (!viewport.supported || viewport.portrait) {
        return;
    }
    const knownCut = options.noticeCutAt?.includes(viewport.name) === true;
    const notices = knownCut
        ? await measureShownNotices(page)
        : await measureBoxes(page, ".board-notice");
    checkNotices(notices, board, report);
}

/** The notices over the table: a lost connection, a refused move, faces that did not load. */
export const noticesSurface: Surface = {
    checkBoard,
    pages: PAGES,
};
