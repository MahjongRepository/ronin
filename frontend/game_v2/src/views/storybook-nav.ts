import { type TemplateResult, html } from "lit-html";

interface StorybookPage {
    path: string;
    title: string;
}

const STORYBOOK_PAGES: StorybookPage[] = [
    { path: "/play/storybook", title: "Index" },
    { path: "/play/storybook/board", title: "Board" },
    { path: "/play/storybook/discards", title: "Discards" },
    { path: "/play/storybook/hand", title: "Hand" },
    { path: "/play/storybook/melds", title: "Melds" },
];

/** Renders the storybook header with a row of badge links.
 * The badge matching `currentPath` gets the `active` class. */
function storybookNav(currentPath: string): TemplateResult {
    return html`
        <h1>Game Storybook</h1>
        <nav class="storybook-nav">
            ${STORYBOOK_PAGES.map((page) => {
                const cls =
                    page.path === currentPath ? "storybook-badge active" : "storybook-badge";
                return html`<a href="${page.path}" class="${cls}">${page.title}</a>`;
            })}
        </nav>
    `;
}

export { storybookNav, STORYBOOK_PAGES };
