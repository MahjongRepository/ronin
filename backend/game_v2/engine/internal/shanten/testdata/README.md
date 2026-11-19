# Shanten reference set

`reference.txt.gz` holds one line per hand: its 34 kind counts as digits, then the lowest,
regular, chiitoitsu and kokushi shanten that mahjong-rs counts for it. The hands are the known and
edge hands of the shanten tests, every hand of one and two tiles, and seeded hands of every valid
size from four kind pools.

It was written by mahjong-rs's `shanten_reference` example at commit `f476065` (branch
`go-port-dumpers`; the shanten code is that of `0d8733f`). Regenerate it only when mahjong-rs's
shanten changes on purpose, from the mahjong-rs repository root:

    cargo run --release -q -p mahjong-core --example shanten_reference | gzip -9n > reference.txt.gz
