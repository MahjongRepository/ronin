# Replay storage format

Storage version `0.4-dev` is a sequence of independent MessagePack maps, compressed together with gzip
level 9 and `mtime=0`. Stored files use `.msgpack.gz`; HTTP serves `application/msgpack` with
`Content-Encoding: gzip`. The browser receives the decompressed record stream. Storage keeps atomic
replacement and owner-only file and directory permissions.

The first record is the version map. Remaining records are the existing gameplay events and seat-control
annotations in their recorded order. There is no outer array, custom action packing, or historical engine.
Unsupported storage versions are rejected. The storage version, RNG version, and rules-profile ID have
separate meanings; changing storage does not change the RNG stream or engine outcomes.

`backend/game/wire/keys.py` declares the named `WireKey` IDs shared with the live protocol;
`backend/game/wire/replay_keys.py` selects the fixed replay metadata keys for this version. The
TypeScript decoder uses the same assignments, pinned together by
`backend/game/tests/fixtures/replay-format-golden.json`. IDs must never be renumbered or reused within a
storage version. Unknown metadata keys are errors. Metadata conversion applies recursively except inside
`gs` and score maps: settings reference keys and setting names stay strings, and score maps retain their
string seat keys. Every list remains a MessagePack array. The sole binary value is `sd`, exactly 96 seed
bytes; the Python and browser read boundaries restore its hexadecimal string.

`gs` contains an integer profile `id` and an `overrides` map. Python owns the complete immutable profile
baselines in `game/logic/rule_profiles.py`; the browser has no registry. Each baseline supplies every
`GameSettings` field explicitly. A completeness validator rejects a profile that would inherit a current
default, and a persisted-baseline test pins its normalized values. Never modify or reuse an existing
profile ID: a new standard baseline requires a new ID. Adding, removing, or renaming a setting requires
deliberate treatment of existing profiles and their completeness check.

Recording compares normalized effective settings against the selected profile and includes every
difference, including false, zero, and changes applied by the server. Resolution rejects unknown IDs and
unknown override names, merges onto the recorded baseline, and applies strict `GameSettings` validation
and engine support checks. Omitted settings never come from current application defaults.

The game-start record independently carries the viewing fields `gt` (game length), `rsv` (riichi-stick
value in wire score units), and `aka` (boolean red-five setting). They come from the same effective
settings as the profile overrides. Playback uses recorded events and these fields; it needs neither the
Python profiles nor a running rules engine. Tenhou export and outcome verification use Python profile
resolution.

A complete record is validated before being returned. Decode errors identify the record number and the
byte offset after the last complete record. A truncated trailing MessagePack record is damaged input,
not an intentionally unfinished game. The browser can retain the valid event prefix and display damage;
a clean stream without a game-end event remains an unfinished replay. Gzip corruption is a separate
transport/decompression failure. Both readers limit decompressed input to 16 MiB and bound strings,
arrays, maps, and binary values. Fixture regeneration and drift checks use this same encoding.
