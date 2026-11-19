package round

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const (
	maxHandTiles = wall.StartingHandSize + 1
	maxSeatMelds = 4
)

type handTiles struct {
	tiles [maxHandTiles]tile.TileID
	count int
}

func newHand(dealt [wall.StartingHandSize]tile.TileID) handTiles {
	var h handTiles
	h.count = copy(h.tiles[:], dealt[:])
	return h
}

func (h *handTiles) view() []tile.TileID {
	return h.tiles[:h.count:h.count]
}

func (h *handTiles) ids() []tile.TileID {
	return slices.Clone(h.view())
}

func (h *handTiles) push(id tile.TileID) {
	h.tiles[h.count] = id
	h.count++
}

func (h *handTiles) removeAt(position int) {
	copy(h.tiles[position:h.count], h.tiles[position+1:h.count])
	h.count--
	h.tiles[h.count] = tile.TileID{}
}

func (h *handTiles) keep(kept func(tile.TileID) bool) {
	count := 0
	for _, id := range h.view() {
		if kept(id) {
			h.tiles[count] = id
			count++
		}
	}
	clear(h.tiles[count:h.count])
	h.count = count
}

type seatMelds struct {
	views [maxSeatMelds]play.MeldView
	count int
}

func (m *seatMelds) view() []play.MeldView {
	return m.views[:m.count:m.count]
}

func (m *seatMelds) push(view play.MeldView) {
	m.views[m.count] = view
	m.count++
}

func (m *seatMelds) addToPon(id tile.TileID) play.MeldView {
	var added play.MeldView
	for i, view := range m.view() {
		if view.Kind == play.MeldPon && len(view.Tiles) > 0 && view.Tiles[0].Kind() == id.Kind() {
			tiles := append(slices.Clone(view.Tiles), id)
			slices.SortFunc(tiles, tile.TileID.Compare)
			added = play.MeldView{
				Kind: play.MeldAddedKan, Tiles: tiles, Called: view.Called, From: view.From, Added: play.Some(id),
			}
			m.views[i] = added
		}
	}
	return added
}

func appendTo[T any](s []T, items ...T) []T {
	return append(slices.Clip(s), items...)
}
