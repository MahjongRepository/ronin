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

let debugMode = true;
let overlayMode: OverlayMode = "none";

function rerender(): void {
    const app = document.getElementById("app");
    if (app) {
        render(storybookBoardView(), app);
    }
}

function handleDebugToggle(): void {
    debugMode = !debugMode;
    rerender();
}

function handleOverlayChange(event: Event): void {
    const select = event.target as HTMLSelectElement;
    overlayMode = select.value as OverlayMode;
    rerender();
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
        { isCurrent: true, isDealer: true, isRiichi: false, score: "25,000", wind: "East" },
        { isCurrent: false, isDealer: false, isRiichi: false, score: "25,000", wind: "South" },
        { isCurrent: false, isDealer: false, isRiichi: false, score: "25,000", wind: "West" },
        { isCurrent: false, isDealer: false, isRiichi: true, score: "24,000", wind: "North" },
    ],
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
        score: 33000,
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
        score: 21000,
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
        score: 25000,
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
        score: 21000,
        seat: 3,
        tiles: [],
    },
];

// Mock round-end result: tsumo by seat 0 with 3 yaku
const mockRoundEnd: RoundEndResult = {
    resultType: ROUND_RESULT_TYPE.TSUMO,
    scoreChanges: { "0": 8000, "1": -4000, "2": -2000, "3": -2000 },
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
        { finalScore: 52.0, score: 42000, seat: 0 },
        { finalScore: -2.0, score: 28000, seat: 2 },
        { finalScore: -22.0, score: 18000, seat: 1 },
        { finalScore: -28.0, score: 12000, seat: 3 },
    ],
    winnerSeat: 0,
};

function buildOverlay(): TemplateResult | undefined {
    if (overlayMode === "round_end") {
        return RoundEndDisplay(mockRoundEnd, mockPlayers, 0);
    }
    if (overlayMode === "game_end") {
        return GameEndDisplay(mockGameEnd, mockPlayers);
    }
    return undefined;
}

function storybookBoardView(): TemplateResult {
    return html`
        <div class="board-storybook">
            <div class="board-storybook__toolbar">
                <a href="/play/storybook" class="board-storybook__back">Back</a>
                <label class="board-storybook__toggle">
                    <input
                        type="checkbox"
                        ?checked=${debugMode}
                        @change=${handleDebugToggle}
                    />
                    Debug mode
                </label>
                <select class="board-storybook__select" @change=${handleOverlayChange}>
                    <option value="none" ?selected=${overlayMode === "none"}>No overlay</option>
                    <option value="round_end" ?selected=${overlayMode === "round_end"}>Round end</option>
                    <option value="game_end" ?selected=${overlayMode === "game_end"}>Game end</option>
                </select>
            </div>
            <div class="board-storybook__viewport">
                ${GameBoard({ debug: debugMode, overlay: buildOverlay(), state: mockState })}
            </div>
        </div>
    `;
}

export { storybookBoardView };
