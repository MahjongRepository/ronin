import { type TemplateResult, html, nothing, render } from "lit-html";

import {
    type DecisionCountdown,
    type LeaveControls,
    RotatePanel,
    type RotatePanelProps,
    failureDisplay,
} from "@/entities/client";
import { type SessionState, describePlayerSessionStatus } from "@/entities/session";

const HANDOFF = { gameTicket: "story", wsUrl: "ws://story" } as const;
const PLAYING: SessionState = {
    gameId: "story",
    gameStarted: true,
    handoff: HANDOFF,
    status: "playing",
};

const RECONNECTING: SessionState = {
    ...PLAYING,
    attempts: { session: 0, transport: 1 },
    dueAt: 0,
    identity: { kind: "reconnect", lostSeat: true },
    status: "awaiting_retry",
};

const RETRIES_SPENT: SessionState = {
    gameId: "story",
    reason: { gameStarted: true, kind: "retries_exhausted", retry: "transport" },
    status: "ended",
};

/**
 * The rotate panel's stories: a seat waiting on others, one whose decision counts down, one owing a round result's
 * confirm, the edge cases, the question leaving mid-game asks, and an end that stopped the session on the page.
 */
const ROTATE_STORIES = [
    "waiting",
    "countdown",
    "result",
    "untimed",
    "expired",
    "reconnecting",
    "leave",
    "ended",
] as const;

type RotateStory = (typeof ROTATE_STORIES)[number];

const DEFAULT_STORY: RotateStory = "waiting";

const ASKS_TO_LEAVE: LeaveControls = { command: { kind: "ask_leave" }, confirming: false };

function storyProps(
    session: SessionState,
    countdown: DecisionCountdown | null,
    leave: LeaveControls = ASKS_TO_LEAVE,
): RotatePanelProps {
    return {
        countdown,
        failure: failureDisplay(session),
        leave,
        onCommand: () => {},
        status: describePlayerSessionStatus(session),
    };
}

const STORY_PROPS: Readonly<Record<RotateStory, RotatePanelProps>> = {
    countdown: storyProps(PLAYING, {
        kind: "running",
        move: "turn",
        secondsLeft: 17,
        turn: { bankSeconds: 17, baseSeconds: 0, inBank: true },
    }),
    ended: storyProps(RETRIES_SPENT, null),
    expired: storyProps(PLAYING, { kind: "expired", move: "call" }),
    leave: storyProps(PLAYING, null, { ...ASKS_TO_LEAVE, confirming: true }),
    reconnecting: storyProps(RECONNECTING, null),
    result: storyProps(PLAYING, {
        kind: "running",
        move: "result",
        secondsLeft: 8,
        turn: null,
    }),
    untimed: storyProps(PLAYING, { kind: "untimed", move: "turn" }),
    waiting: storyProps(PLAYING, null),
};

function parseStory(search: string): RotateStory {
    const param = new URLSearchParams(search).get("state");
    return ROTATE_STORIES.find((key) => key === param) ?? DEFAULT_STORY;
}

/** Keep the story in the query, beside whatever else the page was opened with (the lobby's `?v=2`). */
function syncStoryParam(story: RotateStory): void {
    const url = new URL(window.location.href);
    if (story === DEFAULT_STORY) {
        url.searchParams.delete("state");
    } else {
        url.searchParams.set("state", story);
    }
    history.replaceState(null, "", url);
}

function rotateStorybookTemplate(
    current: RotateStory,
    show: (story: RotateStory) => void,
): TemplateResult {
    return html`
        <div class="rotate-storybook">
            ${RotatePanel(STORY_PROPS[current])}
            <nav class="rotate-storybook__stories">
                <a class="board-storybook__btn" href="/play/storybook">Back</a>
                ${ROTATE_STORIES.map(
                    (key) => html`<button
                        class="board-storybook__btn ${key === current ? "board-storybook__btn--active" : ""}"
                        @click=${() => show(key)}
                    >${key}</button>`,
                )}
            </nav>
        </div>
    `;
}

/**
 * Mount the rotate panel's storybook: the panel the live game shows on an upright phone, always shown here, in the
 * story the page's `?state=` names.
 */
export function mountStorybookRotate(host: HTMLElement): () => void {
    function show(story: RotateStory): void {
        syncStoryParam(story);
        render(rotateStorybookTemplate(story, show), host);
    }

    show(parseStory(window.location.search));
    return () => render(nothing, host);
}
