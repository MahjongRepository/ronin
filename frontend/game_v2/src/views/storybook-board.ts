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
} from "@/entities/table";
import { type DiscardTile, type HandTile, type MeldInput } from "@/entities/tile";
import { ROUND_RESULT_TYPE } from "@/shared/protocol";

type OverlayMode = "none" | "round_end" | "game_end";

const OVERLAY_MODES: readonly OverlayMode[] = ["none", "round_end", "game_end"];

interface BoardStoryState {
    readonly debug: boolean;
    readonly overlay: OverlayMode;
}

function parseOverlayParam(search: string): OverlayMode {
    const param = new URLSearchParams(search).get("overlay");
    return OVERLAY_MODES.find((mode) => mode === param) ?? "none";
}

function syncOverlayParam(overlay: OverlayMode): void {
    const url = new URL(window.location.href);
    if (overlay === "none") {
        url.searchParams.delete("overlay");
    } else {
        url.searchParams.set("overlay", overlay);
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
        { isCurrent: false, isDealer: true, isRiichi: true, score: "25000", wind: "E" },
        { isCurrent: true, isDealer: false, isRiichi: true, score: "25000", wind: "S" },
        { isCurrent: false, isDealer: false, isRiichi: true, score: "25000", wind: "W" },
        { isCurrent: false, isDealer: false, isRiichi: true, score: "24000", wind: "N" },
    ],
    tilesRemaining: 42,
};

const bottomPlayer: BoardPlayerDisplay = {
    discards: bottomDiscards,
    drawnTile: bottomDrawn,
    hand: bottomHand,
    melds: bottomMelds,
};

const rightPlayer: BoardPlayerDisplay = {
    discards: rightDiscards,
    drawnTile: undefined,
    hand: rightHand,
    melds: rightMelds,
};

const topPlayer: BoardPlayerDisplay = {
    discards: topDiscards,
    drawnTile: undefined,
    hand: topHand,
    melds: topMelds,
};

const leftPlayer: BoardPlayerDisplay = {
    discards: leftDiscards,
    drawnTile: undefined,
    hand: leftHand,
    melds: leftMelds,
};

const mockState: BoardDisplayState = {
    center: mockCenter,
    players: [bottomPlayer, rightPlayer, topPlayer, leftPlayer],
};

// Mock players for overlay displays
const mockPlayers: PlayerState[] = [
    {
        discards: [],
        drawnTileId: null,
        isAiPlayer: false,
        isRiichi: false,
        melds: [],
        name: "You",
        score: 33_000,
        seat: 0,
        tiles: [],
    },
    {
        discards: [],
        drawnTileId: null,
        isAiPlayer: true,
        isRiichi: false,
        melds: [],
        name: "Bot South",
        score: 21_000,
        seat: 1,
        tiles: [],
    },
    {
        discards: [],
        drawnTileId: null,
        isAiPlayer: true,
        isRiichi: false,
        melds: [],
        name: "Bot West",
        score: 25_000,
        seat: 2,
        tiles: [],
    },
    {
        discards: [],
        drawnTileId: null,
        isAiPlayer: true,
        isRiichi: true,
        melds: [],
        name: "Bot North",
        score: 21_000,
        seat: 3,
        tiles: [],
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
    return html`
        <div class="board-storybook">
            <div class="board-storybook__viewport">
                ${GameBoard({ debug: story.debug, overlay: buildOverlay(story.overlay), state: mockState })}
            </div>
            <div class="board-storybook__overlay">
                <a class="board-storybook__btn" href="/play/storybook">Back</a>
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

/** Mount the board storybook into `host`; its overlay choice is kept in the page's `?overlay=` query. */
export function mountStorybookBoard(host: HTMLElement): () => void {
    let story: BoardStoryState = {
        debug: true,
        overlay: parseOverlayParam(window.location.search),
    };

    function show(next: BoardStoryState): void {
        story = next;
        render(storybookBoardTemplate(story, handlers), host);
    }

    const handlers: BoardStoryHandlers = {
        toggleDebug: () => show({ ...story, debug: !story.debug }),
        toggleOverlay(mode) {
            const overlay = story.overlay === mode ? "none" : mode;
            syncOverlayParam(overlay);
            show({ ...story, overlay });
        },
    };

    show(story);
    return () => {};
}
