// Package wire is the game server's wire format, read by the server, the replay tools and the
// clients: the metadata keys, the integer codes of events and results, the packed draws, discards
// and melds, the MessagePack codec of a live message and the replay codec with its format version.
//
// Its bytes are a contract. A message is built as a Map, an ordered list of keyed values, never
// from a Go map, so its keys encode in the order it lists them; an integer takes the fewest bytes
// that hold it, a float is always a float64, so an Int and a Float of one number differ on the
// wire, strings take str8 from 32 bytes, and binary data appears only as a replay's seed. Keys and
// codes are only ever added: a retired one leaves its gap.
//
// Ported from ronin's Python game server: its wire package, the MessagePack codec of its messaging
// package and its integer-mapped meld encoding.
package wire
