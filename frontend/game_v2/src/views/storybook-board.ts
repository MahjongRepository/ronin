import { type TemplateResult, html, render } from "lit-html";

import {
    type BoardCallouts,
    type BoardCenterInfo,
    type BoardDisplayState,
    type BoardPlayerDisplay,
    type CalloutKind,
    GameBoard,
    type PlayerState,
    RoundEndDisplay,
    type RoundRecord,
    SEAT_POSITIONS,
    type SeatPosition,
    type StandingsAction,
    type StandingsRenderer,
    type TableState,
    boardCallouts,
    boardOverlay,
    createInitialPlayerState,
    createInitialTableState,
    roundEndDisplay,
    tableStateToDisplayState,
} from "@/entities/table";
import {
    type DiscardTile,
    type HandTile,
    type MeldInput,
    type MeldTile,
    meldTiles,
} from "@/entities/tile";
import { browserClock } from "@/shared/clock";
import { SEAT_CONTROL_REASON } from "@/shared/protocol";

import {
    RESULT_STORIES,
    type ResultStory,
    resultStoryLabel,
    resultStoryTable,
} from "./storybook-results";
import { startStorybookStandings } from "./storybook-standings";

type OverlayMode = "none" | "round_end" | "game_end";

const OVERLAY_MODES: readonly OverlayMode[] = ["none", "round_end", "game_end"];

/**
 * The board's hand-written stories, the edge cases no generated scenario reaches: full rivers, and the worst case of
 * all at once (every seat with four melds, long rivers, five dora, AI marks). A board the scenarios reach is a
 * decisions story instead.
 */
const BOARD_STORIES = ["full_rivers", "worst"] as const;

type BoardStory = (typeof BOARD_STORIES)[number];

const BOARD_STORY_LABELS: Readonly<Record<BoardStory, string>> = {
    full_rivers: "Full rivers",
    worst: "Worst case",
};

const DEFAULT_STORY: BoardStory = "full_rivers";

/** Every call the board shows, one of which the story shows at every seat at once. */
const CALLOUT_KINDS: readonly CalloutKind[] = ["ron", "tsumo", "pon", "chi", "kan", "riichi"];

interface BoardStoryState {
    readonly debug: boolean;
    /** The call shown at every seat, held still, kept in the page's `?callout=`; null for none. */
    readonly callout: CalloutKind | null;
    /** The nameplate pinned for the others' score differences, kept in the page's `?pin=`. */
    readonly pinned: SeatPosition | null;
    readonly overlay: OverlayMode;
    readonly story: BoardStory;
    readonly result: ResultStory;
    readonly page: number;
}

const DEFAULT_RESULT: ResultStory = "tsumo";

function parseResultParam(search: string): ResultStory {
    const param = new URLSearchParams(search).get("result");
    return RESULT_STORIES.find((result) => result === param) ?? DEFAULT_RESULT;
}

function parsePageParam(search: string): number {
    const page = Number(new URLSearchParams(search).get("page") ?? "0");
    return Number.isInteger(page) && page >= 0 ? page : 0;
}

function parseOverlayParam(search: string): OverlayMode {
    const param = new URLSearchParams(search).get("overlay");
    return OVERLAY_MODES.find((mode) => mode === param) ?? "none";
}

function parseCalloutParam(search: string): CalloutKind | null {
    const param = new URLSearchParams(search).get("callout");
    return CALLOUT_KINDS.find((kind) => kind === param) ?? null;
}

/** The story's call at every seat, which the storybook's stylesheet holds still so it can be read and measured. */
function storyCallouts(kind: CalloutKind | null): BoardCallouts | null {
    if (kind === null) {
        return null;
    }
    const calls = SEAT_POSITIONS.map((_position, seat) => ({ kind, seat }));
    return { items: boardCallouts(calls, 0), key: kind };
}

function parsePinParam(search: string): SeatPosition | null {
    const param = new URLSearchParams(search).get("pin");
    return SEAT_POSITIONS.find((seat) => seat === param) ?? null;
}

function parseStoryParam(search: string): BoardStory {
    const param = new URLSearchParams(search).get("state");
    return BOARD_STORIES.find((story) => story === param) ?? DEFAULT_STORY;
}

function syncQueryParam(name: string, value: string, fallback: string): void {
    const url = new URL(window.location.href);
    if (value === fallback) {
        url.searchParams.delete(name);
    } else {
        url.searchParams.set(name, value);
    }
    history.replaceState(null, "", url);
}

// Mock data: bottom player (seat 0) — face-up hand, 2 melds, 8 discards
const bottomHand: HandTile[] = [
    { face: "1m", show: "face" },
    { face: "2m", show: "face" },
    { face: "3m", show: "face" },
    { face: "5p", show: "face" },
    { face: "6p", show: "face" },
    { face: "7p", show: "face" },
    { face: "2s", show: "face" },
];
const bottomDrawn: HandTile = { face: "6z", show: "face" };
const bottomMelds: MeldInput[] = [
    { calledTileId: 125, callerSeat: 0, fromSeat: 2, meldType: "pon", tileIds: [124, 125, 126] },
    { calledTileId: 96, callerSeat: 0, fromSeat: 3, meldType: "chi", tileIds: [96, 100, 104] },
];
const bottomDiscards: DiscardTile[] = [
    { face: "9m" },
    { face: "8m" },
    { face: "4z" },
    { face: "3z" },
    { face: "2z" },
    { face: "9p" },
    { face: "1p" },
    { face: "4m" },
];

// Mock data: right player (seat 1) — face-up, pon + open kan, 6 discards
const rightHand: HandTile[] = [
    { face: "1p", show: "face" },
    { face: "2p", show: "face" },
    { face: "3p", show: "face" },
    { face: "4p", show: "face" },
    { face: "6p", show: "face" },
    { face: "7p", show: "face" },
];
const rightMelds: MeldInput[] = [
    { calledTileId: 73, callerSeat: 1, fromSeat: 2, meldType: "pon", tileIds: [72, 73, 74] },
    {
        calledTileId: 135,
        callerSeat: 1,
        fromSeat: 3,
        meldType: "open_kan",
        tileIds: [132, 133, 134, 135],
    },
];
const rightDiscards: DiscardTile[] = [
    { face: "7z" },
    { face: "6z" },
    { face: "1m" },
    { face: "9s" },
    { face: "8p" },
    { face: "2m" },
];

// Mock data: top player (seat 2) — face-up, chi + closed kan, 10 discards
const topHand: HandTile[] = [
    { face: "1m", show: "face" },
    { face: "2m", show: "face" },
    { face: "4m", show: "face" },
    { face: "5m", show: "face" },
    { face: "7p", show: "face" },
    { face: "8p", show: "face" },
];
const topMelds: MeldInput[] = [
    { calledTileId: 84, callerSeat: 2, fromSeat: 1, meldType: "chi", tileIds: [84, 88, 92] },
    {
        calledTileId: null,
        callerSeat: 2,
        fromSeat: null,
        meldType: "closed_kan",
        tileIds: [108, 109, 110, 111],
    },
];
const topDiscards: DiscardTile[] = [
    { face: "1z" },
    { face: "2z" },
    { face: "3z" },
    { face: "4z" },
    { face: "9m" },
    { face: "8m" },
    { face: "7m" },
    { face: "1p" },
    { face: "2p" },
    { face: "3p" },
];

// Mock data: left player (seat 3) — face-up, 2 melds, 7 discards with 1 riichi
const leftHand: HandTile[] = [
    { face: "3m", show: "face" },
    { face: "4m", show: "face" },
    { face: "5m", show: "face" },
    { face: "7m", show: "face" },
    { face: "8m", show: "face" },
    { face: "9m", show: "face" },
    { face: "1p", show: "face" },
];
const leftMelds: MeldInput[] = [
    { calledTileId: 114, callerSeat: 3, fromSeat: 1, meldType: "pon", tileIds: [112, 113, 114] },
    { calledTileId: 104, callerSeat: 3, fromSeat: 2, meldType: "pon", tileIds: [104, 105, 106] },
];
const leftDiscards: DiscardTile[] = [
    { face: "5m" },
    { face: "6m" },
    { face: "7z" },
    { face: "6z" },
    { face: "5z" },
    { face: "9p", riichi: true },
    { face: "3m" },
];

const mockCenter: BoardCenterInfo = {
    doraIndicators: ["5m"],
    honbaSticks: 0,
    riichiSticks: 1,
    roundDisplay: "East 1",
    tilesRemaining: 42,
};

type SeatPlayers = readonly [PlayerState, PlayerState, PlayerState, PlayerState];

/** The nameplates the board mapper gives four mock players, seat 0 at the bottom, the seat named current to play. */
function mockNameplates(
    players: SeatPlayers,
    currentPlayerSeat: number,
): BoardDisplayState["nameplates"] {
    const table = { ...createInitialTableState(), currentPlayerSeat, players };
    const display = tableStateToDisplayState(table, { bottomSeat: 0, reveal: "all" });
    if (display === null) {
        throw new Error("mock nameplates need four players");
    }
    return display.nameplates;
}

function mockRiichiPlayer(seat: number, name: string, score: number): PlayerState {
    return {
        ...createInitialPlayerState({ isAiPlayer: false, name, score, seat }),
        isRiichi: true,
    };
}

const riverPlates = mockNameplates(
    [
        mockRiichiPlayer(0, "Alice", 25_000),
        { ...mockRiichiPlayer(1, "Bob", 32_300), isRiichi: false },
        mockRiichiPlayer(2, "Charlie", 18_700),
        mockRiichiPlayer(3, "Diana", 24_000),
    ],
    1,
);

/**
 * The worst case's plates: names too long for any plate, an AI player seated from the start, one standing in for a
 * human who left and one for a human who never came, every seat in riichi, and scores far apart.
 */
const worstPlates = mockNameplates(
    [
        mockRiichiPlayer(0, "Bartholomew Featherstonehaugh", 41_300),
        {
            ...mockRiichiPlayer(1, "Wolfeschlegelsteinhausenberger", -2600),
            aiStandIn: SEAT_CONTROL_REASON.LEFT,
        },
        { ...mockRiichiPlayer(2, "Tsumogiri 2", 7000), isAiPlayer: true },
        {
            ...mockRiichiPlayer(3, "Maximiliana Ostrogradskaya", 54_300),
            aiStandIn: SEAT_CONTROL_REASON.ABSENT,
        },
    ],
    3,
);

function laid(melds: readonly MeldInput[]): MeldTile[][] {
    return melds.map(meldTiles);
}

const bottomPlayer: BoardPlayerDisplay = {
    discards: bottomDiscards,
    drawnTile: bottomDrawn,
    hand: bottomHand,
    melds: laid(bottomMelds),
};

const rightPlayer: BoardPlayerDisplay = {
    discards: rightDiscards,
    drawnTile: undefined,
    hand: rightHand,
    melds: laid(rightMelds),
};

const topPlayer: BoardPlayerDisplay = {
    discards: topDiscards,
    drawnTile: undefined,
    hand: topHand,
    melds: laid(topMelds),
};

const leftPlayer: BoardPlayerDisplay = {
    discards: leftDiscards,
    drawnTile: undefined,
    hand: leftHand,
    melds: laid(leftMelds),
};

/** Nineteen discards, a long river a drawn round can reach: its third row runs past the other two. */
const fullRiver: DiscardTile[] = [
    ...bottomDiscards,
    ...topDiscards.slice(0, 7),
    { face: "5s" },
    { face: "6s", riichi: true },
    { face: "7s" },
    { face: "8s" },
];

const thirteenFaces: HandTile[] = [...bottomHand, ...leftHand.slice(0, 6)];

function withRiver(player: BoardPlayerDisplay, hand: readonly HandTile[]): BoardPlayerDisplay {
    return { ...player, discards: fullRiver, hand, melds: [] };
}

/** Twenty-four discards: the longest third row the worst case lays out, six past the others. */
const longRiver: DiscardTile[] = [
    ...fullRiver,
    { face: "9s" },
    { face: "1z" },
    { face: "2z" },
    { face: "3z" },
    { face: "4z" },
];

/** The long river with its last tile the table's latest discard, which only one seat's river holds. */
const latestRiver: DiscardTile[] = [...longRiver.slice(0, -1), { face: "4z", last: true }];

/** Four melds for `seat`, the widest kinds: a closed, an open and an added kan, then a pon. */
function fourMelds(seat: number): MeldInput[] {
    return [
        {
            calledTileId: null,
            callerSeat: seat,
            fromSeat: null,
            meldType: "closed_kan",
            tileIds: [0, 1, 2, 3],
        },
        {
            calledTileId: 39,
            callerSeat: seat,
            fromSeat: (seat + 1) % 4,
            meldType: "open_kan",
            tileIds: [36, 37, 38, 39],
        },
        {
            addedTileId: 75,
            calledTileId: 73,
            callerSeat: seat,
            fromSeat: (seat + 2) % 4,
            meldType: "added_kan",
            tileIds: [72, 73, 74, 75],
        },
        {
            calledTileId: 117,
            callerSeat: seat,
            fromSeat: (seat + 3) % 4,
            meldType: "pon",
            tileIds: [116, 117, 118],
        },
    ];
}

function worstSeat(seat: number, discards: readonly DiscardTile[] = longRiver): BoardPlayerDisplay {
    return {
        discards,
        drawnTile: { face: "6z", show: "face" },
        hand: [{ face: "2s", show: "face" }],
        melds: laid(fourMelds(seat)),
    };
}

const BOARD_STATES: Readonly<Record<BoardStory, BoardDisplayState>> = {
    full_rivers: {
        center: { ...mockCenter, tilesRemaining: 2 },
        nameplates: riverPlates,
        players: [
            withRiver(bottomPlayer, thirteenFaces),
            withRiver(rightPlayer, thirteenFaces),
            withRiver(topPlayer, thirteenFaces),
            withRiver(leftPlayer, thirteenFaces),
        ],
    },
    worst: {
        center: {
            ...mockCenter,
            doraIndicators: ["5m", "3p", "7s", "2z", "9m"],
            riichiSticks: 4,
            tilesRemaining: 0,
        },
        nameplates: worstPlates,
        players: [worstSeat(0), worstSeat(1), worstSeat(2), worstSeat(3, latestRiver)],
    },
};

const STANDINGS_PLAYERS: readonly PlayerState[] = [
    createInitialPlayerState({ isAiPlayer: false, name: "You", score: 39_500, seat: 0 }),
    createInitialPlayerState({ isAiPlayer: true, name: "Bot South", score: 12_000, seat: 1 }),
    createInitialPlayerState({ isAiPlayer: true, name: "Bot West", score: 29_100, seat: 2 }),
    createInitialPlayerState({ isAiPlayer: true, name: "Bot North", score: 19_400, seat: 3 }),
];

const NO_RIICHI: readonly number[] = [];

/**
 * A short East-only game that ends on a draw with a riichi stick left: a ron on a riichi, a tenpai draw, a tsumo on
 * honba, a draw that keeps a riichi stick on the table, a ron collecting it, then a draw leaving one to the winner.
 */
const STANDINGS_HISTORY: readonly RoundRecord[] = [
    {
        dealerSeat: 0,
        honba: 0,
        loserSeat: 3,
        outcome: "ron",
        riichiSeats: [0],
        scoreChanges: { "0": 4900, "3": -3900 },
        tenpaiSeats: null,
        wind: 0,
        winnerSeats: [0],
    },
    {
        dealerSeat: 0,
        honba: 1,
        loserSeat: null,
        outcome: "exhaustive",
        riichiSeats: NO_RIICHI,
        scoreChanges: { "0": 1500, "1": -1500, "2": 1500, "3": -1500 },
        tenpaiSeats: [0, 2],
        wind: 0,
        winnerSeats: [],
    },
    {
        dealerSeat: 0,
        honba: 2,
        loserSeat: null,
        outcome: "tsumo",
        riichiSeats: NO_RIICHI,
        scoreChanges: { "0": -2200, "1": -1200, "2": 4600, "3": -1200 },
        tenpaiSeats: null,
        wind: 0,
        winnerSeats: [2],
    },
    {
        dealerSeat: 1,
        honba: 0,
        loserSeat: null,
        outcome: "exhaustive",
        riichiSeats: [3],
        scoreChanges: { "0": -1000, "1": -1000, "2": -1000, "3": 3000 },
        tenpaiSeats: [3],
        wind: 0,
        winnerSeats: [],
    },
    {
        dealerSeat: 2,
        honba: 1,
        loserSeat: 1,
        outcome: "ron",
        riichiSeats: NO_RIICHI,
        scoreChanges: { "0": 9300, "1": -8300 },
        tenpaiSeats: null,
        wind: 0,
        winnerSeats: [0],
    },
    {
        dealerSeat: 3,
        honba: 0,
        loserSeat: null,
        outcome: "exhaustive",
        riichiSeats: [0],
        scoreChanges: { "0": 3000, "1": -1000, "2": -1000, "3": -1000 },
        tenpaiSeats: [0],
        wind: 0,
        winnerSeats: [],
    },
];

/** The table that short game ends on, its standings as the server ranks them with uma and oka. */
const STANDINGS_TABLE: TableState = {
    ...createInitialTableState(),
    dealerSeat: 3,
    gameEndResult: {
        leftoverRiichiBonus: 1000,
        standings: [
            { finalScore: 50, score: 39_500, seat: 0 },
            { finalScore: 9, score: 29_100, seat: 2 },
            { finalScore: -21, score: 19_400, seat: 3 },
            { finalScore: -38, score: 12_000, seat: 1 },
        ],
        winnerSeat: 0,
    },
    phase: "game_ended",
    players: STANDINGS_PLAYERS,
    roundHistory: STANDINGS_HISTORY,
};

const STANDINGS_ACTIONS: readonly StandingsAction[] = [
    { href: "/play/storybook/replay?state=standings", kind: "link", label: "Replay" },
    { href: "/play/storybook", kind: "link", label: "Storybook", primary: true },
];

function buildOverlay(
    story: BoardStoryState,
    handlers: BoardStoryHandlers,
    standings: StandingsRenderer | null,
): TemplateResult | undefined {
    const { overlay } = story;
    if (overlay === "round_end") {
        return RoundEndDisplay({
            display: roundEndDisplay(resultStoryTable(story.result), story.page),
            onPage: handlers.showPage,
        });
    }
    if (overlay === "game_end") {
        return boardOverlay(STANDINGS_TABLE, {
            standings: { actions: STANDINGS_ACTIONS, renderer: standings, viewerSeat: 0 },
        });
    }
    return undefined;
}

interface BoardStoryHandlers {
    readonly showStory: (story: BoardStory) => void;
    readonly showResult: (result: ResultStory) => void;
    readonly showPage: (page: number) => void;
    readonly showCallout: (kind: CalloutKind | null) => void;
    readonly pin: (seat: SeatPosition | null) => void;
    readonly toggleDebug: () => void;
    readonly toggleOverlay: (mode: OverlayMode) => void;
}

function activeClass(active: boolean): string {
    return active ? "board-storybook__btn--active" : "";
}

function storybookBoardTemplate(
    story: BoardStoryState,
    handlers: BoardStoryHandlers,
    standings: StandingsRenderer | null,
): TemplateResult {
    const state = BOARD_STATES[story.story];
    return html`
        <div class="board-page board-storybook">
            <div class="board-page__board">
                ${GameBoard({
                    callouts: storyCallouts(story.callout),
                    debug: story.debug,
                    overlay: buildOverlay(story, handlers, standings),
                    scoreDiff: { onPin: handlers.pin, pinned: story.pinned },
                    state,
                })}
            </div>
            <div class="board-page__aside">
                <a class="board-storybook__btn" href="/play/storybook">Back</a>
                ${BOARD_STORIES.map(
                    (key) => html`<button
                        class="board-storybook__btn ${activeClass(story.story === key)}"
                        @click=${() => handlers.showStory(key)}
                    >${BOARD_STORY_LABELS[key]}</button>`,
                )}
                <button
                    class="board-storybook__btn ${activeClass(story.debug)}"
                    @click=${handlers.toggleDebug}
                >Debug</button>
                <button
                    class="board-storybook__btn ${activeClass(story.overlay === "round_end")}"
                    @click=${() => handlers.toggleOverlay("round_end")}
                >Round end</button>
                ${
                    story.overlay === "round_end"
                        ? html`<div class="board-storybook__picker"><select
                              class="board-storybook__select"
                              aria-label="Round result"
                              @change=${(event: Event) => {
                                  const { target } = event;
                                  const picked = RESULT_STORIES.find(
                                      (result) =>
                                          target instanceof HTMLSelectElement &&
                                          result === target.value,
                                  );
                                  if (picked !== undefined) {
                                      handlers.showResult(picked);
                                  }
                              }}
                          >
                              ${RESULT_STORIES.map(
                                  (
                                      result,
                                  ) => html`<option value=${result} ?selected=${result === story.result}>
                                      ${resultStoryLabel(result)}
                                  </option>`,
                              )}
                          </select></div>`
                        : ""
                }
                <button
                    class="board-storybook__btn ${activeClass(story.overlay === "game_end")}"
                    @click=${() => handlers.toggleOverlay("game_end")}
                >Game end</button>
                <div class="board-storybook__picker"><select
                    class="board-storybook__select"
                    aria-label="Call shown"
                    @change=${(event: Event) => {
                        const { target } = event;
                        const value = target instanceof HTMLSelectElement ? target.value : "";
                        handlers.showCallout(CALLOUT_KINDS.find((kind) => kind === value) ?? null);
                    }}
                >
                    <option value="" ?selected=${story.callout === null}>No call</option>
                    ${CALLOUT_KINDS.map(
                        (kind) =>
                            html`<option value=${kind} ?selected=${kind === story.callout}>Call: ${kind}</option>`,
                    )}
                </select></div>
            </div>
        </div>
    `;
}

/** Mount the board storybook into `host`; its story and overlay are kept in the page's `?state=` and `?overlay=`. */
export function mountStorybookBoard(host: HTMLElement): () => void {
    const standings = startStorybookStandings(browserClock.setTimer);
    let story: BoardStoryState = {
        callout: parseCalloutParam(window.location.search),
        debug: true,
        overlay: parseOverlayParam(window.location.search),
        page: parsePageParam(window.location.search),
        pinned: parsePinParam(window.location.search),
        result: parseResultParam(window.location.search),
        story: parseStoryParam(window.location.search),
    };

    function show(next: BoardStoryState): void {
        story = next;
        render(storybookBoardTemplate(story, handlers, standings.value()), host);
    }

    const handlers: BoardStoryHandlers = {
        pin(seat) {
            syncQueryParam("pin", seat ?? "", "");
            show({ ...story, pinned: seat });
        },
        showCallout(callout) {
            syncQueryParam("callout", callout ?? "", "");
            show({ ...story, callout });
        },
        showPage(page) {
            syncQueryParam("page", String(page), "0");
            show({ ...story, page });
        },
        showResult(result) {
            syncQueryParam("result", result, DEFAULT_RESULT);
            syncQueryParam("page", "0", "0");
            show({ ...story, page: 0, result });
        },
        showStory(key) {
            syncQueryParam("state", key, DEFAULT_STORY);
            show({ ...story, story: key });
        },
        toggleDebug: () => show({ ...story, debug: !story.debug }),
        toggleOverlay(mode) {
            const overlay = story.overlay === mode ? "none" : mode;
            syncQueryParam("overlay", overlay, "none");
            show({ ...story, overlay });
        },
    };

    standings.subscribe(() => show(story));
    show(story);
    return () => standings.stop();
}
