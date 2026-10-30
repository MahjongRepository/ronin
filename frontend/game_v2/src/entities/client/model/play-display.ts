import {
    type BoardCallouts,
    type BoardDisplayState,
    type BoardPlayerDisplay,
    type SeatPosition,
    boardCallouts,
    tableStateToDisplayState,
} from "@/entities/table";
import { type HandTile } from "@/entities/tile";
import { CALL_TYPE } from "@/shared/protocol";

import {
    type NoticeSheetDisplay,
    type PlayNotice,
    boardNotices,
    noticeSheet,
} from "./board-notices";
import { type DecisionCountdown, decisionCountdown, firstDealCountdown } from "./countdown";
import {
    type DecisionAction,
    type DecisionStanding,
    type TilePlay,
    decisionActions,
    decisionStanding,
    escapeCommand,
    intentsOf,
    pickingRiichi,
    tilePlays,
} from "./decision-controls";
import { takesIntent } from "./dispatch";
import { PLAY_SWITCHES } from "./play-switches";
import { type PlayAction, type PlayCommand, type PlayUi, intentCommand } from "./play-ui";
import {
    type ResultControls,
    lastResultAction,
    resultControls,
    shownResultPage,
} from "./result-controls";
import {
    type FailureDisplay,
    type LeaveControls,
    failureDisplay,
    leaveControls,
} from "./session-end";
import { type GameClientState, type LocalIntent, type PlayIntent, type PlaySwitch } from "./types";

/**
 * A play switch on the board: its label, whether it is on, and the command turning it, which sends nothing itself.
 */
export interface SwitchControl {
    readonly playSwitch: PlaySwitch;
    readonly label: string;
    readonly on: boolean;
    readonly command: PlayCommand;
}

/**
 * The live board as the viewer plays it: the table from its seat, its own hand's tiles marked by the open decision
 * (with the intent tapping each selectable one sends), the decision's buttons, its countdown and the seat's furiten.
 */
export interface PlayDisplay {
    readonly board: BoardDisplayState | null;
    /** The calls the board shows by their seats, from the viewer's seat; null with none. */
    readonly callouts: BoardCallouts | null;
    /** The whole seconds left of the game start pause, which the seating before the first deal counts down. */
    readonly firstDealSeconds: number | null;
    readonly tileAction: string;
    readonly tileIntents: ReadonlyMap<number, LocalIntent>;
    /** The open decision's controls, ranked; an answered one keeps them, showing which sent the answer. */
    readonly actions: readonly DecisionAction[];
    /** Where the viewer's decision stands; null with none. */
    readonly decisionStanding: DecisionStanding | null;
    /** What Escape does: step back from a call's choice of tiles or the riichi toggle; null with neither on. */
    readonly escape: PlayCommand | null;
    readonly countdown: DecisionCountdown | null;
    /** The seat is furiten, shown only while a round plays, never under its result or the standings. */
    readonly furiten: boolean;
    /** The play switches, while the player may turn them (a live seat in a round); else none. */
    readonly switches: readonly SwitchControl[];
    /** The page of the round's result the panel shows, clamped to its pages; 0 with no result. */
    readonly resultPage: number;
    /** The nameplate pinned for the others' score differences, or null. */
    readonly pinnedNameplate: SeatPosition | null;
    /** The result panel's controls while the viewer has a round result to confirm or waits on one; else null. */
    readonly result: ResultControls | null;
    /** Whether the game's last result still shows over the standings, until the player dismisses it. */
    readonly resultOverStandings: boolean;
    /** The standings' way back to the game's last result once the player dismissed it; else null. */
    readonly lastResult: PlayAction | null;
    /** The viewer's seat, which the standings mark; null before the seat is known. */
    readonly viewerSeat: number | null;
    /** The notices over the table, in `NoticeKind`'s order; none while a failure blocks the board. */
    readonly notices: readonly PlayNotice[];
    /** The notice opened whole in its sheet over the board, while it shows; else null. */
    readonly noticeSheet: NoticeSheetDisplay | null;
    /** The end that blocks the board with its reason and a way back, or null. */
    readonly failure: FailureDisplay | null;
    readonly leave: LeaveControls;
}

const DISCARD_ACTION = "Discard";
const RIICHI_ACTION = "Declare riichi discarding";

const SWITCH_LABELS: Readonly<Record<PlaySwitch, string>> = {
    auto_discard: "Auto discard",
    auto_win: "Auto win",
    no_calls: "No calls",
};

function playTile(tile: HandTile, plays: ReadonlyMap<number, TilePlay>): HandTile {
    const play = tile.tileId === undefined ? undefined : plays.get(tile.tileId);
    if (play === undefined || tile.show !== "face" || tile.tileId === undefined) {
        return tile;
    }
    return { face: tile.face, show: "face", state: play.state, tileId: tile.tileId };
}

function playHand(
    player: BoardPlayerDisplay,
    plays: ReadonlyMap<number, TilePlay>,
): BoardPlayerDisplay {
    return {
        ...player,
        drawnTile: player.drawnTile === undefined ? undefined : playTile(player.drawnTile, plays),
        hand: player.hand.map((tile) => playTile(tile, plays)),
    };
}

/**
 * A chankan offer's source, the kan it may rob, as the declarer's board position and the meld's index (oldest first);
 * null for any other decision, so the mark goes once the offer resolves.
 */
function kanSource(state: GameClientState): { position: number; meld: number } | null {
    const { decision, table, viewerSeat } = state;
    if (
        decision?.kind !== "call" ||
        decision.callType !== CALL_TYPE.CHANKAN ||
        viewerSeat === null
    ) {
        return null;
    }
    const declarer = table.players.find((player) => player.seat === decision.fromSeat);
    const meld =
        declarer?.melds.findIndex(
            (candidate) =>
                candidate.tileIds.includes(decision.tileId) ||
                candidate.addedTileId === decision.tileId,
        ) ?? -1;
    return meld === -1 ? null : { meld, position: (decision.fromSeat - viewerSeat + 4) % 4 };
}

function viewerBoard(
    state: GameClientState,
    plays: ReadonlyMap<number, TilePlay>,
): BoardDisplayState | null {
    const { table, viewerSeat } = state;
    if (viewerSeat === null) {
        return null;
    }
    const board = tableStateToDisplayState(table, { bottomSeat: viewerSeat, reveal: "bottom" });
    if (board === null) {
        return null;
    }
    const [bottom, right, top, left] = board.players;
    const players: BoardDisplayState["players"] = [playHand(bottom, plays), right, top, left];
    return { ...board, players: markSource(players, kanSource(state)) };
}

function withSource(player: BoardPlayerDisplay, meld: number): BoardPlayerDisplay {
    return { ...player, sourceMeld: meld };
}

/** The players with the kan a chankan offer may rob marked in its declarer's melds; as they were with none. */
function markSource(
    players: BoardDisplayState["players"],
    source: { position: number; meld: number } | null,
): BoardDisplayState["players"] {
    if (source === null) {
        return players;
    }
    const [bottom, right, top, left] = players.map((player, position) =>
        position === source.position ? withSource(player, source.meld) : player,
    );
    return [bottom, right, top, left];
}

/** The play switches as the board shows them, each turned by its intent, while the dispatcher takes that. */
function switchControls(state: GameClientState): SwitchControl[] {
    return PLAY_SWITCHES.flatMap((playSwitch): SwitchControl[] => {
        const intent: PlayIntent = { playSwitch, type: "toggle_switch" };
        if (!takesIntent(state, intent)) {
            return [];
        }
        return [
            {
                command: intentCommand(intent),
                label: SWITCH_LABELS[playSwitch],
                on: state.switches[playSwitch],
                playSwitch,
            },
        ];
    });
}

/** The live calls as the viewer's board shows them, keyed by when they were made. */
function liveCallouts(state: GameClientState): BoardCallouts | null {
    const { calls, viewerSeat } = state;
    if (calls === null || viewerSeat === null) {
        return null;
    }
    return { items: boardCallouts(calls.calls, viewerSeat), key: `call-${calls.at}` };
}

/**
 * The live board a client state shows its viewer, with the view's `ui` beside it: the table from the viewer's seat
 * with only its own hand face up, and the open decision as the hand's playable tiles and the buttons around them.
 * What may be played is the dispatcher's answer (`takesIntent`), never a rule restated here, so the board offers
 * exactly what stepping the intent would send.
 */
export function playDisplay(state: GameClientState, ui: PlayUi): PlayDisplay {
    const { furiten, table, viewerSeat } = state;
    const viewer = table.players.find((player) => player.seat === viewerSeat);
    const picking = pickingRiichi(state, ui);
    const plays =
        viewer === undefined ? new Map<number, TilePlay>() : tilePlays(state, viewer, picking);
    const resultPage = shownResultPage(table, ui);
    const failure = failureDisplay(state.session);
    const notices = boardNotices(state, ui);
    return {
        actions: decisionActions(state, ui),
        board: viewerBoard(state, plays),
        callouts: liveCallouts(state),
        countdown: decisionCountdown(state),
        decisionStanding: decisionStanding(state),
        escape: escapeCommand(state, ui),
        failure,
        firstDealSeconds: firstDealCountdown(state),
        furiten: furiten && viewer !== undefined && table.phase === "in_round",
        lastResult: lastResultAction(state),
        leave: leaveControls(state, ui),
        noticeSheet: noticeSheet(state, ui, notices),
        notices,
        pinnedNameplate: ui.pinnedNameplate,
        result: resultControls(state, resultPage),
        resultOverStandings: state.roundConfirm?.kind === "final",
        resultPage,
        switches: switchControls(state),
        tileAction: picking ? RIICHI_ACTION : DISCARD_ACTION,
        tileIntents: intentsOf(plays),
        viewerSeat,
    };
}
