import { afterAll, afterEach, describe, expect, it, vi } from "vitest";

import { createHistoryState, parseHistory } from "@/history/state";
import { renderHistory } from "@/history/ui";

vi.stubEnv("TZ", "Asia/Tokyo");

const VIEWER_GAME = {
    duration_seconds: 2700,
    game_id: "g1",
    game_type: "hanchan",
    num_rounds_played: 8,
    players: [
        { final_score: 523, is_viewer: false, is_winner: true, name: "Winner", score: 40_000 },
        { final_score: -150, is_viewer: true, is_winner: false, name: "dev", score: 20_000 },
    ],
    replay_url: "/play/history/g1",
    started_at: "2026-10-24T03:09:00+00:00",
    viewer_replay_url: "/play/history/g1?seat=1",
    wind: "南",
};

function renderGames(games: unknown[]): HTMLElement {
    const state = createHistoryState();
    state.games = parseHistory({ games });
    const host = document.createElement("main");
    document.body.append(host);
    renderHistory(host, state);
    return host;
}

afterEach(() => {
    document.body.replaceChildren();
});

afterAll(() => {
    vi.unstubAllEnvs();
});

describe("renderHistory", () => {
    it("shows a game's local start time, rounds, translated type, final scores from tenths and the viewer's replay link", () => {
        const host = renderGames([VIEWER_GAME]);

        const time = host.querySelector("time.games-time");
        expect(time?.textContent).toMatch(/24.*12:09/);
        expect(time?.getAttribute("datetime")).toBe("2026-10-24T03:09:00.000Z");
        expect([...host.querySelectorAll(".games-meta-tag")].map((tag) => tag.textContent)).toEqual(
            ["45m 0s", "8 rounds"],
        );
        expect(host.querySelector(".games-type")?.textContent).toBe("Hanchan");
        expect(host.querySelector(".games-card-link")?.getAttribute("href")).toBe(
            "/play/history/g1?seat=1",
        );
        expect(host.querySelector(".games-copy-btn")?.getAttribute("data-replay-url")).toBe(
            "/play/history/g1",
        );
        expect(host.querySelector(".games-standing--me .games-name")?.textContent).toBe("dev");
        expect(
            [...host.querySelectorAll(".games-pts")].map((points) => points.textContent),
        ).toEqual(["+52.3", "-15.0"]);
    });

    it("points an empty history at quick match and the lobby's tables", () => {
        const host = renderGames([]);

        const hint = host.querySelector(".lobby-empty-hint");
        expect(hint?.textContent?.replace(/\s+/g, " ").trim()).toBe(
            "Start a quick match or join a table in the lobby. Finished games and their replays show up here.",
        );
        expect([...(hint?.querySelectorAll("a") ?? [])].map((a) => a.getAttribute("href"))).toEqual(
            ["/matchmaking", "/"],
        );
        expect(host.querySelector(".games-list")).toBeNull();
    });
});
