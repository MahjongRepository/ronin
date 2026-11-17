import { type PlayerState } from "@/entities/table";
import { tile136toString } from "@/entities/tile";

/** Tenhou's hand analysis, which takes a hand in `handNotation`'s form as its query. */
const HAND_ANALYSIS_URL = "https://tenhou.net/2/?q=";

/**
 * A closed hand as one line of faces grouped by suit, `10569m9p1238s4457z`: its tiles sorted, red fives as 0 before
 * their suit's other fives, and the drawn tile apart at the end (`…4457z3m`). Melds are not written.
 */
export function handNotation(
    { drawnTileId, tiles }: Pick<PlayerState, "drawnTileId" | "tiles">,
    hasAkadora: boolean,
): string {
    const drawn = drawnTileId !== null && tiles.includes(drawnTileId) ? [drawnTileId] : [];
    const held = tiles
        .filter((tile) => tile !== drawnTileId)
        .toSorted((first, second) => first - second);
    const faces = [...held, ...drawn].map((tile) => tile136toString(tile, hasAkadora));
    return faces
        .map((face, index) => {
            const [digit, suit] = face;
            return faces[index + 1]?.[1] === suit && index + 1 !== held.length ? digit : face;
        })
        .join("");
}

/** Tenhou's analysis of a hand written as `handNotation` writes it. */
export function handAnalysisUrl(notation: string): string {
    return `${HAND_ANALYSIS_URL}${encodeURIComponent(notation)}`;
}
