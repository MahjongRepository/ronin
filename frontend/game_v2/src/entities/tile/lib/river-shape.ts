/**
 * How a river past its normal three rows lies: a top or bottom river's third row runs on along its line (`run-on`), a
 * side river wraps its overflow into a fourth row of six toward its seat (`wrap`).
 */
type RiverOverflow = "run-on" | "wrap";

/** How many discards a river's row holds before the next row starts. */
const RIVER_ROW_SIZE = 6;

/** How many rows a river lays at most: a side river's fourth wraps, a top or bottom river's third runs on. */
const RIVER_ROWS: Readonly<Record<RiverOverflow, number>> = { "run-on": 3, wrap: 4 };

export { RIVER_ROW_SIZE, RIVER_ROWS };
export type { RiverOverflow };
