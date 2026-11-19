import { afterEach, describe, expect, it } from "vitest";

import { createTournamentsState, parseOwnTournaments } from "@/tournaments/state";
import { renderTournaments } from "@/tournaments/ui";

afterEach(() => {
    document.body.replaceChildren();
});

describe("renderTournaments", () => {
    it("shows each tournament's live and finished games, or that it has none", () => {
        const state = createTournamentsState();
        state.own = parseOwnTournaments({
            name_max_length: 80,
            tournaments: [
                { created_at: 0, finished: 6, id: "t1", name: "Autumn Cup", playing: 2 },
                { created_at: 0, finished: 0, id: "t2", name: "Aye", playing: 0 },
            ],
        });
        const host = document.createElement("main");
        document.body.append(host);
        renderTournaments(host, state, { createTournament: () => {} });

        expect(
            [...host.querySelectorAll(".lobby-tournament-list li")].map((row) => [
                row.querySelector(".lobby-tournament-name")?.textContent,
                row.querySelector(".lobby-tournament-live")?.textContent ?? null,
                [
                    ...row.querySelectorAll(
                        ".lobby-tournament-meta > span:not(.lobby-tournament-live)",
                    ),
                ].map((part) => part.textContent),
            ]),
        ).toEqual([
            ["Autumn Cup", "2 playing", ["6 finished"]],
            ["Aye", null, ["No games yet"]],
        ]);
    });
});
