import { windLetter, windName } from "@/entities/table/lib/wind-name";
import {
    type BoardCenterInfo,
    type BoardDisplayState,
    type BoardPlayerDisplay,
    type BoardPlayerScore,
    SEAT_POSITIONS,
    type SeatPosition,
} from "@/entities/table/model/board-types";
import { type PlayerState, type TableState } from "@/entities/table/model/types";
import { type DiscardTile, type HandTile, tile136toString } from "@/entities/tile";

const REQUIRED_PLAYERS = 4;

function formatScore(score: number): string {
    return String(score);
}

function toHandTile(tileId: number, show: "face" | "back"): HandTile {
    return { face: tile136toString(tileId), show };
}

function separateDrawnTile(
    tiles: number[],
    drawnTileId: number,
    show: "face" | "back",
): { baseTiles: HandTile[]; drawnTile: HandTile | undefined } {
    const baseTiles: HandTile[] = [];
    let drawnTile: HandTile | undefined = undefined;
    for (const tileId of tiles) {
        if (!drawnTile && tileId === drawnTileId) {
            drawnTile = toHandTile(tileId, show);
        } else {
            baseTiles.push(toHandTile(tileId, show));
        }
    }
    return { baseTiles, drawnTile };
}

function buildHandTiles(
    player: PlayerState,
    show: "face" | "back",
): { baseTiles: HandTile[]; drawnTile: HandTile | undefined } {
    if (player.drawnTileId !== null) {
        return separateDrawnTile(player.tiles, player.drawnTileId, show);
    }
    return {
        baseTiles: player.tiles.map((id) => toHandTile(id, show)),
        drawnTile: undefined,
    };
}

function buildDiscardTiles(player: PlayerState): DiscardTile[] {
    return player.discards.map((d) => ({
        face: tile136toString(d.tileId),
        grayed: d.claimed,
        riichi: d.isRiichi,
    }));
}

const EMPTY_PLAYER: BoardPlayerDisplay = {
    discards: [],
    drawnTile: undefined,
    hand: [],
    melds: [],
};

const EMPTY_SCORE: BoardPlayerScore = {
    isCurrent: false,
    isDealer: false,
    isRiichi: false,
    score: "0",
    wind: "",
};

function mapPlayerDisplay(
    player: PlayerState,
    position: SeatPosition,
    allOpen: boolean,
): BoardPlayerDisplay {
    const show = allOpen || position === "bottom" ? "face" : "back";
    const { baseTiles, drawnTile } = buildHandTiles(player, show);

    return {
        discards: buildDiscardTiles(player),
        drawnTile,
        hand: baseTiles,
        melds: player.melds,
    };
}

function mapPlayerScore(player: PlayerState, state: TableState): BoardPlayerScore {
    return {
        isCurrent: player.seat === state.currentPlayerSeat,
        isDealer: player.seat === state.dealerSeat,
        isRiichi: player.isRiichi,
        score: formatScore(player.score),
        wind: windLetter((player.seat - state.dealerSeat + 4) % 4),
    };
}

// Rotate players so the dealer sits at bottom, then clockwise: right, top, left.
// Handles unsorted arrays and incomplete states (< 4 players) gracefully.
function normalizeBySeat(
    players: PlayerState[],
    dealerSeat: number,
): [
    PlayerState | undefined,
    PlayerState | undefined,
    PlayerState | undefined,
    PlayerState | undefined,
] {
    const slots: [
        PlayerState | undefined,
        PlayerState | undefined,
        PlayerState | undefined,
        PlayerState | undefined,
    ] = [undefined, undefined, undefined, undefined];
    for (const p of players) {
        if (p.seat < 0 || p.seat >= REQUIRED_PLAYERS) {
            throw new Error(`Invalid seat ${p.seat}, expected 0–${REQUIRED_PLAYERS - 1}`);
        }
        const position = (p.seat - dealerSeat + REQUIRED_PLAYERS) % REQUIRED_PLAYERS;
        slots[position] = p;
    }
    return slots;
}

interface DisplayOptions {
    allOpen?: boolean;
}

function tableStateToDisplayState(
    state: TableState,
    options: DisplayOptions = {},
): BoardDisplayState | null {
    if (state.players.length !== REQUIRED_PLAYERS) {
        return null;
    }

    const { allOpen = false } = options;
    const seats = normalizeBySeat(state.players, state.dealerSeat);

    const players = SEAT_POSITIONS.map((pos, i) => {
        const p = seats[i];
        return p ? mapPlayerDisplay(p, pos, allOpen) : EMPTY_PLAYER;
    }) as BoardDisplayState["players"];

    const scores = seats.map((p) =>
        p ? mapPlayerScore(p, state) : EMPTY_SCORE,
    ) as BoardCenterInfo["scores"];

    return {
        center: {
            doraIndicators: state.doraIndicators.map((id) => tile136toString(id)),
            honbaSticks: state.honbaSticks,
            riichiSticks: state.riichiSticks,
            roundDisplay: `${windName(state.roundWind)} ${state.roundNumber}`,
            scores,
            tilesRemaining: state.tilesRemaining,
        },
        players,
    };
}

export { formatScore, tableStateToDisplayState };
