import { type TemplateResult, html, nothing, render } from "lit-html";

import {
    type ClientEffect,
    type LiveClient,
    type LiveEvent,
    type LocalIntent,
    NO_PLAY_UI,
    type NoticeKind,
    PLAY_SWITCHES,
    PlayBoard,
    type PlayCommand,
    type PlayUi,
    type SeatTranscript,
    type TileChoiceKind,
    decisionOf,
    parseSeatTranscript,
    playDisplay,
    scenarioCheckpoint,
    seatScenarioFromTranscript,
    stepGameClient,
    stepPlayUi,
} from "@/entities/client";
import { CALLOUT_MS } from "@/entities/table";
import { type TileSpriteStatus } from "@/entities/tile";
import ANCHOR_SEAT_1 from "@/fixtures/seat-scenarios/anchor_seat_1.json";
import CALL_PROMPT_SEAT_1 from "@/fixtures/seat-scenarios/call_prompt_seat_1.json";
import CHANKAN_ROBBED_SEAT_3 from "@/fixtures/seat-scenarios/chankan_robbed_seat_3.json";
import DOUBLE_RON_SEAT_1 from "@/fixtures/seat-scenarios/double_ron_seat_1.json";
import FINAL_ROUND_SEAT_1 from "@/fixtures/seat-scenarios/final_round_seat_1.json";
import FIRST_TURN_WIN_SEAT_1 from "@/fixtures/seat-scenarios/first_turn_win_seat_1.json";
import FIRST_TURN_WIN_SEAT_3 from "@/fixtures/seat-scenarios/first_turn_win_seat_3.json";
import GAME_END_RECONNECT_SEAT_1 from "@/fixtures/seat-scenarios/game_end_reconnect_seat_1.json";
import KAN_CHOICE_SEAT_1 from "@/fixtures/seat-scenarios/kan_choice_seat_1.json";
import OWN_TURN_SEAT_1 from "@/fixtures/seat-scenarios/own_turn_seat_1.json";
import RECONNECT_SEAT_1 from "@/fixtures/seat-scenarios/reconnect_seat_1.json";
import RIICHI_KAN_SEAT_1 from "@/fixtures/seat-scenarios/riichi_kan_seat_1.json";
import SEAT_LEFT_SEAT_1 from "@/fixtures/seat-scenarios/seat_left_seat_1.json";
import SEAT_LEFT_SEAT_3 from "@/fixtures/seat-scenarios/seat_left_seat_3.json";
import { getLobbyHistoryUrl, replayPageUrl } from "@/shared/config";

import { storybookIndexHref } from "./storybook-nav";

/** The transcripts the stories run, imported one by one so the storybook's chunk carries no other. */
const TRANSCRIPTS = {
    anchor_seat_1: ANCHOR_SEAT_1,
    call_prompt_seat_1: CALL_PROMPT_SEAT_1,
    chankan_robbed_seat_3: CHANKAN_ROBBED_SEAT_3,
    double_ron_seat_1: DOUBLE_RON_SEAT_1,
    final_round_seat_1: FINAL_ROUND_SEAT_1,
    first_turn_win_seat_1: FIRST_TURN_WIN_SEAT_1,
    first_turn_win_seat_3: FIRST_TURN_WIN_SEAT_3,
    game_end_reconnect_seat_1: GAME_END_RECONNECT_SEAT_1,
    kan_choice_seat_1: KAN_CHOICE_SEAT_1,
    own_turn_seat_1: OWN_TURN_SEAT_1,
    reconnect_seat_1: RECONNECT_SEAT_1,
    riichi_kan_seat_1: RIICHI_KAN_SEAT_1,
    seat_left_seat_1: SEAT_LEFT_SEAT_1,
    seat_left_seat_3: SEAT_LEFT_SEAT_3,
} as const satisfies Readonly<Record<string, unknown>>;

type TranscriptName = keyof typeof TRANSCRIPTS;

/**
 * A board at a checkpoint of a generated seat transcript: the client state after the step its label names, as the
 * live game reaches it, with the view's riichi pick on or off, a call's choice of tiles open or not, and its round
 * result at a page.
 */
interface DecisionStory {
    readonly title: string;
    readonly transcript: TranscriptName;
    readonly label: string;
    readonly pickRiichi: boolean;
    readonly chooseTiles?: TileChoiceKind;
    readonly resultPage: number;
    /** What happens next, stepped on the checkpoint's state: a drop, a refusal, a kick. */
    readonly followUp?: (state: LiveClient) => readonly LiveEvent[];
    readonly confirmingLeave?: boolean;
    readonly tileSprite?: TileSpriteStatus;
    /** The notice opened whole in its sheet. */
    readonly noticeSheet?: NoticeKind;
}

/**
 * The stories in the order the page lists them: the look spec's anchor (`docs/game-client-look.md`, States) at its
 * three checkpoints and its call passed, declared and expired, the seating before the first deal, the call prompts and a
 * chi's choice of tiles, the turns (a kan's choice of tiles, in their base time and in the bank), the play switches on
 * beside furiten, what follows an answer, the first turns of a hand (kyuushu, tenhou, chiihou), the round results the
 * player confirms, the game's end and the last result reopened from it, a game ended out of step, then another
 * player's seat left to an AI and back, the viewer's own seat back, the board's notices (alone, stacked, long, over a
 * panel and opened whole over a decision, over the round confirm and under the leave question), the ends (a kick,
 * another tab) and the leave question.
 */
const STORY_KEYS = [
    "anchor_turn",
    "anchor_call",
    "anchor_riichi",
    "anchor_riichi_off",
    "anchor_call_passed",
    "anchor_pon_declared",
    "anchor_call_expired",
    "game_start",
    "call_prompt",
    "chi_choice",
    "ron_prompt",
    "chankan_prompt",
    "kuikae_turn",
    "own_turn",
    "kan_offer",
    "kan_choice",
    "turn_in_bank",
    "riichi_pick",
    "riichi_turn",
    "riichi_kan",
    "switches_furiten",
    "discard_pending",
    "kyuushu_offer",
    "tenhou_offer",
    "chiihou_offer",
    "round_end",
    "tenhou_result",
    "double_ron_first",
    "double_ron_last",
    "waiting",
    "reconnect_owed",
    "last_result",
    "game_end",
    "last_result_reopened",
    "out_of_step_result",
    "out_of_step_game_end",
    "player_left",
    "player_back",
    "seat_back",
    "connection_lost",
    "move_refused",
    "faces_missing",
    "notices_stacked",
    "notice_long",
    "notice_over_confirm",
    "notice_sheet_decision",
    "notice_sheet_confirm",
    "notice_sheet_leave",
    "kicked",
    "replaced",
    "leave_confirm",
    "leave_after_win",
] as const;

type DecisionStoryKey = (typeof STORY_KEYS)[number];

/** A story at the step labelled `label` of the transcript named `transcript`. */
function checkpoint(transcript: TranscriptName, label: string, title: string): DecisionStory {
    return { label, pickRiichi: false, resultPage: 0, title, transcript };
}

/**
 * The kuikae turn's first tile the player may discard, discarded, and the game's refusal of it, named by the turn's
 * wait id as the server names it.
 */
function refusedDiscard(state: LiveClient): readonly LiveEvent[] {
    const [intent] = playDisplay(state, NO_PLAY_UI).tileIntents.values();
    const at = state.now + 500;
    const refusal = {
        cd: "invalid_discard",
        msg: "invalid discard",
        t: 7,
        wi: decisionOf(state)?.waitId,
    };
    return [
        { at, intent, kind: "intent" },
        { at: at + 100, kind: "server_message", raw: refusal },
    ];
}

/**
 * The player's intents, one after another, once the last win's call has gone, as it has by the time the player
 * dismisses its result.
 */
function intentsAfterCall(
    ...picked: readonly LocalIntent[]
): (state: LiveClient) => readonly LiveEvent[] {
    return (state) => {
        const at = state.now + CALLOUT_MS;
        const answers: LiveEvent[] = picked.map((intent) => ({ at, intent, kind: "intent" }));
        return [{ at, kind: "tick" }, ...answers];
    };
}

/** The payload of the message labelled `label` that the transcript named `transcriptName` received. */
function receivedPayload(
    transcriptName: TranscriptName,
    label: string,
): Readonly<Record<string, unknown>> {
    const event = parsedTranscript(transcriptName).events.find(
        (candidate) => candidate.label === label,
    );
    if (event?.kind !== "received") {
        throw new Error(`${transcriptName} received no message labelled ${label}`);
    }
    return event.payload;
}

/**
 * Right after the player's ron, a message the client cannot read, which puts it out of step with the server, then the
 * ron's round end, the game's last, and its end as the final round's transcript received them, which reach the table
 * out of step; then the player's intents once the win's call has gone.
 */
function endedOutOfStep(
    ...picked: readonly LocalIntent[]
): (state: LiveClient) => readonly LiveEvent[] {
    return (state) => {
        const at = state.now;
        const unreadable: LiveEvent = { at, kind: "server_message", raw: { t: 999 } };
        const ends = ["round end", "game end"].map((label): LiveEvent => ({
            at,
            kind: "server_message",
            raw: receivedPayload("final_round_seat_1", label),
        }));
        return [unreadable, ...ends, ...intentsAfterCall(...picked)(state)];
    };
}

/** A message the client cannot read, `ms` after the checkpoint: the long notice of a client out of step. */
function unreadableAfter(ms: number): (state: LiveClient) => readonly LiveEvent[] {
    return (state) => [{ at: state.now + ms, kind: "server_message", raw: { t: 999 } }];
}

function closedWith(code: number): (state: LiveClient) => readonly LiveEvent[] {
    return (state) => [{ at: state.now + 500, code, kind: "transport_closed", reason: "" }];
}

/** The player's answer at the checkpoint. */
function answering(intent: LocalIntent): (state: LiveClient) => readonly LiveEvent[] {
    return (state) => [{ at: state.now, intent, kind: "intent" }];
}

/** Every play switch turned on at the checkpoint, which answers none of the decision already open. */
function allSwitchesOn(state: LiveClient): readonly LiveEvent[] {
    return PLAY_SWITCHES.map((playSwitch) => ({
        at: state.now,
        intent: { playSwitch, type: "toggle_switch" },
        kind: "intent",
    }));
}

/** A tick `seconds` after the checkpoint, the time the player let run. */
function after(seconds: number): (state: LiveClient) => readonly LiveEvent[] {
    return (state) => [{ at: state.now + seconds * 1000, kind: "tick" }];
}

const DECISION_STORIES: Readonly<Record<DecisionStoryKey, DecisionStory>> = {
    anchor_call: checkpoint("anchor_seat_1", "call offer", "Anchor: call offer"),
    anchor_call_expired: {
        ...checkpoint("anchor_seat_1", "call offer", "Anchor: call expired"),
        followUp: after(5),
    },
    anchor_call_passed: {
        ...checkpoint("anchor_seat_1", "call offer", "Anchor: call passed"),
        followUp: answering({ type: "pass" }),
    },
    anchor_pon_declared: {
        ...checkpoint("anchor_seat_1", "call offer", "Anchor: Pon declared"),
        followUp: (state) => {
            const offer = decisionOf(state)?.offers.find((candidate) => candidate.kind === "pon");
            if (offer === undefined) {
                throw new Error("The anchor call must offer Pon");
            }
            return answering({ offer, type: "choose" })(state);
        },
    },
    anchor_riichi: {
        ...checkpoint("anchor_seat_1", "riichi offer", "Anchor: riichi"),
        pickRiichi: true,
    },
    anchor_riichi_off: checkpoint("anchor_seat_1", "riichi offer", "Anchor: riichi offered"),
    anchor_turn: checkpoint("anchor_seat_1", "own turn", "Anchor: own turn"),
    call_prompt: checkpoint("call_prompt_seat_1", "prompt", "Call prompt"),
    chankan_prompt: checkpoint("chankan_robbed_seat_3", "chankan prompt", "Chankan prompt"),
    chi_choice: {
        ...checkpoint("call_prompt_seat_1", "prompt", "Chi: choose the tiles"),
        chooseTiles: "chi",
    },
    chiihou_offer: checkpoint("first_turn_win_seat_3", "chiihou draw", "Chiihou offered"),
    connection_lost: {
        ...checkpoint("call_prompt_seat_1", "turn", "Connection lost"),
        followUp: closedWith(1006),
    },
    discard_pending: checkpoint("call_prompt_seat_1", "discarded", "Discard pending"),
    double_ron_first: checkpoint("double_ron_seat_1", "round end", "Double ron 1/2"),
    double_ron_last: {
        ...checkpoint("double_ron_seat_1", "round end", "Double ron 2/2"),
        resultPage: 1,
    },
    faces_missing: {
        ...checkpoint("call_prompt_seat_1", "turn", "Faces missing"),
        tileSprite: "failed",
    },
    game_end: {
        ...checkpoint("final_round_seat_1", "game end", "Game end"),
        followUp: intentsAfterCall({ type: "confirm_result" }),
    },
    game_start: checkpoint("own_turn_seat_1", "game started", "Game start"),
    kan_choice: {
        ...checkpoint("kan_choice_seat_1", "kan offer", "Kan: choose the tiles"),
        chooseTiles: "kan",
    },
    kan_offer: checkpoint("kan_choice_seat_1", "kan offer", "Kan of either of two types"),
    kicked: { ...checkpoint("call_prompt_seat_1", "turn", "Kicked"), followUp: closedWith(1008) },
    kuikae_turn: checkpoint("call_prompt_seat_1", "turn", "Kuikae turn"),
    kyuushu_offer: checkpoint("game_end_reconnect_seat_1", "first draw", "First turn: kyuushu"),
    last_result: checkpoint("final_round_seat_1", "game end", "Last result"),
    last_result_reopened: {
        ...checkpoint("final_round_seat_1", "game end", "Last result reopened"),
        followUp: intentsAfterCall({ type: "confirm_result" }, { type: "show_last_result" }),
    },
    leave_after_win: {
        ...checkpoint("own_turn_seat_1", "round end", "Leave after a win"),
        confirmingLeave: true,
    },
    leave_confirm: {
        ...checkpoint("call_prompt_seat_1", "turn", "Leave?"),
        confirmingLeave: true,
    },
    move_refused: {
        ...checkpoint("call_prompt_seat_1", "turn", "Move refused"),
        followUp: refusedDiscard,
    },
    notice_long: {
        ...checkpoint("call_prompt_seat_1", "turn", "A long notice"),
        followUp: unreadableAfter(500),
    },
    notice_over_confirm: {
        ...checkpoint("own_turn_seat_1", "round end", "A notice over the round confirm"),
        tileSprite: "failed",
    },
    notice_sheet_confirm: {
        ...checkpoint("own_turn_seat_1", "round end", "A notice opened over the round confirm"),
        noticeSheet: "tile_sprite",
        tileSprite: "failed",
    },
    notice_sheet_decision: {
        ...checkpoint("call_prompt_seat_1", "turn", "A notice opened over a decision"),
        followUp: refusedDiscard,
        noticeSheet: "tile_sprite",
        tileSprite: "failed",
    },
    notice_sheet_leave: {
        ...checkpoint("call_prompt_seat_1", "turn", "The leave question over a notice's sheet"),
        confirmingLeave: true,
        noticeSheet: "tile_sprite",
        tileSprite: "failed",
    },
    notices_stacked: {
        ...checkpoint("call_prompt_seat_1", "turn", "Notices stacked"),
        followUp: refusedDiscard,
        tileSprite: "failed",
    },
    out_of_step_game_end: {
        ...checkpoint("final_round_seat_1", "ron chosen", "Out of step: game end"),
        followUp: endedOutOfStep({ type: "confirm_result" }),
    },
    out_of_step_result: {
        ...checkpoint("final_round_seat_1", "ron chosen", "Out of step: last result"),
        followUp: endedOutOfStep(),
    },
    own_turn: checkpoint("own_turn_seat_1", "first draw", "Own turn"),
    player_back: checkpoint("seat_left_seat_1", "player back", "Player back"),
    player_left: checkpoint("seat_left_seat_1", "player left", "Player left"),
    reconnect_owed: checkpoint("double_ron_seat_1", "reconnected", "Reconnect owed"),
    replaced: checkpoint("reconnect_seat_1", "replaced", "Opened elsewhere"),
    riichi_kan: checkpoint("riichi_kan_seat_1", "kan offer", "In riichi: kan offered"),
    riichi_pick: {
        ...checkpoint("own_turn_seat_1", "rinshan", "Riichi pick"),
        pickRiichi: true,
    },
    riichi_turn: checkpoint("own_turn_seat_1", "tsumo draw", "In riichi"),
    ron_prompt: checkpoint("reconnect_seat_1", "ron prompt", "Ron prompt"),
    round_end: checkpoint("own_turn_seat_1", "round end", "Round end"),
    seat_back: checkpoint("seat_left_seat_3", "reconnected", "Own seat back"),
    switches_furiten: {
        ...checkpoint("own_turn_seat_1", "furiten", "Switches on, furiten"),
        followUp: allSwitchesOn,
    },
    tenhou_offer: checkpoint("first_turn_win_seat_1", "tenhou draw", "Tenhou offered"),
    tenhou_result: checkpoint("first_turn_win_seat_1", "round end", "Tenhou"),
    turn_in_bank: {
        ...checkpoint("own_turn_seat_1", "rinshan", "Turn in bank"),
        followUp: after(6),
    },
    waiting: checkpoint("chankan_robbed_seat_3", "confirmed", "Waiting"),
};

const DEFAULT_STORY: DecisionStoryKey = "call_prompt";

/** The page's story, the client state it shows, the view's `ui`, and what the last answer sent. */
interface StoryScreen {
    readonly story: DecisionStoryKey;
    readonly state: LiveClient;
    readonly ui: PlayUi;
    readonly sent: readonly ClientEffect[];
}

function parsedTranscript(transcriptName: TranscriptName): SeatTranscript {
    const [error, transcript] = parseSeatTranscript(TRANSCRIPTS[transcriptName]);
    if (error) {
        throw new Error(`${transcriptName}: ${error.message}`);
    }
    return transcript;
}

/** The client state after the transcript's step labelled `label`, run as the live driver would run it. */
function checkpointState(transcriptName: TranscriptName, label: string): LiveClient {
    const transcript = parsedTranscript(transcriptName);
    const handoff = { gameTicket: "storybook", wsUrl: `ws://storybook/ws/${transcript.gameId}` };
    return scenarioCheckpoint(seatScenarioFromTranscript(transcript, handoff), label);
}

function storyScreen(key: DecisionStoryKey): StoryScreen {
    const {
        chooseTiles,
        confirmingLeave,
        followUp,
        label,
        noticeSheet,
        pickRiichi,
        resultPage,
        tileSprite,
        transcript,
    } = DECISION_STORIES[key];
    const reached = checkpointState(transcript, label);
    const state = (followUp?.(reached) ?? []).reduce(
        (current, event) => stepGameClient(current, event).state,
        reached,
    );
    const waitId = decisionOf(state)?.waitId ?? null;
    const picked = {
        ...NO_PLAY_UI,
        confirmingLeave: confirmingLeave ?? false,
        noticeSheet: noticeSheet ?? null,
        riichiPickWaitId: pickRiichi ? waitId : null,
        tileChoice:
            chooseTiles === undefined || waitId === null ? null : { kind: chooseTiles, waitId },
        tileSprite: tileSprite ?? NO_PLAY_UI.tileSprite,
    };
    const ui = stepPlayUi(state, picked, { kind: "show_result_page", page: resultPage });
    return { sent: [], state, story: key, ui };
}

function parseStory(search: string): DecisionStoryKey {
    const param = new URLSearchParams(search).get("state");
    return STORY_KEYS.find((key) => key === param) ?? DEFAULT_STORY;
}

/** Keep the story in the query, beside whatever else the page was opened with (the lobby's `?v=2`). */
function syncStoryParam(story: DecisionStoryKey): void {
    const url = new URL(window.location.href);
    if (story === DEFAULT_STORY) {
        url.searchParams.delete("state");
    } else {
        url.searchParams.set("state", story);
    }
    history.replaceState(null, "", url);
}

function describeSent(sent: readonly ClientEffect[]): TemplateResult | typeof nothing {
    if (sent.length === 0) {
        return nothing;
    }
    return html`<pre class="decisions-storybook__sent">${sent.map((effect) => JSON.stringify(effect)).join("\n")}</pre>`;
}

/** The story the picker's change names, shown; a value naming none is ignored. */
function pickStory(event: Event, show: (story: DecisionStoryKey) => void): void {
    const { target } = event;
    const key = target instanceof HTMLSelectElement ? target.value : "";
    const picked = STORY_KEYS.find((candidate) => candidate === key);
    if (picked !== undefined) {
        show(picked);
    }
}

/** The page's controls: the story picker's and the board's. */
interface StoryHandlers {
    readonly show: (story: DecisionStoryKey) => void;
    readonly onCommand: (command: PlayCommand) => void;
}

function storybookTemplate(
    screen: StoryScreen,
    { onCommand, show }: StoryHandlers,
): TemplateResult {
    const { sent, state, story, ui } = screen;
    return html`
        <div class="board-page decisions-storybook">
            <div class="board-page__board">
                ${PlayBoard({
                    display: playDisplay(state, ui),
                    links: {
                        history: getLobbyHistoryUrl(),
                        replay: replayPageUrl(
                            state.table.gameId,
                            state.viewerSeat,
                            window.location.search,
                        ),
                    },
                    onCommand,
                })}
            </div>
            <div class="board-page__aside">
                <a class="board-storybook__btn" href="${storybookIndexHref()}">Back</a>
                <div class="board-storybook__picker"><select
                    class="board-storybook__select"
                    aria-label="Story"
                    @change=${(event: Event) => pickStory(event, show)}
                >${STORY_KEYS.map(
                    (key) =>
                        html`<option value=${key} ?selected=${key === story}>${DECISION_STORIES[key].title}</option>`,
                )}</select></div>
                ${describeSent(sent)}
            </div>
        </div>
    `;
}

/**
 * Mount the decisions storybook: the live board at labelled checkpoints of the generated seat transcripts, in the
 * story the page's `?state=` names. Its controls step the client's own dispatcher, so a tap shows the answer the
 * live game would send and the state it leaves, with no socket behind it.
 */
export function mountStorybookDecisions(host: HTMLElement): () => void {
    let screen = storyScreen(parseStory(window.location.search));

    function draw(): void {
        render(storybookTemplate(screen, { onCommand, show }), host);
    }

    function show(key: DecisionStoryKey): void {
        syncStoryParam(key);
        screen = storyScreen(key);
        draw();
    }

    function onCommand(command: PlayCommand): void {
        const { state, ui } = screen;
        if (command.kind === "intent") {
            const step = stepGameClient(state, {
                at: state.now,
                intent: command.intent,
                kind: "intent",
            });
            screen = {
                ...screen,
                sent: step.effects,
                state: step.state,
                ui: stepPlayUi(step.state, ui, command),
            };
        } else {
            screen = { ...screen, ui: stepPlayUi(state, ui, command) };
        }
        draw();
    }

    draw();
    return () => {
        render(nothing, host);
    };
}
