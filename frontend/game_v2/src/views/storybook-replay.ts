import { DEFAULT_REPLAY_PREFS, type ReplayPrefs, type StandingsRenderer } from "@/entities/table";
import { type LoadReplay, type ReplayFetch } from "@/shared/api";
import { type Clock, browserClock } from "@/shared/clock";
import { getLobbyHistoryUrl, getLobbyUrl } from "@/shared/config";
import { type RetryingLoad } from "@/shared/lib";
import { REPLAY_VERSION } from "@/shared/protocol";

import { startStorybookStandings } from "./storybook-standings";

/** The replay page's stories: positions of generated replays, and every way a replay may fail to show. */
export const REPLAY_STORIES = [
    "start",
    "mid",
    "autoplay",
    "viewpoint_hidden",
    "double_ron",
    "result_hidden",
    "standings",
    "standings_long",
    "round_list",
    "incomplete",
    "ends_on_result",
    "damaged",
    "throws_on_step",
    "loading",
    "waiting",
    "not_found",
    "unreachable",
    "unsupported",
    "no_round",
] as const;

type ReplayStory = (typeof REPLAY_STORIES)[number];

interface StorySetup {
    readonly load: LoadReplay;
    /** The page's query: the position the story opens at. */
    readonly search: string;
    readonly roundListOpen?: boolean;
    /** Opens with autoplay running; on `STILL_CLOCK` it holds its stop. */
    readonly autoplay?: boolean;
    /**
     * The clock the view runs on: the browser's, so its input keeps its real timing (a click never lasts as long as a
     * held button's delay), unless the story needs its timers hurried or stilled.
     */
    readonly clock?: Clock;
    readonly prefs?: ReplayPrefs;
    /** The final standings' load; the storybook's own, on hurried timers, when omitted. */
    readonly standings?: () => RetryingLoad<StandingsRenderer>;
}

type FixtureImport = () => Promise<{ readonly default: string }>;

const NEVER = new Promise<ReplayFetch>(() => {});
const NOT_FOUND: ReplayFetch = { ok: false, status: 404 };

function paoReplay(): Promise<{ readonly default: string }> {
    return import("@/fixtures/replays/pao.txt?raw");
}

/** A load answered with a generated replay, which its story's own chunk carries, rewritten by `edit`. */
function servesFixture(fixture: FixtureImport, edit = (text: string) => text): LoadReplay {
    return async () => {
        const loaded = await fixture();
        return { ok: true, text: edit(loaded.default) };
    };
}

function serves(text: string): LoadReplay {
    return () => Promise.resolve({ ok: true, text });
}

/** A replay with a line broken past its first moves: a damaged replay that still opens. */
function withBrokenLine(text: string): string {
    const lines = text.trimEnd().split("\n");
    return [...lines.slice(0, 12), "{broken", ...lines.slice(12)].join("\n");
}

function notFoundThen(next: Promise<ReplayFetch>): LoadReplay {
    let calls = 0;
    return () => {
        calls += 1;
        return calls === 1 ? Promise.resolve(NOT_FOUND) : next;
    };
}

/**
 * Final standings whose drawing throws, as a bug in drawing would: stepping onto the game's end shows the replay's
 * failure screen.
 */
function throwingStandings(): RetryingLoad<StandingsRenderer> {
    return {
        status: () => "ready",
        stop: () => {},
        subscribe: () => () => {},
        value: () => (table) => {
            if (table.phase === "game_ended") {
                throw new Error("The standings story throws as it draws");
            }
            return undefined;
        },
    };
}

/** A clock whose timers never fire: autoplay's story stays on the stop it opened on. */
const STILL_CLOCK: Clock = { now: () => Date.now(), setTimer: () => () => {} };

/** A clock whose timers fire at once, so a story's retries are spent before it is looked at. */
const HURRIED_CLOCK: Clock = {
    now: () => Date.now(),
    setTimer: (_delayMs, callback) => {
        const handle = setTimeout(callback, 0);
        return () => clearTimeout(handle);
    },
};

const STORIES: Readonly<Record<ReplayStory, StorySetup>> = {
    autoplay: {
        autoplay: true,
        clock: STILL_CLOCK,
        load: servesFixture(paoReplay),
        prefs: { hideHands: false, speed: 2 },
        search: "?round=0&step=14",
    },
    damaged: { load: servesFixture(paoReplay, withBrokenLine), search: "?round=0&step=8" },
    double_ron: {
        load: servesFixture(() => import("@/fixtures/replays/double_ron_head_bump.txt?raw")),
        search: "?round=0&step=2",
    },
    ends_on_result: {
        load: servesFixture(() => import("@/fixtures/replays/truncated_after_round.txt?raw")),
        search: "?round=1&step=140",
    },
    incomplete: {
        load: servesFixture(() => import("@/fixtures/replays/truncated_mid_round.txt?raw")),
        search: "?round=0&step=23",
    },
    loading: { load: () => NEVER, search: "" },
    mid: { load: servesFixture(paoReplay), search: "?round=0&step=14" },
    no_round: { load: serves(JSON.stringify({ version: REPLAY_VERSION })), search: "" },
    not_found: { clock: HURRIED_CLOCK, load: () => Promise.resolve(NOT_FOUND), search: "" },
    result_hidden: {
        load: servesFixture(() => import("@/fixtures/replays/double_ron_head_bump.txt?raw")),
        prefs: { hideHands: true, speed: 1 },
        search: "?round=0&step=2",
    },
    round_list: {
        load: servesFixture(() => import("@/fixtures/replays/ai_replacements.txt?raw")),
        roundListOpen: true,
        search: "?round=1&step=3",
    },
    standings: { load: servesFixture(paoReplay), search: "?round=0&step=24" },
    standings_long: {
        load: servesFixture(() => import("@/fixtures/replays/full_game.txt?raw")),
        search: "?round=11&step=141",
    },
    start: { load: servesFixture(paoReplay), search: "" },
    throws_on_step: {
        load: servesFixture(paoReplay),
        search: "?round=0&step=23",
        standings: throwingStandings,
    },
    unreachable: { load: () => Promise.reject(new TypeError("Failed to fetch")), search: "" },
    unsupported: { load: serves('{"version": "0.1"}\n{"t": 8}'), search: "" },
    viewpoint_hidden: {
        load: servesFixture(paoReplay),
        prefs: { hideHands: true, speed: 1 },
        search: "?seat=2&round=0&step=18",
    },
    waiting: { load: notFoundThen(NEVER), search: "" },
};

function parseStory(search: string): ReplayStory {
    const param = new URLSearchParams(search).get("state");
    return REPLAY_STORIES.find((key) => key === param) ?? "start";
}

/**
 * Mount the replay page's storybook: the replay view itself, whole-page as on its route and from its route's own
 * chunk, in the story the page's `?state=` names, its loads answered from generated replays (each loaded with its
 * story) and its address kept to itself. The index page links every story.
 */
export function mountStorybookReplay(host: HTMLElement): () => void {
    const story = STORIES[parseStory(window.location.search)];
    let dispose: (() => void) | null = null;
    let disposed = false;
    async function mount(): Promise<void> {
        const { mountReplayView } = await import("@/views/replay");
        if (disposed) {
            return;
        }
        dispose = mountReplayView(host, "story", {
            autoplay: story.autoplay ?? false,
            clock: story.clock ?? browserClock,
            links: { history: getLobbyHistoryUrl(), lobby: getLobbyUrl() },
            loadReplay: story.load,
            location: { onPageHide: () => () => {}, replaceSearch: () => {}, search: story.search },
            prefs: { load: () => story.prefs ?? DEFAULT_REPLAY_PREFS, save: () => {} },
            roundListOpen: story.roundListOpen ?? false,
            startStandings:
                story.standings ?? (() => startStorybookStandings(HURRIED_CLOCK.setTimer)),
        });
    }
    void mount();
    return () => {
        disposed = true;
        dispose?.();
    };
}
