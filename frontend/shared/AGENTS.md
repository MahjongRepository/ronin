# Shared frontend source (TypeScript)

Source both apps import as `@ronin/shared/<module>`: no package.json, lockfile, `.npmrc` or
`node_modules`, never installed and never built on its own. Each app's Vite bundles the modules it
imports, and each app's `tsc` checks them.

* `src/` is flat: modules import each other as `./<module>`, never `@/` (each app binds `@/` to its
  own `src/`), and never import an app.
* Dependencies resolve from the importing app's `node_modules`; both apps pin the same versions, and
  both dedupe `lit-html`, so a bundle holds one copy. Add an import only of a package both apps
  depend on at the same version.
* The lobby's scripts check this directory: `lint` (this `.oxlintrc.json`), `typecheck` (this
  `tsconfig.json`, resolving packages from `../lobby/node_modules`), `test`
  (`frontend/lobby/vitest.shared.config.ts`) and `fmt`/`fmt:check` (the lobby's `.oxfmtrc.json`).
  Run one file's tests with `cd frontend/lobby && npx vitest run --config vitest.shared.config.ts
  <path>`.
* The Docker builder stages copy only `src/`, so a module imports nothing outside it.
* Storage keys and the game handoff key (`session-storage.ts`, *Game client contract* in
  `docs/architecture.md`) are contracts between the apps and with stored browser data; change them
  only with every reader.

## Tests

Vitest in `tests/`, one file per module, importing `@ronin/shared/<module>` and only local setup
(no app fixtures). `describe` names the subject, `it` says what it pins; no doc or file-header
comments.
