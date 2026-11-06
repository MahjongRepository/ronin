import { type TemplateResult, html } from "lit-html";

export function unsupportedBrowserTemplate(lobbyUrl: string): TemplateResult {
    return html`<div class="browser-notice" role="alert">
        <h1 class="browser-notice__title">This browser is too old for the game</h1>
        <p class="browser-notice__detail">
            Update to Chrome or Edge 108, Firefox 128, Safari 16.4 or newer, then open the game again.
        </p>
        <a href=${lobbyUrl} role="button">Lobby</a>
    </div>`;
}
