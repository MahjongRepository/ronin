import { afterEach, describe, expect, it } from "vitest";

import { createTournamentsState, parseTournamentLists } from "@/tournaments/state";
import { renderTournaments } from "@/tournaments/ui";

afterEach(() => {
    document.body.replaceChildren();
});

describe("renderTournaments", () => {
    it("shows each tournament's live and finished games, or that it has none", () => {
        const state = createTournamentsState();
        state.lists = parseTournamentLists({
            can_create: true,
            name_max_length: 80,
            others: [],
            own: [
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

    it("offers a guest no create form, asks them to register and lists others' tournaments", () => {
        const state = createTournamentsState();
        state.lists = parseTournamentLists({
            can_create: false,
            name_max_length: 80,
            others: [{ created_at: 0, finished: 0, id: "t3", name: "Open Cup", playing: 1 }],
            own: [],
        });
        const host = document.createElement("main");
        document.body.append(host);
        renderTournaments(host, state, { createTournament: () => {} });

        expect(host.querySelector(".lobby-tournament-form")).toBeNull();
        expect(host.querySelector(".lobby-empty-hint")?.textContent?.trim()).toBe(
            "Register an account to create one.",
        );
        expect(
            [...host.querySelectorAll(".lobby-tournaments-others .lobby-tournament-name")].map(
                (name) => name.textContent,
            ),
        ).toEqual(["Open Cup"]);
    });
});
