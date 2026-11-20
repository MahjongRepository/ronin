# `internal/wire` test data

- `live-protocol-golden.json`, `replay-format-golden.json`: the wire goldens, owned by
  `golden_test.go`. Each frame or record set is a payload in JSON (keys in wire order, a float
  written with its decimal point, a replay seed in hex) and the bytes it encodes to. Edit a payload,
  then run `go test ./internal/wire -update` to rewrite the bytes and the named keys, and review the
  diff. Every frame the Python server's golden shares (`backend/game/tests/fixtures/`) keeps its
  bytes; only the snapshot differs, its double ron now a ron of two wins. The replay golden adds the
  record shapes the Python one lacks: a pao assigned, a ron holding its win under `WINNERS`, an
  abort showing a hand, an exhaustive draw paying a nagashi mangan. The game client's codec and
  replay reader tests import both goldens.
- `legacy/`: the 25 replays of replay version `0.4-dev` the game client's fixtures held, copied as
  they were: the old-format inputs of the Tenhou export, the client's replay reader and the one-off
  migration.
- `rewritten/`: what rewriting a legacy replay into the current version must produce, byte for
  byte. `rewritten/chankan_added.msgpack` is written by `rewrite_test.go` (`-update`). Its facts
  come from the Python Tenhou export and the game client's viewer of `legacy/chankan_added.msgpack`:
  seat 1 raises its pon of 6p (tiles 56, 57, 58, called 58 from seat 0) to an added kan with tile 59;
  seat 2 robs it, a ron of 6 han 30 fu, haneman, 12000 from seat 1. The rewrite records that kan as
  a meld event ahead of the round end, as the engine now announces a kan before the chankan
  decision, and the round end as a ron holding its one win under `WINNERS`; it keeps every other
  record, and the rules envelope of profile 1, the rules the game was played under.
