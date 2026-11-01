import { type TemplateResult, html, nothing } from "lit-html";

import { GameMenu } from "@/entities/client";
import { type ReplayDisplay } from "@/entities/replay/lib/replay-display";
import { type ReplayCursor, lastCursor } from "@/entities/replay/model/replay-cursor";
import { type LoadedReplayScreen, type StepDirection } from "@/entities/replay/model/replay-page";
import {
    GameBoard,
    type PanelAction,
    type PlatePress,
    type SeatPosition,
    type TablePanelControls,
    TablePanelDisplay,
} from "@/entities/table";

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
                          ? "The game's end and the final scores"
                          : "Where the recording ends",
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
    return html`${ReplayControls({
        moves: display.moves,
        onMove: handlers.move,
        onStepClick: handlers.stepClick,
        onStepPress: handlers.stepPress,
        onToggleHands: handlers.toggleHands,
        onTogglePlay: handlers.togglePlay,
        onToggleRoundList: handlers.toggleRoundList,
        playback: { hideHands, playing: autoplay.playing },
        roundListOpen,
    })}${roundList}`;
}

/** The ways back from the game's end: the lobby and the game history. */
function endActions(links: ReplayLinks): readonly PanelAction[] {
    return [
        { href: links.lobby, kind: "link", label: "Lobby" },
        { href: links.history, kind: "link", label: "Game history", primary: true },
    ];
}

/**
 * The replay's board: the table at the display's stop, its panel (the seating's Start, a result, the game's end), the
 * replay's controls and status in the band, and the settings menu in the corner. A nameplate press views that seat.
 */
export function ReplayBoard({
    display,
    handlers,
    links,
    screen,
}: ReplayBoardProps): TemplateResult {
    const platePress: PlatePress = { kind: "view", onView: handlers.viewSeat };
    const { overlay } = display;
    const controls: TablePanelControls = {
        endActions: endActions(links),
        onPage: handlers.showResultPage,
        seatingActions: [
            {
                focusKey: SEATING_START_FOCUS_KEY,
                kind: "button",
                label: "Start",
                onClick: handlers.start,
                primary: true,
            },
        ],
    };
    return GameBoard({
        callouts: display.callouts,
        debug: false,
        menu: GameMenu({
            onClose: handlers.closeSettings,
            onToggleOpen: handlers.toggleSettings,
            onToggleSound: handlers.toggleSound,
            open: screen.settingsOpen,
            soundOn: screen.soundOn,
            status: null,
        }),
        overlay: overlay === null ? undefined : TablePanelDisplay(overlay, controls),
        overlayAfterCall: overlay?.kind === "result" && overlay.afterCall,
        platePress,
        replay: {
            controls: controlsTemplate(screen, display, handlers),
            status: ReplayStatus({ display }),
        },
        state: display.board,
    });
}
