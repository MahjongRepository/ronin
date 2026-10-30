import { createInitialPlayerState } from "@/entities/table/model/initial-state";
import {
    type DiscardRecord,
    type MeldRecord,
    type PlayerState,
    type TableState,
} from "@/entities/table/model/types";
import { type GameReconnectedEvent, decodeMeldCompact } from "@/shared/protocol";

import { extractRoundEndResult, revealHands, showRobbedKan } from "./round-end";
import { roundRecordOfHistory } from "./round-record";

type SnapshotSeat = GameReconnectedEvent["playerStates"][number];

/** The tile each seat lost to a call, keyed `seat:tileId`, so its river shows it claimed. */
function claimedDiscardKeys(melds: readonly MeldRecord[]): ReadonlySet<string> {
    return new Set(
        melds
            .filter((meld) => meld.fromSeat !== null && meld.calledTileId !== null)
            .map((meld) => `${meld.fromSeat}:${meld.calledTileId}`),
    );
}

function snapshotDiscards(
    seat: SnapshotSeat | undefined,
    claimed: ReadonlySet<string>,
): DiscardRecord[] {
    if (seat === undefined) {
        return [];
    }
    return seat.discards.map((discard) => ({
        claimed: claimed.has(`${seat.seat}:${discard.tileId}`),
        isRiichi: discard.isRiichiDiscard,
        isTsumogiri: discard.isTsumogiri,
        tileId: discard.tileId,
    }));
}

/**
 * One seat of the snapshot: the reconnected seat's own hand by its tiles, every other by its closed-hand count,
 * since the snapshot shows other hands face down.
 */
function snapshotPlayer(
    snapshot: GameReconnectedEvent,
    info: GameReconnectedEvent["players"][number],
    claimed: ReadonlySet<string>,
): PlayerState {
    const seatState = snapshot.playerStates.find((state) => state.seat === info.seat);
    const isViewer = info.seat === snapshot.seat;
    return {
        ...createInitialPlayerState({ ...info, score: seatState?.score ?? 0 }),
        aiStandIn: info.aiStandIn,
        concealedCount: isViewer ? 0 : (seatState?.tileCount ?? 0),
        discards: snapshotDiscards(seatState, claimed),
        isRiichi: seatState?.isRiichi ?? false,
        melds: (seatState?.melds ?? []).map(decodeMeldCompact),
        tiles: isViewer ? snapshot.myTiles : [],
    };
}

/**
 * The game's first dealer: the dealer of the first round the snapshot's history lists, or while no round has ended
 * yet, the dealer of the round in play.
 */
function snapshotFirstDealer(snapshot: GameReconnectedEvent): number {
    return snapshot.roundHistory[0]?.dealerSeat ?? snapshot.dealerSeat;
}

/**
 * Rebuild the table from a reconnect snapshot, its latest discard marked where the snapshot names it. It opens
 * no wait: when the game awaits the seat, the server re-sends the event that opened it. A snapshot taken during a round advance shows the round that ended, with its result, the
 * hands it reveals, and the kan its win robbed as declared: the server never completes a robbed kan, so the snapshot's hand still holds its
 * tiles. Its scores and riichi sticks already hold every accepted riichi's deposit, so the table takes them as they are.
 * Its round history lists every finished round, the one whose result it shows included, which the table takes whole.
 */
export function applyGameReconnected(
    state: TableState,
    snapshot: GameReconnectedEvent,
): TableState {
    const allMelds = snapshot.playerStates.flatMap((seat) => seat.melds.map(decodeMeldCompact));
    const claimed = claimedDiscardKeys(allMelds);
    const { roundResult } = snapshot;
    const rebuilt: TableState = {
        ...state,
        currentPlayerSeat: snapshot.currentPlayerSeat,
        dealerSeat: snapshot.dealerSeat,
        doraIndicators: snapshot.doraIndicators,
        firstDealerSeat: snapshotFirstDealer(snapshot),
        gameEndResult: null,
        gameId: snapshot.gameId,
        honbaSticks: snapshot.honbaSticks,
        lastDiscardSeat: snapshot.latestDiscardSeat,
        phase: roundResult === null ? "in_round" : "round_ended",
        players: snapshot.players.map((info) => snapshotPlayer(snapshot, info, claimed)),
        revealedSeats: [],
        riichiCost: snapshot.riichiCost,
        riichiSticks: snapshot.riichiSticks,
        roundEndResult: roundResult === null ? null : extractRoundEndResult(roundResult, snapshot),
        roundHistory: snapshot.roundHistory.map(roundRecordOfHistory),
        roundNumber: snapshot.roundNumber,
        roundWind: snapshot.wind,
        tilesRemaining: snapshot.tilesRemaining,
    };
    if (roundResult === null) {
        return rebuilt;
    }
    return revealHands(showRobbedKan(rebuilt, roundResult), roundResult);
}
