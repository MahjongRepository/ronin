import { roundName } from "@/entities/table/lib/round-name";
import { windLetter, windName } from "@/entities/table/lib/wind-name";
import {
    type BoardDisplayState,
    type BoardNameplate,
    type BoardPerspective,
    type BoardPlayerDisplay,
    type NameplateAiMark,
} from "@/entities/table/model/board-types";
import { roundInWind } from "@/entities/table/model/helpers";
import { type PlayerState, type TableState } from "@/entities/table/model/types";
import { type DiscardTile, type HandTile, meldTiles, tile136toString } from "@/entities/tile";
import { SEAT_CONTROL_REASON, seatDistance } from "@/shared/protocol";

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

/**
 * The hand row, sorted whatever order the table holds its tiles in (a draw's arrival, a result's reveal), and the
 * drawn tile apart from it: the first copy of its id, or the face-down draw a notice announced.
 */
function buildHandTiles(
    player: PlayerState,
    show: "face" | "back",
): { baseTiles: HandTile[]; drawnTile: HandTile | undefined } {
    const drawnIndex = player.drawnTileId === null ? -1 : player.tiles.indexOf(player.drawnTileId);
    const known = player.tiles
        .filter((_tileId, index) => index !== drawnIndex)
        .toSorted((first, second) => first - second)
        .map((tileId) => toHandTile(tileId, show));
    const concealedDrawn = drawnIndex === -1 && player.drawnConcealed && player.concealedCount > 0;
    const concealed = Array.from(
        { length: player.concealedCount - (concealedDrawn ? 1 : 0) },
        () => CONCEALED_TILE,
    );
    const knownDrawn = drawnIndex === -1 ? undefined : toHandTile(player.tiles[drawnIndex], show);
    return {
        baseTiles: [...known, ...concealed],
        drawnTile: concealedDrawn ? CONCEALED_TILE : knownDrawn,
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

/**
 * The river as it lies: a tile another seat claimed has left it for the meld that took it. Its riichi tile lies
 * sideways and, when the table's latest discard is this seat's, that tile is marked.
 */
export function buildDiscardTiles(
    player: PlayerState,
    lastDiscardSeat: number | null,
): DiscardTile[] {
    const sideways = sidewaysDiscardIndex(player.discards);
    const last = player.seat === lastDiscardSeat ? player.discards.length - 1 : -1;
    return player.discards.flatMap((d, index) =>
        d.claimed === true
            ? []
            : [
                  {
                      face: tile136toString(d.tileId),
                      last: index === last,
                      riichi: index === sideways,
                  },
              ],
    );
}

const EMPTY_PLAYER: BoardPlayerDisplay = {
    discards: [],
    drawnTile: undefined,
    hand: [],
    melds: [],
};

function mapPlayerDisplay(
    player: PlayerState,
    atBottom: boolean,
    { perspective, state }: { perspective: BoardPerspective; state: TableState },
): BoardPlayerDisplay {
    const shown =
        perspective.reveal === "all" || atBottom || state.revealedSeats.includes(player.seat);
    const show = shown ? "face" : "back";
    const { baseTiles, drawnTile } = buildHandTiles(player, show);

    return {
        discards: buildDiscardTiles(player, state.lastDiscardSeat),
        drawnTile,
        hand: baseTiles,
        melds: player.melds.map(meldTiles),
    };
}

/** How far `score` is from `from`, signed: `+1000`, `-3000`, or `±0`. */
function formatScoreDiff(score: number, from: number): string {
    const diff = score - from;
    if (diff === 0) {
        return "±0";
    }
    return diff > 0 ? `+${formatScore(diff)}` : formatScore(diff);
}

/**
 * Why an AI player marks the seat: one holding it for its human, as the seat control lines and session messages say,
 * else one the source names as AI. A reconnect's snapshot names an AI player whether it was seated from the start or
 * stands in for a human, so its word says only that one plays the seat.
 */
function aiMark(player: PlayerState): NameplateAiMark | null {
    if (player.aiStandIn === SEAT_CONTROL_REASON.LEFT) {
        return { tag: "Away", words: "Disconnected: an AI player plays this seat" };
    }
    if (player.aiStandIn === SEAT_CONTROL_REASON.ABSENT) {
        return { tag: "Away", words: "Absent: an AI player plays this seat" };
    }
    return player.isAiPlayer ? { tag: "AI", words: "An AI player plays this seat" } : null;
}

const EMPTY_NAMEPLATE: BoardNameplate = {
    aiMark: null,
    isCurrent: false,
    isDealer: false,
    isRiichi: false,
    name: "",
    score: "",
    scoreDiffs: { bottom: "", left: "", right: "", top: "" },
    wind: "",
    windName: "",
};

function mapNameplate(player: PlayerState, slots: SeatSlots, state: TableState): BoardNameplate {
    function diffFrom(other: PlayerState | undefined): string {
        return other === undefined || other === player
            ? ""
            : formatScoreDiff(player.score, other.score);
    }
    const [bottom, right, top, left] = slots;
    const wind = seatDistance(state.dealerSeat, player.seat);
    return {
        aiMark: aiMark(player),
        isCurrent: state.phase === "in_round" && player.seat === state.currentPlayerSeat,
        isDealer: player.seat === state.dealerSeat,
        isRiichi: player.isRiichi,
        name: player.name,
        score: formatScore(player.score),
        scoreDiffs: {
            bottom: diffFrom(bottom),
            left: diffFrom(left),
            right: diffFrom(right),
            top: diffFrom(top),
        },
        wind: windLetter(wind),
        windName: windName(wind),
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

    const slots = slotsFrom(state.players, perspective.bottomSeat);
    const [bottom, right, top, left] = slots;
    function display(player: PlayerState | undefined, atBottom: boolean): BoardPlayerDisplay {
        return player ? mapPlayerDisplay(player, atBottom, { perspective, state }) : EMPTY_PLAYER;
    }
    function nameplate(player: PlayerState | undefined): BoardNameplate {
        return player ? mapNameplate(player, slots, state) : EMPTY_NAMEPLATE;
    }

    return {
        center: {
            doraIndicators: state.doraIndicators.map((id) => tile136toString(id)),
            honbaSticks: state.honbaSticks,
            riichiSticks: state.riichiSticks,
            roundDisplay: roundName(state.roundWind, roundInWind(state)),
            tilesRemaining: state.tilesRemaining,
        },
        nameplates: [nameplate(bottom), nameplate(right), nameplate(top), nameplate(left)],
        players: [
            display(bottom, true),
            display(right, false),
            display(top, false),
            display(left, false),
        ],
    };
}

export { tableStateToDisplayState };
