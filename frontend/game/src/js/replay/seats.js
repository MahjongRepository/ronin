/** The seats at a table, numbered from 0. */
export const SEATS = 4;

/** Whether `value` names a seat: a whole number from 0 below `SEATS`. */
export function isSeat(value) {
    return Number.isInteger(value) && value >= 0 && value < SEATS;
}
