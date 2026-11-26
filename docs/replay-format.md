# Replay storage format

Storage version `0.5-dev` is a sequence of independent MessagePack maps, compressed together with gzip
level 9 and no modification time. Stored files use `.msgpack.gz`; HTTP serves `application/msgpack` with
`Content-Encoding: gzip`, at a URL carrying the version (`?v=0.5-dev`) so a browser's cached copy of an
older version is never read as this one. The browser receives the decompressed record stream. Storage
keeps atomic replacement and owner-only file and directory permissions.

The first record is the version map. Remaining records are the gameplay events and seat-control
annotations in their recorded order. There is no outer array, custom action packing, or historical engine.
Unsupported storage versions are rejected. The storage version, RNG version, and rules-profile ID have
separate meanings; changing storage does not change the RNG stream or engine outcomes.

A live game's observer stream (`GET /games/{game_id}/observe`) carries the same records in the same
encoding, delayed, except that its game start holds no `sd`: the seed derives every wall, so no observer
answer holds it. The version map comes only ahead of the records of the first answer that holds any to a
read from the start (`from=0`); an empty answer and every answer to a later cursor carry none, so the
answers' records joined in order read as a replay without its seed.

`backend/game_v2/internal/wire` declares the named key IDs shared with the live protocol, the replay key
set (every key through `YAKU_YAKUMAN_COUNT`, plus `SHOWN_HANDS` and `PLACE`) and the replay schema: the fields each
record and result type requires and each field's type, checked on encode and decode alike. The TypeScript
decoder uses the same assignments, pinned together by
`backend/game_v2/internal/wire/testdata/replay-format-golden.json`. IDs, event codes and result codes are
never renumbered or reused. Unknown metadata keys are errors. Metadata conversion applies recursively
except inside `gs` and score maps: settings reference keys and setting names stay strings, and score maps
retain their string seat keys. Every list remains a MessagePack array. The sole binary value is `sd`,
exactly 96 seed bytes; the browser's read boundary restores its hexadecimal string.

Against `0.4-dev`, the records differ in these shapes:

* a ron is result type 1 holding one to three wins under `WINNERS`, each with its hand, payments and pao;
  type 2 (double ron) is retired;
* a nagashi mangan is an exhaustive draw naming `QUALIFYING_SEATS` and `QUALIFYING_RIVERS`; type 5 is
  retired;
* an abortive draw may name the hands it shows under `SHOWN_HANDS` (the kyuushu declarer's, every hand at
  four riichi, the triple ron's callers');
* a kan's meld event comes before the chankan decision, so a robbed kan is the meld event ahead of the
  ron that robs it, and no round end names `ROBBED_KAN`;
* `PAO_ASSIGNED` (event 14) follows the call that makes a seat liable;
* a standing's `FINAL_SCORE` is the uma/oka-adjusted result in whole tenths of a point, unrounded;
* a standing may carry its `PLACE` from 1, which tied seats share under a ruleset that splits ties; a
  replay written before it existed has none, and its standings rank by their order.

`backend/game_v2/cmd/migrate` rewrites every stored `0.4-dev` replay into this version once, keeping
profile 1 and the game as it was scored: the old whole-point `FINAL_SCORE` times ten, no `SHOWN_HANDS` on
an abort, a robbed kan's meld (a pon raised by the robbed tile, or the four copies of a robbed closed kan)
right after the declarer's last record, and `PAO_ASSIGNED` after the pon or open kan that completed a
seat's third dragon or fourth wind from another seat's discard, checked against each win's pao seat. A
replay it cannot carry over whole is left as it was and reported.

`gs` contains an integer profile `id` and an empty `overrides` map. Each engine ruleset has its own
profile ID, and the Go server records the game's: `{"id": 2, "overrides": {}}` for Tenhou and
`{"id": 3, "overrides": {}}` for RRC. A replay rewritten from `0.4-dev` keeps profile 1, the rules it was played under, so the
two are told apart. The Go reader accepts a ruleset's ID and profile 1 only, and no overrides; the
browser keeps the envelope opaque and has no registry.

The game-start record independently carries the viewing fields `gt` (game length), `rsv` (riichi-stick
value in wire score units), and `aka` (boolean red-five setting). Playback uses recorded events and these
fields; it needs neither the preset nor a running rules engine. The Tenhou export takes its game type from
`gt` and `aka`.

A complete record is validated before being returned. Decode errors identify the record number and the
byte offset after the last complete record. A truncated trailing MessagePack record is damaged input,
not an intentionally unfinished game. The browser can retain the valid event prefix and display damage;
a clean stream without a game-end event remains an unfinished replay. Gzip corruption is a separate
transport/decompression failure. Both readers limit decompressed input to 16 MiB and bound strings,
arrays, maps, and binary values. Fixture regeneration (`make generate-fixtures`) and its drift check use
this same encoding.
