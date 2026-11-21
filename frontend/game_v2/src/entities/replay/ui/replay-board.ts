import { type TemplateResult, html, nothing } from "lit-html";

import { GameMenu } from "@/entities/client";
import { type ReplayDisplay } from "@/entities/replay/lib/replay-display";
import { type ReplayCursor, lastCursor } from "@/entities/replay/model/replay-cursor";
import {
    type LoadedReplayScreen,
    type StepDirection,
    showsHand,
} from "@/entities/replay/model/replay-page";
import {
    GameBoard,
    type PanelAction,
    SEAT_POSITIONS,
    type SeatPosition,
    type TablePanelControls,
    TablePanelDisplay,
} from "@/entities/table";
import { type Locale, type WindScript, t } from "@/shared/i18n";
import { type ShortcutKeys } from "@/shared/lib";

import { ReplayControls, ReplayStatus } from "./replay-controls";
import { ReplayTools } from "./replay-tools";
import { RoundList } from "./round-list";

/** The focus key the seating's Start renders, so the page focuses it as the seating opens. */
export const SEATING_START_FOCUS_KEY = "seating-start";

/** Where a page that cannot show its replay, or the game's end, sends the reader. */
export interface ReplayLinks {
    readonly lobby: string;
    readonly history: string;
    /** This game's saved replay, where an observed game the server no longer holds sends the viewer. */
    readonly replay: string;
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
    readonly toggleTools: () => void;
    readonly closeTools: () => void;
    readonly copyHand: () => void;
    readonly analyzeHand: () => void;
    readonly toggleTsumogiri: () => void;
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
    /** Whose shortcut names the tools show. */
    readonly shortcuts: ShortcutKeys;
}

function toolsTemplate({
    handlers,
    screen,
    shortcuts,
}: Pick<ReplayBoardProps, "handlers" | "screen" | "shortcuts">): TemplateResult | typeof nothing {
    return screen.toolsOpen
        ? ReplayTools({
              hideHands: screen.hideHands,
              onAnalyzeHand: handlers.analyzeHand,
              onClose: handlers.closeTools,
              onCopyHand: handlers.copyHand,
              onToggleHands: handlers.toggleHands,
              onToggleTsumogiri: handlers.toggleTsumogiri,
              shortcuts,
              showTsumogiri: screen.showTsumogiri,
              showsHand: showsHand(screen),
          })
        : nothing;
}

/** What the round list's last row goes to: the game's end, a live game's newest stop, or where the recording ends. */
function endSummary(display: ReplayDisplay): string {
    if (display.stream === "live") {
        return t("replay.rounds.end_live");
    }
    return display.incomplete === null
        ? t("replay.rounds.end_game")
        : t("replay.rounds.end_recording");
}

/**
 * The replay's moves and options over the board's band, and the round list or the tools' menu over the board while
 * it is open.
 */
function controlsTemplate(props: ReplayBoardProps): TemplateResult {
    const { display, handlers, screen } = props;
    const { autoplay, replay, roundListOpen } = screen;
    const last = lastCursor(replay.navigation);
    const end =
        last === null
            ? null
            : {
                  current: display.moves.last === null,
                  cursor: last,
                  summary: endSummary(display),
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
        onTogglePlay: handlers.togglePlay,
        onToggleRoundList: handlers.toggleRoundList,
        onToggleTools: handlers.toggleTools,
        playback: { playing: autoplay.playing },
        roundListOpen,
        toolsOpen: screen.toolsOpen,
    })}${roundList}${toolsTemplate(props)}</div>`;
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
export function ReplayBoard(props: ReplayBoardProps): TemplateResult {
    const { display, handlers, links, screen } = props;
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
        overlayHeld: overlay?.kind === "result" && overlay.held,
        replay: {
            controls: controlsTemplate(props),
            marksTsumogiri: screen.showTsumogiri,
            status: ReplayStatus({
                display,
                handCopy: screen.handCopy?.outcome ?? null,
                replayUrl: links.replay,
            }),
        },
        state: display.board,
    });
}
