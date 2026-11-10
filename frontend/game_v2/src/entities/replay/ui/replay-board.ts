import { type TemplateResult, html, nothing } from "lit-html";

import { GameMenu } from "@/entities/client";
import { type ReplayDisplay } from "@/entities/replay/lib/replay-display";
import { type ReplayCursor, lastCursor } from "@/entities/replay/model/replay-cursor";
import { type LoadedReplayScreen, type StepDirection } from "@/entities/replay/model/replay-page";
import {
    GameBoard,
    type PanelAction,
    SEAT_POSITIONS,
    type SeatPosition,
    type TablePanelControls,
    TablePanelDisplay,
} from "@/entities/table";
import { type Locale, type WindScript, t } from "@/shared/i18n";

import { ReplayControls, ReplayStatus } from "./replay-controls";
import { RoundList } from "./round-list";

/** The focus key the seating's Start renders, so the page focuses it as the seating opens. */
export const SEATING_START_FOCUS_KEY = "seating-start";

/** Where a page that cannot show its replay, or the game's end, sends the reader. */
export interface ReplayLinks {
    readonly lobby: string;
    readonly history: string;
}

/** What the board's controls, panel, nameplates and menu ask of the page. */
export interface ReplayBoardHandlers {
    readonly move: (cursor: ReplayCursor) => void;
    readonly showResultPage: (page: number) => void;
    readonly viewSeat: (seat: SeatPosition) => void;
    readonly nextView: () => void;
    readonly toggleRoundList: () => void;
    readonly closeRoundList: () => void;
    readonly selectRound: (start: ReplayCursor) => void;
    readonly start: () => void;
    readonly stepPress: (direction: StepDirection, event: PointerEvent) => void;
    readonly stepClick: (direction: StepDirection) => void;
    readonly togglePlay: () => void;
    readonly toggleHands: () => void;
    readonly toggleSettings: () => void;
    readonly closeSettings: () => void;
    readonly toggleSound: () => void;
    readonly toggleAnimations: () => void;
    readonly setLanguage: (locale: Locale) => void;
    readonly setWinds: (script: WindScript) => void;
    readonly setTileLabels: (on: boolean) => void;
}

export interface ReplayBoardProps {
    readonly screen: LoadedReplayScreen;
    readonly display: ReplayDisplay;
    readonly links: ReplayLinks;
    readonly handlers: ReplayBoardHandlers;
}

/** The replay's moves and options over the board's band, and the round list over the board while it is open. */
function controlsTemplate(
    { autoplay, hideHands, replay, roundListOpen }: LoadedReplayScreen,
    display: ReplayDisplay,
    handlers: ReplayBoardHandlers,
): TemplateResult {
    const last = lastCursor(replay.navigation);
    const end =
        last === null
            ? null
            : {
                  current: display.moves.last === null,
                  cursor: last,
                  summary:
                      display.incomplete === null
                          ? t("replay.rounds.end_game")
                          : t("replay.rounds.end_recording"),
              };
    const roundList = roundListOpen
        ? RoundList({
              end,
              incomplete: display.incomplete,
              onClose: handlers.closeRoundList,
              onSelect: handlers.selectRound,
              rows: display.rounds,
          })
        : nothing;
    return html`<div class="replay-controls">${ReplayControls({
        moves: display.moves,
        onMove: handlers.move,
        onNextView: handlers.nextView,
        onStepClick: handlers.stepClick,
        onStepPress: handlers.stepPress,
        onToggleHands: handlers.toggleHands,
        onTogglePlay: handlers.togglePlay,
        onToggleRoundList: handlers.toggleRoundList,
        playback: { hideHands, playing: autoplay.playing },
        roundListOpen,
    })}${roundList}</div>`;
}

/** Where a table's seat stands on the board as the screen views it. */
function positionOf(seat: number, { replay, view }: LoadedReplayScreen): SeatPosition {
    const { seatCount } = replay;
    return SEAT_POSITIONS[(seat - view.bottomSeat + seatCount) % seatCount];
}

/** The ways back from the game's end: the lobby and the game history. */
function endActions(lobby: string, history: string): readonly PanelAction[] {
    return [
        { href: lobby, kind: "link", label: t("common.lobby") },
        { href: history, kind: "link", label: t("common.game_history"), primary: true },
    ];
}

/**
 * The replay's board: the table at the display's stop, its panel (the seating's Start, a result, the game's end), the
 * replay's controls and status in the band, and the settings menu in the corner. A nameplate press views that seat,
 * as a press of its name on the seating does.
 */
export function ReplayBoard({
    display,
    handlers,
    links,
    screen,
}: ReplayBoardProps): TemplateResult {
    const { overlay } = display;
    const { lobby } = links;
    const controls: TablePanelControls = {
        endActions: endActions(lobby, links.history),
        onPage: handlers.showResultPage,
        onPickSeat: (seat) => handlers.viewSeat(positionOf(seat, screen)),
        seatingActions: [
            {
                focusKey: SEATING_START_FOCUS_KEY,
                kind: "button",
                label: t("replay.start"),
                onClick: handlers.start,
                primary: true,
            },
        ],
    };
    return GameBoard({
        animationsOn: screen.animationsOn,
        callouts: display.callouts,
        debug: false,
        matchResult: display.matchResult,
        menu: GameMenu({
            animationsOn: screen.animationsOn,
            backdrop: true,
            leave: { href: lobby, kind: "link" },
            onClose: handlers.closeSettings,
            onLanguage: handlers.setLanguage,
            onTileLabels: handlers.setTileLabels,
            onToggleAnimations: handlers.toggleAnimations,
            onToggleOpen: handlers.toggleSettings,
            onToggleSound: handlers.toggleSound,
            onWinds: handlers.setWinds,
            open: screen.settingsOpen,
            soundOn: screen.soundOn,
            status: null,
        }),
        motion: display.motion,
        onViewSeat: handlers.viewSeat,
        overlay: overlay === null ? undefined : TablePanelDisplay(overlay, controls),
        overlayAfterCall: overlay?.kind === "result" && overlay.afterCall,
        replay: {
            controls: controlsTemplate(screen, display, handlers),
            status: ReplayStatus({ display }),
        },
        state: display.board,
    });
}
