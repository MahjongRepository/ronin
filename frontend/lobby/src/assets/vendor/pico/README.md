# Local Pico subset

Copied from `@picocss/pico` 2.1.1, the final upstream release:
https://github.com/picocss/pico/tree/v2.1.1/scss

This is Ronin's independently maintained copy. Edit these sources directly; we do not sync
with upstream. No npm package or regeneration step owns them. Only the modules selected by
`src/styles/_pico.scss` and their transitive Sass dependencies were copied. Their source, import order, theme behavior and CSS variable names
were preserved, including the supporting palette and settings definitions. Disabled component
implementations are absent. The lobby now emits only the forced dark scheme: the light theme and
automatic dark copy are removed because every lobby page sets `data-theme="dark"`.

The form subset covers the lobby's text/password inputs, invalid-password feedback and the
chat input/button group. Unused control types, contrast variants, grid and overflow utilities
are removed. Code formatting is imported only by the development stylesheet for storybook prose.

Preserve the original `LICENSE.md` here and its full notice in the app's
`legal/THIRD_PARTY_NOTICES.txt`. Vite copies `legal/` into `dist/`, so the notice accompanies the
built assets and is included in the deployed Docker image. Keep both copies of the license in sync.

These sources keep their existing formatting and are outside the application's stylelint
and formatter scope. Compilation still enforces all active Sass deprecations. Check changes with
`npm run lint` and `npm run build`, plus the frontend visual checks when styling changes.

The game client maintains its own independent subset; neither app imports from the other.
