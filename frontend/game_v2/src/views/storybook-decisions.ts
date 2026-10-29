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
import { boardOverlay } from "@/entities/table";
import { SEAT_TRANSCRIPTS } from "@/fixtures/seat-transcripts";

/**
 * A board at a checkpoint of a generated seat transcript: the client state after the step its label names, as the
 * live game reaches it, with the view's riichi pick on or off.
 */
interface DecisionStory {
    readonly title: string;
    readonly transcript: string;
    readonly label: string;
    readonly pickRiichi: boolean;
}

/** The stories in the order the page lists them: the call prompts, the turns, then what follows an answer. */
const STORY_KEYS = [
    "call_prompt",
    "ron_prompt",
    "kuikae_turn",
    "own_turn",
    "riichi_pick",
    "riichi_turn",
    "answered",
    "round_end",
] as const;

type DecisionStoryKey = (typeof STORY_KEYS)[number];

/** A story at the step labelled `label` of the transcript named `transcript`. */
function checkpoint(transcript: string, label: string, title: string): DecisionStory {
    return { label, pickRiichi: false, title, transcript };
}

const DECISION_STORIES: Readonly<Record<DecisionStoryKey, DecisionStory>> = {
    answered: checkpoint("call_prompt_seat_1", "discarded", "Answered"),
    call_prompt: checkpoint("call_prompt_seat_1", "prompt", "Call prompt"),
    kuikae_turn: checkpoint("call_prompt_seat_1", "turn", "Kuikae turn"),
    own_turn: checkpoint("own_turn_seat_1", "first draw", "Own turn"),
    riichi_pick: {
        ...checkpoint("own_turn_seat_1", "rinshan", "Riichi pick"),
        pickRiichi: true,
    },
    riichi_turn: checkpoint("own_turn_seat_1", "tsumo draw", "In riichi"),
    ron_prompt: checkpoint("reconnect_seat_1", "ron prompt", "Ron prompt"),
    round_end: checkpoint("own_turn_seat_1", "round end", "Round end"),
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
function checkpointState(transcriptName: string, label: string): GameClientState {
    const [error, transcript] = parseSeatTranscript(SEAT_TRANSCRIPTS.get(transcriptName));
    if (error) {
        throw new Error(`${transcriptName}: ${error.message}`);
    }
    const handoff = { gameTicket: "storybook", wsUrl: `ws://storybook/ws/${transcript.gameId}` };
    return scenarioCheckpoint(seatScenarioFromTranscript(transcript, handoff), label);
}

function storyScreen(key: DecisionStoryKey): StoryScreen {
    const { label, pickRiichi, transcript } = DECISION_STORIES[key];
    const state = checkpointState(transcript, label);
    const ui = pickRiichi ? { riichiPickWaitId: state.decision?.waitId ?? null } : NO_PLAY_UI;
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
                ${PlayBoard({ display: playDisplay(state, ui), onCommand, overlay: boardOverlay(state.table) })}
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
