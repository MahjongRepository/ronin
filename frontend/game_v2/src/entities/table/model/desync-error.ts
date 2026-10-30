/**
 * A server message that the state the client holds cannot take: a tile, player, caller or pon it names is not there,
 * or an offer names a tile type the hand holds none of. The client lost step with the server, which is recoverable by
 * a fresh snapshot; any other error a step throws is a bug in the client.
 */
export class DesyncError extends Error {
    override readonly name = "DesyncError";
}
