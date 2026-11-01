export type NoticeTone = "info" | "success" | "warning" | "error";

/**
 * A line of news over the table, in its tone: a connection's state, a refused move, a message the client could not
 * read, tile faces that did not load. Who shows it adds its controls.
 */
export interface Notice {
    readonly text: string;
    readonly tone: NoticeTone;
}
