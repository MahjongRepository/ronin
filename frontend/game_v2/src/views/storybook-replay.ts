import { encode } from "@msgpack/msgpack";

import { DEFAULT_MOTION_SETTING, type GameSound } from "@/entities/client";
import { DEFAULT_REPLAY_PREFS, type ReplayPrefs } from "@/entities/replay";
import { type LoadReplay, type ReplayFetch } from "@/shared/api";
import { type Clock, browserClock } from "@/shared/clock";
import { getLobbyHistoryUrl, getLobbyUrl } from "@/shared/config";
import { applyPageLocale } from "@/shared/i18n";
import { REPLAY_VERSION, WIRE_KEY } from "@/shared/protocol";

/** A storybook replay plays no sound, with the sound off. */
const SILENT: GameSound = {
    play: () => {},
    setting: { load: () => ({ sound_on: false }), save: () => {} },
};

/** The replay page's stories: positions of generated replays, and every way a replay may fail to show. */
export const REPLAY_STORIES = [
    "start",
    "custom_settings",
    "seating",
    "mid",
    "autoplay",
    "viewpoint_hidden",
    "double_ron",
    "result_hidden",
    "game_end",
    "round_list",
    "incomplete",
    "ends_on_result",
    "damaged",
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
}

type FixtureImport = () => Promise<{ readonly default: string }>;

const NEVER = new Promise<ReplayFetch>(() => {});
const NOT_FOUND: ReplayFetch = { ok: false, status: 404 };

function paoReplay(): Promise<{ readonly default: string }> {
    return import("@/fixtures/replays/pao.msgpack?inline");
}

/** A load answered with a generated replay, which its story's own chunk carries, rewritten by `edit`. */
function servesFixture(
    fixture: FixtureImport,
    edit = (content: Uint8Array) => content,
): LoadReplay {
    return async () => {
        const loaded = await fixture();
        const content = Uint8Array.from(atob(loaded.default.split(",")[1]), (character) =>
            character.charCodeAt(0),
        );
        return { content: edit(content), ok: true };
    };
}

function serves(content: Uint8Array): LoadReplay {
    return () => Promise.resolve({ content, ok: true });
}

/** A replay with a line broken past its first moves: a damaged replay that still opens. */
function withBrokenLine(content: Uint8Array): Uint8Array {
    return content.slice(0, Math.floor(content.length / 2));
}

function versionRecord(version: string): Uint8Array {
    return new Uint8Array([0x81, WIRE_KEY.REPLAY_VERSION, ...encode(version)]);
}

function notFoundThen(next: Promise<ReplayFetch>): LoadReplay {
    let calls = 0;
    return () => {
        calls += 1;
        return calls === 1 ? Promise.resolve(NOT_FOUND) : next;
    };
}

/** A clock whose timers never fire: autoplay's story stays on the stop it opened on. */
const STILL_CLOCK: Clock = { now: browserClock.now, setTimer: () => () => {} };

/** A clock whose timers fire at once, so a story's retries are spent before it is looked at. */
const HURRIED_CLOCK: Clock = {
    now: browserClock.now,
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
        prefs: { hideHands: false },
        search: "?round=0&step=14",
    },
    custom_settings: {
        load: servesFixture(() => import("@/fixtures/replays/custom_settings.msgpack?inline")),
        search: "?round=0&step=0",
    },
    damaged: { load: servesFixture(paoReplay, withBrokenLine), search: "?round=0&step=8" },
    double_ron: {
        load: servesFixture(() => import("@/fixtures/replays/double_ron_head_bump.msgpack?inline")),
        search: "?round=0&step=2",
    },
    ends_on_result: {
        load: servesFixture(
            () => import("@/fixtures/replays/truncated_after_round.msgpack?inline"),
        ),
        search: "?round=1&step=140",
    },
    game_end: { load: servesFixture(paoReplay), search: "?round=0&step=24" },
    incomplete: {
        load: servesFixture(() => import("@/fixtures/replays/truncated_mid_round.msgpack?inline")),
        search: "?round=0&step=23",
    },
    loading: { load: () => NEVER, search: "" },
    mid: { load: servesFixture(paoReplay), search: "?round=0&step=14" },
    no_round: { load: serves(versionRecord(REPLAY_VERSION)), search: "" },
    not_found: { clock: HURRIED_CLOCK, load: () => Promise.resolve(NOT_FOUND), search: "" },
    result_hidden: {
        load: servesFixture(() => import("@/fixtures/replays/double_ron_head_bump.msgpack?inline")),
        prefs: { hideHands: true },
        search: "?round=0&step=2",
    },
    round_list: {
        load: servesFixture(() => import("@/fixtures/replays/ai_replacements.msgpack?inline")),
        roundListOpen: true,
        search: "?round=1&step=3",
    },
    seating: { load: servesFixture(paoReplay), search: "" },
    start: { load: servesFixture(paoReplay), search: "?round=0&step=0" },
    unreachable: { load: () => Promise.reject(new TypeError("Failed to fetch")), search: "" },
    unsupported: { load: serves(versionRecord("0.1")), search: "" },
    viewpoint_hidden: {
        load: servesFixture(paoReplay),
        prefs: { hideHands: true },
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
            motionSetting: { load: () => DEFAULT_MOTION_SETTING, save: () => {} },
            prefs: { load: () => story.prefs ?? DEFAULT_REPLAY_PREFS, save: () => {} },
            roundListOpen: story.roundListOpen ?? false,
            setLanguage: applyPageLocale,
            sound: SILENT,
        });
    }
    void mount();
    return () => {
        disposed = true;
        dispose?.();
    };
}
