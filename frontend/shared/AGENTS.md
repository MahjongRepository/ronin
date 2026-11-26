# Shared frontend source (TypeScript)

Not a package: it gets no `package.json`, lockfile, `.npmrc` or `node_modules`, and is never installed
or built on its own.

* Import only a package both apps depend on at the same version: each app resolves these modules from its own
  `node_modules`.
* The lobby's `package.json` scripts lint, typecheck, test and format this directory.
  Run one file's tests with `cd frontend/lobby && npx vitest run --config vitest.shared.config.ts
  <path>`.
* The Docker builder stages copy only `src/`, so a module imports nothing outside it.
* Text follows `docs/i18n.md` with catalogs of its own (`src/locales/`): shared UI translates through
  `t` from `shared-i18n.ts`, never an app's `t` or catalog. `bin/check_i18n.py` checks them as the
  `shared` app.
* Storage keys and the game handoff key (`session-storage.ts`, *Game client contract* in
  `docs/architecture.md`) are contracts between the apps and with stored browser data; change them
  only with every reader.

## Tests

Vitest in `tests/`, one file per module, importing `@ronin/shared/<module>` and only local setup
(no app fixtures). `describe` names the subject, `it` says what it pins; no doc or file-header
comments.
