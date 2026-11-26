package wire

import (
	"slices"
	"strconv"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	chiCount        = 21 * 64 * 3
	ponCount        = tile.KindCount * 4 * 3 * 3
	openKanCount    = tile.KindCount * 4 * 3
	ponOffset       = chiCount
	addedKanOffset  = ponOffset + ponCount
	openKanOffset   = addedKanOffset + ponCount
	closedKanOffset = openKanOffset + openKanCount
	meldIndexCount  = closedKanOffset + tile.KindCount

	chiStartsPerSuit = 7
	ranksPerSuit     = 9
	suitedKinds      = 3 * ranksPerSuit
	meldTiles        = 3
	kanTiles         = tile.CopiesPerKind
	fromOffsets      = 3
	copySum          = 0 + 1 + 2 + 3
)

type Meld struct {
	Caller tile.Seat
	Kind   play.MeldKind
	Tiles  []tile.TileID
	Called play.Option[tile.TileID]
	From   play.Option[tile.Seat]
	Added  play.Option[tile.TileID]
}

type InvalidMeldError struct {
	Reason string
}

func (e InvalidMeldError) Error() string {
	return "invalid meld: " + e.Reason
}

func PackMeld(m Meld) (int, error) {
	tiles := slices.SortedFunc(slices.Values(m.Tiles), tile.TileID.Compare)
	if m.Added.OK && m.Kind != play.MeldAddedKan {
		return 0, InvalidMeldError{Reason: "only an added kan has an added tile"}
	}

	var index int
	var err error
	switch m.Kind {
	case play.MeldChi:
		index, err = chiIndex(m, tiles)
	case play.MeldPon:
		index, err = ponIndex(m, tiles)
		index += ponOffset
	case play.MeldAddedKan:
		index, err = addedKanIndex(m, tiles)
		index += addedKanOffset
	case play.MeldOpenKan:
		index, err = openKanIndex(m, tiles)
		index += openKanOffset
	case play.MeldClosedKan:
		index, err = closedKanIndex(m, tiles)
		index += closedKanOffset
	default:
		err = InvalidMeldError{Reason: "unknown meld kind " + strconv.Itoa(int(m.Kind))}
	}
	if err != nil {
		return 0, err
	}
	return index*tile.SeatCount + m.Caller.Index(), nil
}

func chiIndex(m Meld, tiles []tile.TileID) (int, error) {
	if len(tiles) != meldTiles {
		return 0, InvalidMeldError{Reason: "a chi has three tiles"}
	}
	low := tiles[0].Kind()
	if low >= suitedKinds || int(low)%ranksPerSuit >= chiStartsPerSuit ||
		tiles[1].Kind() != low+1 || tiles[2].Kind() != low+2 {
		return 0, InvalidMeldError{Reason: "a chi is three suited tiles in a row"}
	}
	if m.From != play.Some(m.Caller.Kamicha()) {
		return 0, InvalidMeldError{Reason: "a chi calls the kamicha's discard"}
	}
	calledAt, err := calledPosition(m, tiles)
	if err != nil {
		return 0, err
	}

	base := int(low)/ranksPerSuit*chiStartsPerSuit + int(low)%ranksPerSuit
	copies := copyOf(tiles[0])*16 + copyOf(tiles[1])*4 + copyOf(tiles[2])
	return (base*64+copies)*meldTiles + calledAt, nil
}

func ponIndex(m Meld, tiles []tile.TileID) (int, error) {
	if !isOneKind(tiles, meldTiles) {
		return 0, InvalidMeldError{Reason: "a pon or kan is copies of one kind"}
	}
	calledAt, err := calledPosition(m, tiles)
	if err != nil {
		return 0, err
	}
	from, err := fromOffset(m)
	if err != nil {
		return 0, err
	}

	missing := copySum
	for _, t := range tiles {
		missing -= copyOf(t)
	}
	return ((int(tiles[0].Kind())*tile.CopiesPerKind+missing)*meldTiles+calledAt)*fromOffsets + from, nil
}

func addedKanIndex(m Meld, tiles []tile.TileID) (int, error) {
	if !m.Added.OK || !slices.Contains(tiles, m.Added.Value) || m.Called == play.Some(m.Added.Value) {
		return 0, InvalidMeldError{Reason: "an added kan adds one of its tiles other than the called one"}
	}
	if !isOneKind(tiles, kanTiles) {
		return 0, InvalidMeldError{Reason: "a pon or kan is copies of one kind"}
	}
	pon := slices.DeleteFunc(slices.Clone(tiles), func(t tile.TileID) bool { return t == m.Added.Value })
	return ponIndex(m, pon)
}

func openKanIndex(m Meld, tiles []tile.TileID) (int, error) {
	if !isOneKind(tiles, kanTiles) {
		return 0, InvalidMeldError{Reason: "a pon or kan is copies of one kind"}
	}
	_, err := calledPosition(m, tiles)
	if err != nil {
		return 0, err
	}
	from, err := fromOffset(m)
	if err != nil {
		return 0, err
	}
	return (int(tiles[0].Kind())*tile.CopiesPerKind+copyOf(m.Called.Value))*fromOffsets + from, nil
}

func closedKanIndex(m Meld, tiles []tile.TileID) (int, error) {
	if !isOneKind(tiles, kanTiles) {
		return 0, InvalidMeldError{Reason: "a pon or kan is copies of one kind"}
	}
	if m.Called.OK || m.From.OK {
		return 0, InvalidMeldError{Reason: "a closed kan calls no discard"}
	}
	return int(tiles[0].Kind()), nil
}

func isOneKind(tiles []tile.TileID, size int) bool {
	if len(tiles) != size {
		return false
	}
	for i, t := range tiles[1:] {
		if t.Kind() != tiles[0].Kind() || t == tiles[i] {
			return false
		}
	}
	return true
}

func calledPosition(m Meld, tiles []tile.TileID) (int, error) {
	at := slices.Index(tiles, m.Called.Value)
	if !m.Called.OK || at < 0 {
		return 0, InvalidMeldError{Reason: "a called meld holds its called tile"}
	}
	return at, nil
}

func fromOffset(m Meld) (int, error) {
	if !m.From.OK || m.From.Value == m.Caller {
		return 0, InvalidMeldError{Reason: "a called meld calls another seat's discard"}
	}
	return m.From.Value.DistanceFrom(m.Caller) - 1, nil
}

func copyOf(t tile.TileID) int {
	return t.Index() % tile.CopiesPerKind
}

func UnpackMeld(packed int) (Meld, error) {
	if packed < 0 || packed >= meldIndexCount*tile.SeatCount {
		return Meld{}, InvalidMeldError{Reason: "packed meld " + strconv.Itoa(packed) + " out of range"}
	}
	caller, _ := tile.NewSeat(packed % tile.SeatCount)
	index := packed / tile.SeatCount

	switch {
	case index < ponOffset:
		return unpackChi(caller, index), nil
	case index < addedKanOffset:
		return unpackPon(caller, index-ponOffset), nil
	case index < openKanOffset:
		return unpackAddedKan(caller, index-addedKanOffset), nil
	case index < closedKanOffset:
		return unpackOpenKan(caller, index-openKanOffset), nil
	default:
		return unpackClosedKan(caller, index-closedKanOffset), nil
	}
}

func unpackChi(caller tile.Seat, index int) Meld {
	calledAt := index % meldTiles
	copies := index / meldTiles % 64
	base := index / meldTiles / 64
	low := base/chiStartsPerSuit*ranksPerSuit + base%chiStartsPerSuit

	tiles := []tile.TileID{
		tileOf(low, copies/16),
		tileOf(low+1, copies/4%4),
		tileOf(low+2, copies%4),
	}
	return Meld{
		Caller: caller,
		Kind:   play.MeldChi,
		Tiles:  tiles,
		Called: play.Some(tiles[calledAt]),
		From:   play.Some(caller.Kamicha()),
	}
}

func unpackPon(caller tile.Seat, index int) Meld {
	from := index % fromOffsets
	calledAt := index / fromOffsets % meldTiles
	missing := index / fromOffsets / meldTiles % tile.CopiesPerKind
	kind := index / fromOffsets / meldTiles / tile.CopiesPerKind

	tiles := make([]tile.TileID, 0, meldTiles)
	for c := range tile.CopiesPerKind {
		if c != missing {
			tiles = append(tiles, tileOf(kind, c))
		}
	}
	return Meld{
		Caller: caller,
		Kind:   play.MeldPon,
		Tiles:  tiles,
		Called: play.Some(tiles[calledAt]),
		From:   play.Some(seatAfter(caller, from)),
	}
}

func unpackAddedKan(caller tile.Seat, index int) Meld {
	pon := unpackPon(caller, index)
	kind := int(pon.Tiles[0].Kind())
	missing := copySum - copyOf(pon.Tiles[0]) - copyOf(pon.Tiles[1]) - copyOf(pon.Tiles[2])
	added := tileOf(kind, missing)

	pon.Kind = play.MeldAddedKan
	pon.Tiles = slices.SortedFunc(slices.Values(append(pon.Tiles, added)), tile.TileID.Compare)
	pon.Added = play.Some(added)
	return pon
}

func unpackOpenKan(caller tile.Seat, index int) Meld {
	from := index % fromOffsets
	called := index / fromOffsets % tile.CopiesPerKind
	kind := index / fromOffsets / tile.CopiesPerKind
	return Meld{
		Caller: caller,
		Kind:   play.MeldOpenKan,
		Tiles:  kindTiles(kind),
		Called: play.Some(tileOf(kind, called)),
		From:   play.Some(seatAfter(caller, from)),
	}
}

func unpackClosedKan(caller tile.Seat, kind int) Meld {
	return Meld{Caller: caller, Kind: play.MeldClosedKan, Tiles: kindTiles(kind)}
}

func kindTiles(kind int) []tile.TileID {
	tiles := make([]tile.TileID, 0, kanTiles)
	for c := range tile.CopiesPerKind {
		tiles = append(tiles, tileOf(kind, c))
	}
	return tiles
}

func tileOf(kind, copyIndex int) tile.TileID {
	id, _ := tile.NewTileID(kind*tile.CopiesPerKind + copyIndex)
	return id
}

func seatAfter(caller tile.Seat, offset int) tile.Seat {
	seat, _ := tile.NewSeat((caller.Index() + offset + 1) % tile.SeatCount)
	return seat
}
