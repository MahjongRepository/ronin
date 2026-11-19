import { type TemplateResult, html, nothing, render } from "lit-html";

import { pageFailedView } from "@/app/page-failed";
import { t } from "@/i18n";
import { type OwnTournaments, type TournamentsState, tournamentPath } from "@/tournaments/state";

export interface TournamentsActions {
    readonly createTournament: (name: string) => void;
}

function createFormTemplate(
    state: TournamentsState,
    nameMaxLength: number,
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
            maxlength=${nameMaxLength}
            placeholder=${t("tournaments.name_label")}
            aria-label=${t("tournaments.name_label")}
            autocomplete="off"
        />
        <button type="submit" ?disabled=${state.creating}>${t("tournaments.create")}</button>
    </form>`;
}

function listTemplate(own: OwnTournaments): TemplateResult {
    if (own.tournaments.length === 0) {
        return html`<div class="lobby-empty lobby-empty--boxed lobby-tournaments-empty">
            <p class="lobby-empty-title">${t("tournaments.empty")}</p>
            <p class="lobby-empty-hint">${t("tournaments.empty_hint")}</p>
        </div>`;
    }
    return html`<ul class="lobby-tournament-list">
        ${own.tournaments.map(
            (tournament) =>
                html`<li><a href=${tournamentPath(tournament.id)}>${tournament.name}</a></li>`,
        )}
    </ul>`;
}

function tournamentsTemplate(state: TournamentsState, actions: TournamentsActions): TemplateResult {
    if (state.loadFailed) {
        return pageFailedView();
    }
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
        ${state.own ? createFormTemplate(state, state.own.nameMaxLength, actions) : nothing}
        ${state.own ? listTemplate(state.own) : nothing}
    </section>`;
}

export function renderTournaments(
    host: HTMLElement,
    state: TournamentsState,
    actions: TournamentsActions,
): void {
    document.title = t("page.title.with_page", { page: t("nav.tournaments") });
    render(tournamentsTemplate(state, actions), host);
}
