import { type TemplateResult, html, nothing, render } from "lit-html";

import {
    type ClientEffect,
    type GameClientState,
    NO_PLAY_UI,
    PlayBoard,
    type PlayCommand,
    type PlayUi,
    nextPlayUi,
    parseSeatTranscript,
    playDisplay,
    scenarioCheckpoint,
    seatScenarioFromTranscript,
    stepGameClient,
} from "@/entities/client";
import CALL_PROMPT_SEAT_1 from "@/fixtures/seat-scenarios/call_prompt_seat_1.json";
import CHANKAN_ROBBED_SEAT_3 from "@/fixtures/seat-scenarios/chankan_robbed_seat_3.json";
import DOUBLE_RON_SEAT_1 from "@/fixtures/seat-scenarios/double_ron_seat_1.json";
import FINAL_ROUND_SEAT_1 from "@/fixtures/seat-scenarios/final_round_seat_1.json";
import OWN_TURN_SEAT_1 from "@/fixtures/seat-scenarios/own_turn_seat_1.json";
import RECONNECT_SEAT_1 from "@/fixtures/seat-scenarios/reconnect_seat_1.json";

/** The transcripts the stories run, imported one by one so the storybook's chunk carries no other. */
const TRANSCRIPTS = {
    call_prompt_seat_1: CALL_PROMPT_SEAT_1,
    chankan_robbed_seat_3: CHANKAN_ROBBED_SEAT_3,
    double_ron_seat_1: DOUBLE_RON_SEAT_1,
    final_round_seat_1: FINAL_ROUND_SEAT_1,
    own_turn_seat_1: OWN_TURN_SEAT_1,
    reconnect_seat_1: RECONNECT_SEAT_1,
} as const satisfies Readonly<Record<string, unknown>>;

type TranscriptName = keyof typeof TRANSCRIPTS;

/**
 * A board at a checkpoint of a generated seat transcript: the client state after the step its label names, as the
 * live game reaches it, with the view's riichi pick on or off and its round result at a page.
 */
interface DecisionStory {
    readonly title: string;
    readonly transcript: TranscriptName;
    readonly label: string;
    readonly pickRiichi: boolean;
    readonly resultPage: number;
}

/**
 * The stories in the order the page lists them: the call prompts, the turns, what follows an answer, then the round
 * results the player confirms.
 */
const STORY_KEYS = [
    "call_prompt",
    "ron_prompt",
    "chankan_prompt",
    "kuikae_turn",
    "own_turn",
    "riichi_pick",
    "riichi_turn",
    "answered",
    "round_end",
    "double_ron_first",
    "double_ron_last",
    "waiting",
    "reconnect_owed",
    "last_result",
] as const;

type DecisionStoryKey = (typeof STORY_KEYS)[number];

/** A story at the step labelled `label` of the transcript named `transcript`. */
function checkpoint(transcript: TranscriptName, label: string, title: string): DecisionStory {
    return { label, pickRiichi: false, resultPage: 0, title, transcript };
}

const DECISION_STORIES: Readonly<Record<DecisionStoryKey, DecisionStory>> = {
    answered: checkpoint("call_prompt_seat_1", "discarded", "Answered"),
    call_prompt: checkpoint("call_prompt_seat_1", "prompt", "Call prompt"),
    chankan_prompt: checkpoint("chankan_robbed_seat_3", "chankan prompt", "Chankan prompt"),
    double_ron_first: checkpoint("double_ron_seat_1", "round end", "Double ron 1/2"),
    double_ron_last: {
        ...checkpoint("double_ron_seat_1", "round end", "Double ron 2/2"),
        resultPage: 1,
    },
    kuikae_turn: checkpoint("call_prompt_seat_1", "turn", "Kuikae turn"),
    last_result: checkpoint("final_round_seat_1", "game end", "Last result"),
    own_turn: checkpoint("own_turn_seat_1", "first draw", "Own turn"),
    reconnect_owed: checkpoint("double_ron_seat_1", "reconnected", "Reconnect owed"),
    riichi_pick: {
        ...checkpoint("own_turn_seat_1", "rinshan", "Riichi pick"),
        pickRiichi: true,
    },
    riichi_turn: checkpoint("own_turn_seat_1", "tsumo draw", "In riichi"),
    ron_prompt: checkpoint("reconnect_seat_1", "ron prompt", "Ron prompt"),
    round_end: checkpoint("own_turn_seat_1", "round end", "Round end"),
    waiting: checkpoint("chankan_robbed_seat_3", "confirmed", "Waiting"),
};

const DEFAULT_STORY: DecisionStoryKey = "call_prompt";

/** The page's story, the client state it shows, the view's `ui`, and what the last answer sent. */
interface StoryScreen {
    readonly story: DecisionStoryKey;
    readonly state: GameClientState;
    readonly ui: PlayUi;
    readonly sent: readonly ClientEffect[];
}

/** The client state after the transcript's step labelled `label`, run as the live driver would run it. */
function checkpointState(transcriptName: TranscriptName, label: string): GameClientState {
    const [error, transcript] = parseSeatTranscript(TRANSCRIPTS[transcriptName]);
    if (error) {
        throw new Error(`${transcriptName}: ${error.message}`);
    }
    const handoff = { gameTicket: "storybook", wsUrl: `ws://storybook/ws/${transcript.gameId}` };
    return scenarioCheckpoint(seatScenarioFromTranscript(transcript, handoff), label);
}

function storyScreen(key: DecisionStoryKey): StoryScreen {
    const { label, pickRiichi, resultPage, transcript } = DECISION_STORIES[key];
    const state = checkpointState(transcript, label);
    const picked = pickRiichi
        ? { ...NO_PLAY_UI, riichiPickWaitId: state.decision?.waitId ?? null }
        : NO_PLAY_UI;
    const ui = nextPlayUi(state, picked, { kind: "show_result_page", page: resultPage });
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

function storybookTemplate(
    screen: StoryScreen,
    show: (story: DecisionStoryKey) => void,
    onCommand: (command: PlayCommand) => void,
): TemplateResult {
    const { sent, state, story, ui } = screen;
    return html`
        <div class="board-page decisions-storybook">
            <div class="board-page__board">
                ${PlayBoard({ display: playDisplay(state, ui), onCommand, table: state.table })}
            </div>
            <div class="board-page__aside">
                <a class="board-storybook__btn" href="/play/storybook">Back</a>
                ${STORY_KEYS.map(
                    (key) => html`<button
                        class="board-storybook__btn ${key === story ? "board-storybook__btn--active" : ""}"
                        @click=${() => show(key)}
                    >${DECISION_STORIES[key].title}</button>`,
                )}
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
        render(storybookTemplate(screen, show, onCommand), host);
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
            screen = { ...screen, sent: step.effects, state: step.state };
        } else {
            screen = { ...screen, ui: nextPlayUi(state, ui, command) };
        }
        draw();
    }

    draw();
    return () => render(nothing, host);
}
