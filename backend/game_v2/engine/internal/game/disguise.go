package game

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func (g Game) Disguised(seat tile.Seat, action play.Action, pick func(n int) int) play.Action {
	hand := g.round.Hand(seat)
	if kind, isKan := action.Kan(); isKan {
		named, _ := action.Tile()
		if kind != play.KanClosed {
			return action
		}
		return play.KanAction(kind, pickedLookalike(hand, named, nil, pick))
	}

	held, takesTwo := action.Held()
	if !takesTwo || held[0] == held[1] || !slices.Contains(hand, held[0]) || !slices.Contains(hand, held[1]) {
		return action
	}
	first := pickedLookalike(hand, held[0], nil, pick)
	second := pickedLookalike(hand, held[1], []tile.TileID{first}, pick)
	if action.Kind() == play.ActionPon {
		return play.PonAction([2]tile.TileID{first, second})
	}
	return play.ChiAction([2]tile.TileID{first, second})
}

func pickedLookalike(hand []tile.TileID, named tile.TileID, taken []tile.TileID, pick func(n int) int) tile.TileID {
	var lookalikes []tile.TileID
	for held := range tile.HeldCopies(hand, named.Kind()) {
		if held.Tile(rules.AkaDora) == named.Tile(rules.AkaDora) && !slices.Contains(taken, held) {
			lookalikes = append(lookalikes, held)
		}
	}
	if len(lookalikes) == 0 {
		return named
	}
	return lookalikes[pick(len(lookalikes))]
}
