import { type TemplateResult, html, nothing, render } from "lit-html";

import { pageFailedView } from "@/app/page-failed";
import { formatDate, t } from "@/i18n";
import { listLoadingTemplate } from "@/list-loading";
import {
    type TournamentLists,
    type TournamentRow,
    type TournamentsState,
    tournamentPath,
} from "@/tournaments/state";

const tournamentCreationHidden = true;

export interface TournamentsActions {
    readonly createTournament: (name: string) => void;
}

/** Draws the create form; a null `nameMaxLength` is the page still loading, which disables the form. */
function createFormTemplate(
    state: TournamentsState,
    nameMaxLength: number | null,
    actions: TournamentsActions,
): TemplateResult {
    function submitCreate(event: SubmitEvent): void {
        event.preventDefault();
        const form = event.currentTarget;
        const input = form instanceof HTMLFormElement ? form.elements.namedItem("name") : null;
        if (input instanceof HTMLInputElement) {
            actions.createTournament(input.value);
        }
    }
    return html`<form class="lobby-tournament-form" @submit=${submitCreate}>
        <input
            type="text"
            name="name"
            required
            maxlength=${nameMaxLength ?? nothing}
            ?disabled=${nameMaxLength === null}
            placeholder=${t("tournaments.name_label")}
            aria-label=${t("tournaments.name_label")}
            autocomplete="off"
        />
        <button type="submit" ?disabled=${state.creating || nameMaxLength === null}>
            ${t("tournaments.create")}
        </button>
    </form>`;
}

function gamesTemplate(tournament: TournamentRow): TemplateResult {
    if (tournament.playing === 0 && tournament.finished === 0) {
        return html`<span>${t("tournaments.row.no_games")}</span>`;
    }
    return html`${
        tournament.playing > 0
            ? html`<span class="lobby-tournament-live"
                  >${t("current_games.count", { count: tournament.playing })}</span
              >`
            : nothing
    }${
        tournament.finished > 0
            ? html`<span>${t("tournaments.row.finished", { count: tournament.finished })}</span>`
            : nothing
    }`;
}

function rowTemplate(tournament: TournamentRow): TemplateResult {
    return html`<li>
        <a href=${tournamentPath(tournament.id)}>
            <span class="lobby-tournament-name">${tournament.name}</span>
            <span class="lobby-tournament-meta">
                ${
                    tournament.finishedAt === null
                        ? nothing
                        : html`<span class="lobby-tournament-ended">${t("tournaments.row.ended")}</span>`
                }
                ${gamesTemplate(tournament)}
                <time datetime=${tournament.createdAt.toISOString()}>${formatDate(tournament.createdAt)}</time>
            </span>
        </a>
    </li>`;
}

function rowsTemplate(rows: readonly TournamentRow[]): TemplateResult {
    return html`<ul class="lobby-tournament-list">
        ${rows.map((tournament) => rowTemplate(tournament))}
    </ul>`;
}

function ownListTemplate(lists: TournamentLists): TemplateResult {
    if (lists.own.length === 0) {
        return html`<div class="lobby-empty lobby-empty--boxed lobby-tournaments-empty">
            <p class="lobby-empty-title">${t("tournaments.empty")}</p>
            ${
                tournamentCreationHidden
                    ? nothing
                    : html`<p class="lobby-empty-hint">
                          ${t(lists.canCreate ? "tournaments.empty_hint" : "tournaments.empty_hint_guest")}
                      </p>`
            }
        </div>`;
    }
    return rowsTemplate(lists.own);
}

function othersListTemplate(lists: TournamentLists): TemplateResult {
    if (lists.others.length === 0) {
        return html`<div class="lobby-empty lobby-empty--boxed lobby-tournaments-empty">
            <p class="lobby-empty-title">${t("tournaments.others_empty")}</p>
        </div>`;
    }
    return rowsTemplate(lists.others);
}

function ownSectionTemplate(state: TournamentsState, actions: TournamentsActions): TemplateResult {
    return html`<section class="lobby-section lobby-tournaments">
        <div class="lobby-section-header">
            <h2>${t("tournaments.title")}</h2>
        </div>
        ${
            state.createFailed
                ? html`<div class="lobby-alert" role="alert">
                      <p>${t("tournaments.create_failed")}</p>
                  </div>`
                : nothing
        }
        ${
            tournamentCreationHidden || state.lists?.canCreate === false
                ? nothing
                : createFormTemplate(state, state.lists?.nameMaxLength ?? null, actions)
        }
        ${state.lists ? ownListTemplate(state.lists) : listLoadingTemplate("compact-rows", 3)}
    </section>`;
}

function othersSectionTemplate(state: TournamentsState): TemplateResult {
    return html`<section class="lobby-section lobby-tournaments-others">
        <div class="lobby-section-header">
            <h2>${t("tournaments.others_title")}</h2>
        </div>
        ${state.lists ? othersListTemplate(state.lists) : listLoadingTemplate("compact-rows", 3)}
    </section>`;
}

function tournamentsTemplate(state: TournamentsState, actions: TournamentsActions): TemplateResult {
    if (state.loadFailed) {
        return pageFailedView();
    }
    return html`${ownSectionTemplate(state, actions)} ${othersSectionTemplate(state)}`;
}

export function renderTournaments(
    host: HTMLElement,
    state: TournamentsState,
    actions: TournamentsActions,
): void {
    document.title = t("page.title.with_page", { page: t("nav.tournaments") });
    render(tournamentsTemplate(state, actions), host);
}
