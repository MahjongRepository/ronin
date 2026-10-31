import { type TemplateResult, html, render } from "lit-html";

import {
    type ActionRank,
    type DecisionAction,
    DecisionControls,
    type DecisionView,
    type Offer,
    type PlayCommand,
} from "@/entities/client";
import {
    type BoardCallouts,
    type BoardCenterInfo,
    type BoardDisplayState,
    type BoardNotice,
    type BoardPlayerDisplay,
    type CalloutKind,
    GameBoard,
    NoticeSheet,
    type PanelAction,
    type PlayerState,
    RoundEndDisplay,
    SEAT_POSITIONS,
    type SeatPosition,
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
    type TileFace,
    meldTiles,
} from "@/entities/tile";
import { assertNever } from "@/shared/lib";
import { GAME_END_CAUSE, SEAT_CONTROL_REASON } from "@/shared/protocol";

import { storybookHref, storybookIndexHref } from "./storybook-nav";
import {
    RESULT_STORIES,
    type ResultStory,
    resultStoryLabel,
    resultStoryTable,
} from "./storybook-results";

type OverlayMode = "none" | "round_end" | "game_end";

const OVERLAY_MODES: readonly OverlayMode[] = ["none", "round_end", "game_end"];

/**
 * The board's hand-written stories, the edge cases no generated scenario reaches: full rivers, the worst case of all
 * at once (every seat with four melds, long rivers, five dora, AI marks), the strips' capacity: every opponent's
 * full hand (fourteen faces with the drawn tile apart, or thirteen backs) and legal mixed hands, each seat at one,
 * two and three melds across the three mixed stories, four kans a seat, every kind, whose open and added kans
 * between two kan stories come from every feeder, and four open kans a seat, the longest strip. A board the
 * scenarios reach is a decisions story instead.
 */
const BOARD_STORIES = [
    "full_rivers",
    "worst",
    "riichi_latest",
    "full_hands",
    "concealed_hands",
    "mixed_hands_a",
    "mixed_hands_b",
    "mixed_hands_c",
    "kans_a",
    "kans_b",
    "kans_c",
] as const;

type BoardStory = (typeof BOARD_STORIES)[number];

const BOARD_STORY_LABELS: Readonly<Record<BoardStory, string>> = {
    concealed_hands: "Concealed hands",
    full_hands: "Full hands",
    full_rivers: "Full rivers",
    kans_a: "Kans A",
    kans_b: "Kans B",
    kans_c: "Kans C",
    mixed_hands_a: "Mixed hands A",
    mixed_hands_b: "Mixed hands B",
    mixed_hands_c: "Mixed hands C",
    riichi_latest: "Riichi just discarded",
    worst: "Worst case",
};

/** The capacity stories, drawn as a played board's row (its furiten slot kept), as the live game draws it. */
const PLAYED_ROW_STORIES: ReadonlySet<BoardStory> = new Set([
    "full_hands",
    "concealed_hands",
    "mixed_hands_a",
    "mixed_hands_b",
    "mixed_hands_c",
    "kans_a",
    "kans_b",
    "kans_c",
]);

const DEFAULT_STORY: BoardStory = "full_rivers";

/** Every call the board shows, one of which the story may show at every seat at once. */
const CALLOUT_KINDS: readonly CalloutKind[] = ["ron", "tsumo", "pon", "chi", "kan", "riichi"];

/**
 * The calls a story shows at once: one kind at every seat, a different call at every seat, or a triple ron, whose
 * three claimants are every seat but the one whose river holds the latest discard.
 */
const STORY_CALLS = [...CALLOUT_KINDS, "every", "triple_ron"] as const;

type StoryCall = (typeof STORY_CALLS)[number];

const STORY_CALL_LABELS: Readonly<Record<StoryCall, string>> = {
    chi: "Call: chi",
    every: "Calls: one a seat",
    kan: "Call: kan",
    pon: "Call: pon",
    riichi: "Call: riichi",
    ron: "Call: ron",
    triple_ron: "Calls: triple ron",
    tsumo: "Call: tsumo",
};

/** A different call at each seat, bottom, right, top and left. */
const EVERY_CALL: readonly CalloutKind[] = ["riichi", "pon", "kan", "chi"];

/** The seat that discards a triple ron's tile where no river holds the latest discard: the left one. */
const DEFAULT_DISCARDER = 3;

/** The story's long notice, kept in the page's `?notice=long`: a message the client could not read, worded as the live board words it. */
const LONG_NOTICE_TEXT =
    "The game server sent a message this page could not read, so the table may be wrong until the server sends it again; play goes on.";

interface BoardStoryState {
    readonly debug: boolean;
    /** The long notice shows in the notices' place, kept in the page's `?notice=long`. */
    readonly notice: boolean;
    /** The long notice is opened whole in its sheet. */
    readonly noticeOpen: boolean;
    /** The calls shown, held still, kept in the page's `?callout=`; null for none. */
    readonly callout: StoryCall | null;
    /** The nameplate pinned for the others' score differences, kept in the page's `?pin=`. */
    readonly pinned: SeatPosition | null;
    readonly overlay: OverlayMode;
    /** The game ends under rules that award the leftover sticks to nobody, kept in the page's `?leftover=lost`. */
    readonly leftoverLost: boolean;
    readonly story: BoardStory;
    readonly result: ResultStory;
    readonly page: number;
    /**
     * The controls over the board, kept in the page's `?offers=`: the most one discard can offer, or a turn's pressed
     * riichi toggle (the widest control the band takes beside the timer); none by default.
     */
    readonly offers: StoryOffers;
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

function parseStoryCall(value: string | null): StoryCall | null {
    return STORY_CALLS.find((call) => call === value) ?? null;
}

/** The seat whose river holds the table's latest discard, else the left one. */
function discarderSeat(state: BoardDisplayState): number {
    const seat = state.players.findIndex((player) =>
        player.discards.some((tile) => tile.last === true),
    );
    return seat === -1 ? DEFAULT_DISCARDER : seat;
}

/** The story's offers that are the viewer's own turn rather than a call prompt on another seat's discard. */
const OWN_TURN_OFFERS: ReadonlySet<StoryOffers> = new Set(["riichi", "bank"]);

/**
 * The story's board, one seat cued in turn while its round plays (the centre's bar and the badge's underline on it
 * alone): the viewer's on its own turn, else the seat whose discard is the latest, as a call prompt on it finds the
 * table. Under a round's result or the game's end the round is over, so, as on the live board, no seat is cued.
 */
function cuedInTurn(state: BoardDisplayState, story: BoardStoryState): BoardDisplayState {
    if (story.overlay !== "none") {
        return state;
    }
    const cued = OWN_TURN_OFFERS.has(story.offers) ? 0 : discarderSeat(state);
    const [bottom, right, top, left] = state.nameplates;
    return {
        ...state,
        nameplates: [
            { ...bottom, isCurrent: cued === 0 },
            { ...right, isCurrent: cued === 1 },
            { ...top, isCurrent: cued === 2 },
            { ...left, isCurrent: cued === 3 },
        ],
    };
}

function storyCalls(
    call: StoryCall,
    state: BoardDisplayState,
): readonly { readonly kind: CalloutKind; readonly seat: number }[] {
    if (call === "every") {
        return EVERY_CALL.map((kind, seat) => ({ kind, seat }));
    }
    const seats = SEAT_POSITIONS.map((_position, seat) => seat);
    if (call === "triple_ron") {
        const discarder = discarderSeat(state);
        return seats.filter((seat) => seat !== discarder).map((seat) => ({ kind: "ron", seat }));
    }
    return seats.map((seat) => ({ kind: call, seat }));
}

/** The story's calls, which the storybook's stylesheet holds still so they can be read and measured. */
function storyCallouts(call: StoryCall | null, state: BoardDisplayState): BoardCallouts | null {
    if (call === null) {
        return null;
    }
    return { items: boardCallouts(storyCalls(call, state), 0), key: call };
}

const STORY_OFFERS = ["none", "five", "riichi", "bank"] as const;

type StoryOffers = (typeof STORY_OFFERS)[number];

const STORY_OFFER_LABELS: Readonly<Record<StoryOffers, string>> = {
    bank: "Offers: turn in bank",
    five: "Offers: five on a discard",
    none: "No offers",
    riichi: "Offers: riichi pressed",
};

function parseStoryOffers(value: string | null): StoryOffers {
    return STORY_OFFERS.find((offers) => offers === value) ?? "none";
}

/** A control of the story's offers: what it answers with and how it ranks, its label and preview faces. */
interface StoryOffer {
    readonly command: PlayCommand;
    readonly rank: ActionRank;
    readonly label: string;
    readonly tiles?: readonly TileFace[];
    readonly pressed?: boolean;
}

function storyControl({ command, label, pressed, rank, tiles }: StoryOffer): DecisionAction {
    return {
        chosen: false,
        command,
        group: null,
        label,
        pressed: pressed ?? null,
        rank,
        tiles: tiles ?? [],
    };
}

function choosing(offer: Offer): PlayCommand {
    return { intent: { offer, type: "choose" }, kind: "intent" };
}

/** A played board's hand input, so a board with offers keeps a played board's row (its furiten slot included). */
const PLAYED_HAND = { onTile: () => {}, tileAction: "Discard" } as const;

/** A discarded 3m's offers: a win, a kan and a pon of it, a chi with a choice of tiles, and a pass. */
function fiveOffers(): DecisionView {
    const tileId = 8;
    return {
        actions: [
            storyControl({ command: choosing({ kind: "ron" }), label: "Ron", rank: "win" }),
            storyControl({
                command: choosing({ kanType: "open", kind: "kan", tileId }),
                label: "Kan",
                rank: "call",
                tiles: ["3m"],
            }),
            storyControl({
                command: choosing({ kind: "pon", tileId }),
                label: "Pon",
                rank: "call",
                tiles: ["3m"],
            }),
            storyControl({
                command: { kind: "toggle_tile_choice", offer: "chi" },
                label: "Chi",
                pressed: false,
                rank: "call",
            }),
            storyControl({
                command: { intent: { type: "pass" }, kind: "intent" },
                label: "Pass",
                rank: "pass",
            }),
        ],
        countdown: { kind: "running", move: "call", secondsLeft: 5, turn: null },
        decisionStanding: "open",
    };
}

/** A turn's riichi toggle, pressed, with its base and bank: the widest control the band takes beside the timer. */
function riichiOffer(): DecisionView {
    return {
        actions: [
            storyControl({
                command: { kind: "toggle_riichi_pick" },
                label: "Riichi",
                pressed: true,
                rank: "call",
            }),
        ],
        countdown: {
            kind: "running",
            move: "turn",
            secondsLeft: 45,
            turn: { bankSeconds: 40, baseSeconds: 5, inBank: false },
        },
        decisionStanding: "open",
    };
}

/** A turn whose base time ran out, its bank draining, with a tsumo, a choice of two kans and riichi to take. */
function bankOffers(): DecisionView {
    return {
        actions: [
            storyControl({ command: choosing({ kind: "tsumo" }), label: "Tsumo", rank: "win" }),
            storyControl({
                command: { kind: "toggle_tile_choice", offer: "kan" },
                label: "Kan",
                pressed: false,
                rank: "call",
            }),
            storyControl({
                command: { kind: "toggle_riichi_pick" },
                label: "Riichi",
                pressed: false,
                rank: "call",
            }),
        ],
        countdown: {
            kind: "running",
            move: "turn",
            secondsLeft: 8,
            turn: { bankSeconds: 8, baseSeconds: 0, inBank: true },
        },
        decisionStanding: "open",
    };
}

/** The decision a story's `?offers=` shows over its board, if any. */
function storyOffers(offers: StoryOffers): DecisionView | null {
    switch (offers) {
        case "five": {
            return fiveOffers();
        }
        case "riichi": {
            return riichiOffer();
        }
        case "bank": {
            return bankOffers();
        }
        case "none": {
            return null;
        }
        default: {
            return assertNever(offers);
        }
    }
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

/** Nine discards, the ninth the table's latest, laid sideways for riichi: a call's chip must lie off its row. */
const riichiLatestRiver: DiscardTile[] = [
    ...fullRiver.slice(0, 8),
    { face: "6s", last: true, riichi: true },
];

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

const THIRTEEN: readonly TileFace[] = [
    "1m",
    "2m",
    "3m",
    "5p",
    "6p",
    "7p",
    "2s",
    "3m",
    "4m",
    "5m",
    "7m",
    "8m",
    "9m",
];

/** A hand of `count` concealed tiles (`3n+1` for its melds), shown as faces or backs, with the drawn tile apart. */
function capacitySeat(
    count: number,
    {
        discards,
        drawn,
        melds,
        show,
    }: {
        readonly discards: readonly DiscardTile[];
        readonly drawn: boolean;
        readonly melds: readonly MeldInput[];
        readonly show: "face" | "back";
    },
): BoardPlayerDisplay {
    return {
        discards,
        drawnTile: drawn ? { face: "6z", show } : undefined,
        hand: THIRTEEN.slice(0, count).map((face) => ({ face, show })),
        melds: laid(melds),
    };
}

/** `count` melds for `seat`, every one a kan, an added kan first: the longest and deepest lines a count can lay. */
function kanMelds(seat: number, count: number): MeldInput[] {
    const [closed, open, added] = fourMelds(seat);
    return [added, open, closed].slice(0, count);
}

/** A seat's legal mixed hand at its turn: `count` melds and the thirteen less three a meld, plus the drawn tile. */
function mixedSeat(seat: number, count: number): BoardPlayerDisplay {
    return capacitySeat(13 - 3 * count, {
        discards: fullRiver.slice(0, 10),
        drawn: true,
        melds: kanMelds(seat, count),
        show: "face",
    });
}

/** Each seat's meld count, bottom, right, top and left, in the three mixed stories. */
function mixedHands(counts: readonly [number, number, number, number]): BoardDisplayState {
    return {
        center: mockCenter,
        nameplates: riverPlates,
        players: [
            mixedSeat(0, counts[0]),
            mixedSeat(1, counts[1]),
            mixedSeat(2, counts[2]),
            mixedSeat(3, counts[3]),
        ],
    };
}

function worstSeat(seat: number, discards: readonly DiscardTile[] = longRiver): BoardPlayerDisplay {
    return {
        discards,
        drawnTile: { face: "6z", show: "face" },
        hand: [{ face: "2s", show: "face" }],
        melds: laid(fourMelds(seat)),
    };
}

/** How many places on from the caller a feeder sits: the next seat is on its right, the one before on its left. */
const FROM_RIGHT = 1;
const FROM_ACROSS = 2;
const FROM_LEFT = 3;

/** A kan's kind and, for an open or added one, how many places on from the caller its feeder sits. */
type KanFeed = readonly ["closed_kan"] | readonly ["open_kan" | "added_kan", number];

/** A kan for `seat` of the four tiles from `first`, a closed one or fed from the seat its feed names. */
function feedKan(seat: number, feed: KanFeed, first: number): MeldInput {
    const tileIds = [first, first + 1, first + 2, first + 3];
    if (feed[0] === "closed_kan") {
        return {
            calledTileId: null,
            callerSeat: seat,
            fromSeat: null,
            meldType: "closed_kan",
            tileIds,
        };
    }
    const [meldType, offset] = feed;
    return {
        ...(meldType === "added_kan" ? { addedTileId: first + 3 } : {}),
        calledTileId: first + 1,
        callerSeat: seat,
        fromSeat: (seat + offset) % 4,
        meldType,
        tileIds,
    };
}

/** The ids between one kan's first tile and the next's: a kind of tile apart, so each kan shows its own face. */
const KAN_IDS_APART = 36;

/** A kan per feed for `seat`, oldest first. */
function kansOf(seat: number, feeds: readonly KanFeed[]): MeldInput[] {
    return feeds.map((feed, index) => feedKan(seat, feed, KAN_IDS_APART * index));
}

/** Every kan kind a seat, whose open and added kans between A and B come from each feeder at every seat. */
const KANS_A_FEEDS: readonly KanFeed[] = [
    ["closed_kan"],
    ["open_kan", FROM_LEFT],
    ["open_kan", FROM_ACROSS],
    ["added_kan", FROM_RIGHT],
];

const KANS_B_FEEDS: readonly KanFeed[] = [
    ["closed_kan"],
    ["added_kan", FROM_LEFT],
    ["added_kan", FROM_ACROSS],
    ["open_kan", FROM_RIGHT],
];

/** Four open kans, the longest four melds a strip can lay (each four tiles, one sideways). */
const KANS_C_FEEDS: readonly KanFeed[] = [
    ["open_kan", FROM_LEFT],
    ["open_kan", FROM_ACROSS],
    ["open_kan", FROM_RIGHT],
    ["open_kan", FROM_LEFT],
];

/**
 * Four kans a seat, one concealed tile and the drawn one beside a 24-tile river, with the worst case's long names and
 * five dora: `show` the opponents' hands, `latest` the seat whose river holds the latest discard.
 */
function kanStory(
    feeds: readonly KanFeed[],
    { latest, show }: { readonly latest: number; readonly show: "face" | "back" },
): BoardDisplayState {
    function seat(index: number): BoardPlayerDisplay {
        return capacitySeat(1, {
            discards: index === latest ? latestRiver : longRiver,
            drawn: true,
            melds: kansOf(index, feeds),
            show: index === 0 ? "face" : show,
        });
    }
    return {
        center: {
            ...mockCenter,
            doraIndicators: ["5m", "3p", "7s", "2z", "9m"],
            tilesRemaining: 0,
        },
        nameplates: worstPlates,
        players: [seat(0), seat(1), seat(2), seat(3)],
    };
}

const BOARD_STATES: Readonly<Record<BoardStory, BoardDisplayState>> = {
    concealed_hands: {
        center: mockCenter,
        nameplates: riverPlates,
        players: [
            capacitySeat(13, {
                discards: fullRiver.slice(0, 9),
                drawn: true,
                melds: [],
                show: "face",
            }),
            capacitySeat(13, {
                discards: fullRiver.slice(0, 9),
                drawn: false,
                melds: [],
                show: "back",
            }),
            capacitySeat(13, {
                discards: fullRiver.slice(0, 9),
                drawn: false,
                melds: [],
                show: "back",
            }),
            capacitySeat(13, {
                discards: riichiLatestRiver,
                drawn: false,
                melds: [],
                show: "back",
            }),
        ],
    },
    full_hands: {
        center: { ...mockCenter, tilesRemaining: 0 },
        nameplates: riverPlates,
        players: [
            capacitySeat(13, { discards: longRiver, drawn: true, melds: [], show: "face" }),
            capacitySeat(13, { discards: longRiver, drawn: true, melds: [], show: "face" }),
            capacitySeat(13, { discards: longRiver, drawn: true, melds: [], show: "face" }),
            capacitySeat(13, { discards: latestRiver, drawn: true, melds: [], show: "face" }),
        ],
    },
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
    kans_a: kanStory(KANS_A_FEEDS, { latest: 2, show: "back" }),
    kans_b: kanStory(KANS_B_FEEDS, { latest: 1, show: "face" }),
    kans_c: kanStory(KANS_C_FEEDS, { latest: 3, show: "back" }),
    mixed_hands_a: mixedHands([1, 3, 2, 1]),
    mixed_hands_b: mixedHands([2, 2, 1, 3]),
    mixed_hands_c: mixedHands([3, 1, 3, 2]),
    riichi_latest: {
        center: mockCenter,
        nameplates: riverPlates,
        players: [
            { ...bottomPlayer, discards: riichiLatestRiver, hand: thirteenFaces, melds: [] },
            { ...rightPlayer, discards: fullRiver.slice(0, 9), hand: thirteenFaces, melds: [] },
            { ...topPlayer, discards: fullRiver.slice(0, 9), hand: thirteenFaces, melds: [] },
            { ...leftPlayer, discards: fullRiver.slice(0, 9), hand: thirteenFaces, melds: [] },
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

const END_PLAYERS: readonly PlayerState[] = [
    createInitialPlayerState({ isAiPlayer: false, name: "You", score: 39_500, seat: 0 }),
    createInitialPlayerState({ isAiPlayer: true, name: "Bot South", score: 12_000, seat: 1 }),
    createInitialPlayerState({ isAiPlayer: true, name: "Bot West", score: 29_100, seat: 2 }),
    createInitialPlayerState({ isAiPlayer: true, name: "Bot North", score: 19_400, seat: 3 }),
];

/** A short East-only game's end, ranked as the server ranks it with uma and oka, a riichi stick left to the winner. */
const END_TABLE: TableState = {
    ...createInitialTableState(),
    dealerSeat: 3,
    gameEndResult: {
        endCause: GAME_END_CAUSE.LENGTH,
        leftoverRiichiBonus: 1000,
        leftoverSticks: 1,
        standings: [
            { finalScore: 50, score: 39_500, seat: 0 },
            { finalScore: 9, score: 29_100, seat: 2 },
            { finalScore: -21, score: 19_400, seat: 3 },
            { finalScore: -38, score: 12_000, seat: 1 },
        ],
        winnerSeat: 0,
    },
    phase: "game_ended",
    players: END_PLAYERS,
    riichiCost: 1000,
};

/** The same game under rules that award the leftover stick to nobody: the winner's score never took it. */
const END_TABLE_STICK_LOST: TableState = {
    ...END_TABLE,
    gameEndResult: {
        endCause: GAME_END_CAUSE.LENGTH,
        leftoverRiichiBonus: 0,
        leftoverSticks: 1,
        standings: [
            { finalScore: 49, score: 38_500, seat: 0 },
            { finalScore: 9, score: 29_100, seat: 2 },
            { finalScore: -21, score: 19_400, seat: 3 },
            { finalScore: -38, score: 12_000, seat: 1 },
        ],
        winnerSeat: 0,
    },
};

function gameEndActions(): readonly PanelAction[] {
    return [
        {
            href: storybookHref("/play/storybook/replay?state=game_end", window.location.search),
            kind: "link",
            label: "Replay",
        },
        { href: storybookIndexHref(), kind: "link", label: "Storybook", primary: true },
    ];
}

function buildOverlay(
    story: BoardStoryState,
    handlers: BoardStoryHandlers,
): TemplateResult | undefined {
    const { overlay } = story;
    if (overlay === "round_end") {
        return RoundEndDisplay({
            display: roundEndDisplay(resultStoryTable(story.result), story.page),
            onPage: handlers.showPage,
        });
    }
    if (overlay === "game_end") {
        return boardOverlay(story.leftoverLost ? END_TABLE_STICK_LOST : END_TABLE, {
            end: { actions: gameEndActions(), viewerSeat: 0 },
        });
    }
    return undefined;
}

interface BoardStoryHandlers {
    readonly showStory: (story: string) => void;
    readonly showResult: (result: string) => void;
    readonly showPage: (page: number) => void;
    readonly showCallout: (call: string) => void;
    readonly showOffers: (offers: string) => void;
    readonly pin: (seat: SeatPosition | null) => void;
    readonly toggleDebug: () => void;
    readonly toggleOverlay: (mode: OverlayMode) => void;
    readonly openNotice: (open: boolean) => void;
}

function activeClass(active: boolean): string {
    return active ? "board-storybook__btn--active" : "";
}

interface PickerOption {
    readonly value: string;
    readonly label: string;
}

/** A select among a story's options, labelled for assistive technology, handing the picked value on. */
function storyPicker({
    label,
    onPick,
    options,
    selected,
}: {
    readonly label: string;
    readonly options: readonly PickerOption[];
    readonly selected: string;
    readonly onPick: (value: string) => void;
}): TemplateResult {
    return html`<div class="board-storybook__picker"><select
        class="board-storybook__select"
        aria-label=${label}
        @change=${(event: Event) => {
            const { target } = event;
            if (target instanceof HTMLSelectElement) {
                onPick(target.value);
            }
        }}
    >
        ${options.map(
            ({ label: text, value }) =>
                html`<option value=${value} ?selected=${value === selected}>${text}</option>`,
        )}
    </select></div>`;
}

const STORY_OPTIONS: readonly PickerOption[] = BOARD_STORIES.map((value) => ({
    label: BOARD_STORY_LABELS[value],
    value,
}));

const RESULT_OPTIONS: readonly PickerOption[] = RESULT_STORIES.map((value) => ({
    label: resultStoryLabel(value),
    value,
}));

const CALL_OPTIONS: readonly PickerOption[] = [
    { label: "No call", value: "" },
    ...STORY_CALLS.map((value) => ({ label: STORY_CALL_LABELS[value], value })),
];

const OFFER_OPTIONS: readonly PickerOption[] = STORY_OFFERS.map((value) => ({
    label: STORY_OFFER_LABELS[value],
    value,
}));

/** The story's notices: its long notice, which opens whole in its sheet; none without `?notice=long`. */
function storyNotices(
    story: BoardStoryState,
    handlers: BoardStoryHandlers,
): BoardNotice[] | undefined {
    if (!story.notice) {
        return undefined;
    }
    return [
        {
            id: "long",
            onShowAll: () => handlers.openNotice(true),
            text: LONG_NOTICE_TEXT,
            tone: "error",
        },
    ];
}

/** The long notice opened whole over the board, which the board's caller makes inert beneath it. */
function noticeSheetOverlay(
    notices: readonly BoardNotice[] | undefined,
    handlers: BoardStoryHandlers,
): TemplateResult | undefined {
    const [notice] = notices ?? [];
    if (notice?.id === undefined) {
        return undefined;
    }
    return NoticeSheet({
        note: html`<p class="notice-sheet__note">Play goes on beneath this sheet.</p>`,
        notices: [notice],
        onClose: () => handlers.openNotice(false),
        openerId: notice.id,
    });
}

function storybookBoardTemplate(
    story: BoardStoryState,
    handlers: BoardStoryHandlers,
): TemplateResult {
    const state = cuedInTurn(BOARD_STATES[story.story], story);
    const offers = storyOffers(story.offers);
    const notices = storyNotices(story, handlers);
    const sheet = story.noticeOpen ? noticeSheetOverlay(notices, handlers) : undefined;
    return html`
        <div class="board-page board-storybook">
            <div class="board-page__board">
                ${GameBoard({
                    actions: offers === null ? undefined : DecisionControls(offers, () => {}),
                    callouts: storyCallouts(story.callout, state),
                    debug: story.debug,
                    inert: sheet !== undefined,
                    localHand:
                        offers !== null || PLAYED_ROW_STORIES.has(story.story)
                            ? PLAYED_HAND
                            : undefined,
                    notices,
                    overlay: sheet ?? buildOverlay(story, handlers),
                    platePress: { kind: "pin", onPin: handlers.pin, pinned: story.pinned },
                    state,
                })}
            </div>
            <div class="board-page__aside">
                <a class="board-storybook__btn" href="${storybookIndexHref()}">Back</a>
                ${storyPicker({
                    label: "Story",
                    onPick: handlers.showStory,
                    options: STORY_OPTIONS,
                    selected: story.story,
                })}
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
                        ? storyPicker({
                              label: "Round result",
                              onPick: handlers.showResult,
                              options: RESULT_OPTIONS,
                              selected: story.result,
                          })
                        : ""
                }
                <button
                    class="board-storybook__btn ${activeClass(story.overlay === "game_end")}"
                    @click=${() => handlers.toggleOverlay("game_end")}
                >Game end</button>
                ${storyPicker({
                    label: "Call shown",
                    onPick: handlers.showCallout,
                    options: CALL_OPTIONS,
                    selected: story.callout ?? "",
                })}
                ${storyPicker({
                    label: "Offers shown",
                    onPick: handlers.showOffers,
                    options: OFFER_OPTIONS,
                    selected: story.offers,
                })}
            </div>
        </div>
    `;
}

/** Mount the board storybook into `host`; its story and overlay are kept in the page's `?state=` and `?overlay=`. */
export function mountStorybookBoard(host: HTMLElement): () => void {
    const query = new URLSearchParams(window.location.search);
    let story: BoardStoryState = {
        callout: parseStoryCall(query.get("callout")),
        debug: false,
        leftoverLost: query.get("leftover") === "lost",
        notice: query.get("notice") === "long",
        noticeOpen: false,
        offers: parseStoryOffers(query.get("offers")),
        overlay: parseOverlayParam(window.location.search),
        page: parsePageParam(window.location.search),
        pinned: parsePinParam(window.location.search),
        result: parseResultParam(window.location.search),
        story: parseStoryParam(window.location.search),
    };

    function show(next: BoardStoryState): void {
        story = next;
        render(storybookBoardTemplate(story, handlers), host);
    }

    const handlers: BoardStoryHandlers = {
        openNotice: (open) => show({ ...story, noticeOpen: open }),
        pin(seat) {
            syncQueryParam("pin", seat ?? "", "");
            show({ ...story, pinned: seat });
        },
        showCallout(value) {
            const callout = parseStoryCall(value);
            syncQueryParam("callout", callout ?? "", "");
            show({ ...story, callout });
        },
        showOffers(value) {
            const offers = parseStoryOffers(value);
            syncQueryParam("offers", offers, "none");
            show({ ...story, offers });
        },
        showPage(page) {
            syncQueryParam("page", String(page), "0");
            show({ ...story, page });
        },
        showResult(value) {
            const result = RESULT_STORIES.find((candidate) => candidate === value);
            if (result === undefined) {
                return;
            }
            syncQueryParam("result", result, DEFAULT_RESULT);
            syncQueryParam("page", "0", "0");
            show({ ...story, page: 0, result });
        },
        showStory(value) {
            const key = BOARD_STORIES.find((candidate) => candidate === value);
            if (key === undefined) {
                return;
            }
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
