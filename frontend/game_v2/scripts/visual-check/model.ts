import { type BrowserContextOptions, type BrowserType, type Page } from "playwright";

import { type BoardMeasure } from "./board-measure.ts";
import { type Box, type Size } from "./boxes.ts";

/** The transcript's labels the live game is stopped at: its call prompt's buttons, and its turn after the chi. */
export const LIVE_CHECKPOINTS = ["prompt", "turn"] as const;
export type LiveCheckpoint = (typeof LIVE_CHECKPOINTS)[number];
export const GAME_ID = "visual-check";
export const SELECTOR_TIMEOUT_MS = 5000;

/** Safe-area insets to emulate, which Playwright reports as zero: set through the theme's `--ronin-safe-*`. */
export interface Insets {
    readonly left: number;
    readonly right: number;
    readonly bottom: number;
}

export interface Viewport {
    readonly name: string;
    readonly engine: BrowserType;
    readonly context: BrowserContextOptions;
    readonly portrait: boolean;
    /** The live game shows its rotate panel here (an upright phone). */
    readonly rotates: boolean;
    /** A supported device size, where the tap minimum holds. */
    readonly supported: boolean;
    /** The smallest local hand tile it may draw in landscape, on a phone: a tap target. A desktop has none. */
    readonly ownTileFloor?: Size;
    /** A desktop window, not a phone (the decisions surface tells the phones apart by it). */
    readonly desktop: boolean;
    readonly insets?: Insets;
    /** The viewport and safe-area box a capture model must produce, asserted on every page before its checks. */
    readonly captureModel?: { readonly viewport: Size; readonly safeArea: Box };
}

interface Required {
    /** Selectors that must match an element a player can see. */
    readonly visible: readonly string[];
    /** Selectors that must match an element, shown or not (the game's hidden half of its rotate split). */
    readonly attached?: readonly string[];
}

/** What a board page asks of the board's checks beyond the board itself. */
export interface BoardOptions {
    /** The round result's panel is made shorter than its content, which must then scroll. */
    readonly panelScrolls?: boolean;
    /** Its names are longer than any badge holds, so a badge may shorten them in the middle. */
    readonly longNames?: boolean;
}

type PageKind =
    | { readonly kind: "document" }
    | (BoardOptions & {
          readonly kind: "board";
          readonly prepare?: (page: Page) => Promise<void>;
      })
    | {
          readonly kind: "own";
          /** The page's own checks in place of a board's, given the board's checks to run where it shows one. */
          readonly check: (run: PageRun, checkShownBoard: () => Promise<string>) => Promise<string>;
          /** The transcript's checkpoint the mocked game server plays it up to; none opens no game. */
          readonly checkpoint?: LiveCheckpoint;
      };

export type PageCase = PageKind & {
    readonly name: string;
    readonly path: string;
    readonly required: Required;
    /** The face's request is refused, so the page must stay readable in the fallback stack. */
    readonly fontBlocked?: boolean;
    /**
     * The viewports it is checked at, by name: where it is a worst case, or the one page guarding a path of the layout.
     * The floor alone (`FLOOR`) when absent.
     */
    readonly at?: readonly string[];
    /** Its texts, marks and faces are measured for contrast, at `CONTRAST_VIEWPORTS` (`checkContrast`). */
    readonly contrast?: boolean;
};

export type BoardCase = Extract<PageCase, { readonly kind: "board" }>;

export interface PageMeasure {
    readonly innerWidth: number;
    readonly innerHeight: number;
    readonly scrollWidth: number;
    readonly scrollHeight: number;
}

/** What one page's checks found: the failures, and how many checks ran so a page that checked nothing fails. */
export class PageReport {
    readonly failures: string[] = [];
    checks = 0;
    summary = "";

    expect(ok: boolean, failure: string): void {
        this.checks += 1;
        if (!ok) {
            this.failures.push(failure);
        }
    }
}

/** A fact a surface keeps from a page's checks for its checks across pages, by the page's report. */
export class PageRecord<Value> {
    readonly #values = new WeakMap<PageReport, Value>();

    keep(report: PageReport, value: Value): void {
        this.#values.set(report, value);
    }

    read(report: PageReport): Value | undefined {
        return this.#values.get(report);
    }
}

/** One page under check: the viewport it was loaded at, what its document measured, and its report. */
export interface PageRun {
    readonly page: Page;
    readonly viewport: Viewport;
    readonly measure: PageMeasure;
    readonly report: PageReport;
}

/** A page that draws a board, with the board's measure and the viewport's box in page coordinates. */
export interface BoardRun extends PageRun {
    readonly board: BoardMeasure;
    readonly screen: Box;
    readonly options: BoardOptions;
}

export interface TaskResult {
    readonly name: string;
    readonly viewport: string;
    readonly page: string;
    readonly report: PageReport;
}

/**
 * One surface of the client the gate checks: its pages, and its checks, which run on every page that draws a board
 * whichever surface's page it is, so a page is held to every surface's rules.
 */
export interface Surface {
    readonly pages: readonly PageCase[];
    /** Checks on the board as loaded, before its shot. */
    readonly checkBoard?: (run: BoardRun) => Promise<void> | void;
    /** Checks that change the page (a pager's click), once its shot and its contrast are taken. */
    readonly checkAfterShot?: (page: Page, report: PageReport) => Promise<void>;
    /** Checks across every page's report once the run ends, each failure named by its viewport. */
    readonly checkResults?: (results: readonly TaskResult[]) => readonly string[];
}
