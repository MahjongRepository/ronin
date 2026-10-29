import { type TemplateResult, html, render } from "lit-html";

import {
    type BoardCenterInfo,
    type BoardDisplayState,
    type BoardPlayerDisplay,
    GameBoard,
    GameEndDisplay,
    type GameEndResult,
    type PlayerState,
    RoundEndDisplay,
    type RoundEndResult,
    createInitialPlayerState,
} from "@/entities/table";
import {
    type DiscardTile,
    type HandTile,
    type MeldInput,
    type MeldTile,
    meldTiles,
} from "@/entities/tile";
import { ROUND_RESULT_TYPE } from "@/shared/protocol";

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

interface BoardStoryState {
    readonly debug: boolean;
    readonly overlay: OverlayMode;
    readonly story: BoardStory;
}

function parseOverlayParam(search: string): OverlayMode {
    const param = new URLSearchParams(search).get("overlay");
    return OVERLAY_MODES.find((mode) => mode === param) ?? "none";
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
    scores: [
        {
            aiStandIn: false,
            isCurrent: false,
            isDealer: true,
            isRiichi: true,
            score: "25000",
            wind: "E",
        },
        {
            aiStandIn: false,
            isCurrent: true,
            isDealer: false,
            isRiichi: true,
            score: "25000",
            wind: "S",
        },
        {
            aiStandIn: false,
            isCurrent: false,
            isDealer: false,
            isRiichi: true,
            score: "25000",
            wind: "W",
        },
        {
            aiStandIn: false,
            isCurrent: false,
            isDealer: false,
            isRiichi: true,
            score: "24000",
            wind: "N",
        },
    ],
    tilesRemaining: 42,
};

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

/** Twenty-one discards: the longest third row the worst case lays out. */
const longRiver: DiscardTile[] = [...fullRiver, { face: "9s" }, { face: "1z" }];

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

function worstSeat(seat: number): BoardPlayerDisplay {
    return {
        discards: longRiver,
        drawnTile: { face: "6z", show: "face" },
        hand: [{ face: "2s", show: "face" }],
        melds: laid(fourMelds(seat)),
    };
}

const BOARD_STATES: Readonly<Record<BoardStory, BoardDisplayState>> = {
    full_rivers: {
        center: { ...mockCenter, tilesRemaining: 2 },
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
            scores: [
                mockCenter.scores[0],
                { ...mockCenter.scores[1], aiStandIn: true },
                mockCenter.scores[2],
                { ...mockCenter.scores[3], aiStandIn: true },
            ],
            tilesRemaining: 0,
        },
        players: [worstSeat(0), worstSeat(1), worstSeat(2), worstSeat(3)],
    },
};

// Mock players for overlay displays
const mockPlayers: readonly PlayerState[] = [
    createInitialPlayerState({ isAiPlayer: false, name: "You", score: 33_000, seat: 0 }),
    createInitialPlayerState({ isAiPlayer: true, name: "Bot South", score: 21_000, seat: 1 }),
    createInitialPlayerState({ isAiPlayer: true, name: "Bot West", score: 25_000, seat: 2 }),
    {
        ...createInitialPlayerState({
            isAiPlayer: true,
            name: "Bot North",
            score: 21_000,
            seat: 3,
        }),
        isRiichi: true,
    },
];

// Mock round-end result: tsumo by seat 0 with 3 yaku
const mockRoundEnd: RoundEndResult = {
    doraIndicators: [16, 56],
    resultType: ROUND_RESULT_TYPE.TSUMO,
    scoreChanges: { "0": 8000, "1": -4000, "2": -2000, "3": -2000 },
    scoresBeforePayment: { "0": 25_000, "1": 25_000, "2": 27_000, "3": 23_000 },
    uraDoraIndicators: [28],
    winners: [
        {
            closedTiles: [0, 4, 8, 36, 40, 44, 72, 76, 80, 108, 112, 116, 120],
            handResult: {
                fu: 40,
                han: 3,
                yaku: [
                    { han: 1, yakuId: 0 },
                    { han: 1, yakuId: 23 },
                    { han: 1, yakuId: 1 },
                ],
            },
            melds: [],
            seat: 0,
            winningTile: 124,
        },
    ],
};

// Mock game-end result: 4 player standings
const mockGameEnd: GameEndResult = {
    leftoverRiichiBonus: 1000,
    standings: [
        { finalScore: 52, score: 42_000, seat: 0 },
        { finalScore: -2, score: 28_000, seat: 2 },
        { finalScore: -22, score: 18_000, seat: 1 },
        { finalScore: -28, score: 12_000, seat: 3 },
    ],
    winnerSeat: 0,
};

function buildOverlay(overlay: OverlayMode): TemplateResult | undefined {
    if (overlay === "round_end") {
        return RoundEndDisplay(mockRoundEnd, mockPlayers, 0);
    }
    if (overlay === "game_end") {
        return GameEndDisplay(mockGameEnd, mockPlayers);
    }
    return undefined;
}

interface BoardStoryHandlers {
    readonly showStory: (story: BoardStory) => void;
    readonly toggleDebug: () => void;
    readonly toggleOverlay: (mode: OverlayMode) => void;
}

function activeClass(active: boolean): string {
    return active ? "board-storybook__btn--active" : "";
}

function storybookBoardTemplate(
    story: BoardStoryState,
    handlers: BoardStoryHandlers,
): TemplateResult {
    const state = BOARD_STATES[story.story];
    return html`
        <div class="board-page board-storybook">
            <div class="board-page__board">
                ${GameBoard({ debug: story.debug, overlay: buildOverlay(story.overlay), state })}
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
                <button
                    class="board-storybook__btn ${activeClass(story.overlay === "game_end")}"
                    @click=${() => handlers.toggleOverlay("game_end")}
                >Game end</button>
            </div>
        </div>
    `;
}

/** Mount the board storybook into `host`; its story and overlay are kept in the page's `?state=` and `?overlay=`. */
export function mountStorybookBoard(host: HTMLElement): () => void {
    let story: BoardStoryState = {
        debug: true,
        overlay: parseOverlayParam(window.location.search),
        story: parseStoryParam(window.location.search),
    };

    function show(next: BoardStoryState): void {
        story = next;
        render(storybookBoardTemplate(story, handlers), host);
    }

    const handlers: BoardStoryHandlers = {
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

    show(story);
    return () => {};
}
