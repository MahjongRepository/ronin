import { createInitialPlayerState } from "@/entities/table/model/initial-state";
import {
    type DiscardRecord,
    type MeldRecord,
    type PlayerState,
    type TableState,
} from "@/entities/table/model/types";
import { type GameReconnectedEvent } from "@/shared/protocol";

import { extractRoundEndResult, revealHands, showRobbedKan } from "./round-end";

type SnapshotSeat = GameReconnectedEvent["playerStates"][number];

/** The tile each seat lost to a call, keyed `seat:tileId`, so its river shows it claimed. */
function claimedDiscardKeys(melds: readonly MeldRecord[]): ReadonlySet<string> {
    return new Set(
        melds
            .filter((meld) => meld.fromSeat !== null && meld.calledTileId !== null)
            .map((meld) => `${meld.fromSeat}:${meld.calledTileId}`),
    );
}

function snapshotDiscards(seat: SnapshotSeat, claimed: ReadonlySet<string>): DiscardRecord[] {
    return seat.discards.map((discard) => ({
        claimed: claimed.has(`${seat.seat}:${discard.tileId}`),
        isRiichi: discard.isRiichiDiscard,
        isTsumogiri: discard.isTsumogiri,
        tileId: discard.tileId,
    }));
}

/**
 * The snapshot's seat `seat`, from its player and its state, which the snapshot lists in seat order: the reconnected
 * seat's own hand by its tiles, every other by its closed-hand count, since the snapshot shows other hands face down.
 */
function snapshotPlayer(
    snapshot: GameReconnectedEvent,
    seat: number,
    claimed: ReadonlySet<string>,
): PlayerState {
    const info = snapshot.players[seat];
    const seatState = snapshot.playerStates[seat];
    const isViewer = info.seat === snapshot.seat;
    return {
        ...createInitialPlayerState({ ...info, score: seatState.score }),
        aiStandIn: info.aiStandIn,
        concealedCount: isViewer ? 0 : seatState.tileCount,
        discards: snapshotDiscards(seatState, claimed),
        isRiichi: seatState.isRiichi,
        melds: seatState.melds,
        tiles: isViewer ? snapshot.myTiles : [],
    };
}

/**
 * Rebuild the table from a reconnect snapshot, its latest discard marked where the snapshot names it. It opens
 * no wait: when the game awaits the seat, the server re-sends the event that opened it. A snapshot taken during a round advance shows the round that ended, with its result, the
 * hands it reveals, and the kan its win robbed as declared: the server never completes a robbed kan, so the snapshot's hand still holds its
 * tiles. Its scores and riichi sticks already hold every accepted riichi's deposit, so the table takes them as they are.
 * Its round history lists every finished round, the one whose result it shows included, which the table takes whole.
 * The parsed snapshot is complete (`gameReconnectedSchema`): each seat's player and state, in seat order, so nothing
 * of a seat is filled in here.
 */
export function applyGameReconnected(
    state: TableState,
    snapshot: GameReconnectedEvent,
): TableState {
    const allMelds = snapshot.playerStates.flatMap((seat) => seat.melds);
    const claimed = claimedDiscardKeys(allMelds);
    const { roundResult } = snapshot;
    const rebuilt: TableState = {
        ...state,
        currentPlayerSeat: snapshot.currentPlayerSeat,
        dealerSeat: snapshot.dealerSeat,
        doraIndicators: snapshot.doraIndicators,
        firstDealerSeat: snapshot.firstDealerSeat,
        gameEndResult: null,
        gameId: snapshot.gameId,
        honbaSticks: snapshot.honbaSticks,
        inStep: true,
        lastDiscardSeat: snapshot.latestDiscardSeat,
        phase: roundResult === null ? "in_round" : "round_ended",
        players: snapshot.players.map((info) => snapshotPlayer(snapshot, info.seat, claimed)),
        revealedSeats: [],
        riichiStickValue: snapshot.riichiStickValue,
        riichiSticks: snapshot.riichiSticks,
        roundEndResult: roundResult === null ? null : extractRoundEndResult(roundResult, snapshot),
        roundInWind: snapshot.roundInWind,
        roundNumber: snapshot.roundNumber,
        roundWind: snapshot.wind,
        tilesRemaining: snapshot.tilesRemaining,
    };
    if (roundResult === null) {
        return rebuilt;
    }
    return revealHands(showRobbedKan(rebuilt, roundResult), roundResult);
}
