export type NoticeTone = "info" | "success" | "warning" | "error";

/**
 * A line of news over the table, in its tone: a connection's state, a refused move, a message the client could not
 * read, tile faces that did not load. Where its words run long for the board's field, its `brief` form stands there
 * instead, the words whole in its title and wherever it is read or opened whole. Who shows it adds its controls.
 */
export interface Notice {
    readonly text: string;
    readonly brief?: string;
    readonly tone: NoticeTone;
}
