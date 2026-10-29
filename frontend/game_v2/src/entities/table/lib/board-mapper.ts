import { roundName } from "@/entities/table/lib/round-name";
import { windLetter } from "@/entities/table/lib/wind-name";
import {
    type BoardDisplayState,
    type BoardPerspective,
    type BoardPlayerDisplay,
    type BoardPlayerScore,
} from "@/entities/table/model/board-types";
import { roundInWind } from "@/entities/table/model/helpers";
import { type PlayerState, type TableState } from "@/entities/table/model/types";
import { type DiscardTile, type HandTile, meldTiles, tile136toString } from "@/entities/tile";

const REQUIRED_PLAYERS = 4;

type SeatSlots = readonly [
    PlayerState | undefined,
    PlayerState | undefined,
    PlayerState | undefined,
    PlayerState | undefined,
];

const CONCEALED_TILE: HandTile = { show: "concealed" };

function formatScore(score: number): string {
    return String(score);
}

function toHandTile(tileId: number, show: "face" | "back"): HandTile {
    return { face: tile136toString(tileId), show, tileId };
}

/** The hand row and the drawn tile apart from it; the drawn tile is the first copy of its id. */
function buildHandTiles(
    player: PlayerState,
    show: "face" | "back",
): { baseTiles: HandTile[]; drawnTile: HandTile | undefined } {
    const drawnIndex = player.drawnTileId === null ? -1 : player.tiles.indexOf(player.drawnTileId);
    const known = player.tiles
        .filter((_tileId, index) => index !== drawnIndex)
        .map((tileId) => toHandTile(tileId, show));
    const concealed = Array.from({ length: player.concealedCount }, () => CONCEALED_TILE);
    return {
        baseTiles: [...known, ...concealed],
        drawnTile: drawnIndex === -1 ? undefined : toHandTile(player.tiles[drawnIndex], show),
    };
}

/**
 * The river's sideways tile: the riichi declaration's discard, or when another seat called it, the declarer's first
 * discard after it that stayed in the river.
 */
function sidewaysDiscardIndex(discards: PlayerState["discards"]): number {
    const declared = discards.findIndex((discard) => discard.isRiichi);
    if (declared === -1) {
        return -1;
    }
    return discards.findIndex((discard, index) => index >= declared && discard.claimed !== true);
}

function buildDiscardTiles(player: PlayerState): DiscardTile[] {
    const sideways = sidewaysDiscardIndex(player.discards);
    return player.discards.map((d, index) => ({
        face: tile136toString(d.tileId),
        grayed: d.claimed,
        riichi: index === sideways,
    }));
}

const EMPTY_PLAYER: BoardPlayerDisplay = {
    discards: [],
    drawnTile: undefined,
    hand: [],
    melds: [],
};

const EMPTY_SCORE: BoardPlayerScore = {
    aiStandIn: false,
    isCurrent: false,
    isDealer: false,
    isRiichi: false,
    score: "0",
    wind: "",
};

function mapPlayerDisplay(
    player: PlayerState,
    atBottom: boolean,
    perspective: BoardPerspective,
): BoardPlayerDisplay {
    const show = perspective.reveal === "all" || atBottom ? "face" : "back";
    const { baseTiles, drawnTile } = buildHandTiles(player, show);

    return {
        discards: buildDiscardTiles(player),
        drawnTile,
        hand: baseTiles,
        melds: player.melds.map(meldTiles),
    };
}

function mapPlayerScore(player: PlayerState, state: TableState): BoardPlayerScore {
    return {
        aiStandIn: player.aiStandIn !== null,
        isCurrent: player.seat === state.currentPlayerSeat,
        isDealer: player.seat === state.dealerSeat,
        isRiichi: player.isRiichi,
        score: formatScore(player.score),
        wind: windLetter((player.seat - state.dealerSeat + 4) % 4),
    };
}

/** The players by board position: the perspective's seat at the bottom, then the next seats right, top, left. */
function slotsFrom(players: readonly PlayerState[], bottomSeat: number): SeatSlots {
    for (const p of players) {
        if (p.seat < 0 || p.seat >= REQUIRED_PLAYERS) {
            throw new Error(`Invalid seat ${p.seat}, expected 0–${REQUIRED_PLAYERS - 1}`);
        }
    }
    function slotOf(position: number): PlayerState | undefined {
        return players.find((p) => p.seat === (bottomSeat + position) % REQUIRED_PLAYERS);
    }
    return [slotOf(0), slotOf(1), slotOf(2), slotOf(3)];
}

/** The board as `perspective` sees the table, or null until the table seats four players. */
function tableStateToDisplayState(
    state: TableState,
    perspective: BoardPerspective,
): BoardDisplayState | null {
    if (state.players.length !== REQUIRED_PLAYERS) {
        return null;
    }

    const [bottom, right, top, left] = slotsFrom(state.players, perspective.bottomSeat);
    function display(player: PlayerState | undefined, atBottom: boolean): BoardPlayerDisplay {
        return player ? mapPlayerDisplay(player, atBottom, perspective) : EMPTY_PLAYER;
    }
    function score(player: PlayerState | undefined): BoardPlayerScore {
        return player ? mapPlayerScore(player, state) : EMPTY_SCORE;
    }

    return {
        center: {
            doraIndicators: state.doraIndicators.map((id) => tile136toString(id)),
            honbaSticks: state.honbaSticks,
            riichiSticks: state.riichiSticks,
            roundDisplay: roundName(state.roundWind, roundInWind(state)),
            scores: [score(bottom), score(right), score(top), score(left)],
            tilesRemaining: state.tilesRemaining,
        },
        players: [
            display(bottom, true),
            display(right, false),
            display(top, false),
            display(left, false),
        ],
    };
}

export { formatScore, tableStateToDisplayState };
