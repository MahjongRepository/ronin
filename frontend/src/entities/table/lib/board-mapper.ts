import { windName } from "@/entities/table/lib/wind-name";
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
    return score.toLocaleString("en-US");
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

function mapPlayerDisplay(player: PlayerState, position: SeatPosition): BoardPlayerDisplay {
    const show = position === "bottom" ? "face" : "back";
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
        wind: windName((player.seat - state.dealerSeat + 4) % 4),
    };
}

// Normalize players by seat index into a fixed [bottom, right, top, left] tuple.
// Handles unsorted arrays and incomplete states (< 4 players) gracefully.
function normalizeBySeat(
    players: PlayerState[],
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
        if (p.seat >= 0 && p.seat < REQUIRED_PLAYERS) {
            slots[p.seat] = p;
        }
    }
    return slots;
}

function tableStateToDisplayState(state: TableState): BoardDisplayState | null {
    if (state.players.length !== REQUIRED_PLAYERS) {
        return null;
    }

    const seats = normalizeBySeat(state.players);

    const players = SEAT_POSITIONS.map((pos, i) => {
        const p = seats[i];
        return p ? mapPlayerDisplay(p, pos) : EMPTY_PLAYER;
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
        },
        players,
    };
}

export { formatScore, tableStateToDisplayState };
