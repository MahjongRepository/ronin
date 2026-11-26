package record

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
)

func Clone(r play.SeatRecord) play.SeatRecord {
	r.Hand = cloneSlice(r.Hand)
	for i := range r.Players {
		r.Players[i].River = cloneSlice(r.Players[i].River)
		r.Players[i].Melds = cloneMelds(r.Players[i].Melds)
	}
	r.DoraIndicators = cloneSlice(r.DoraIndicators)
	r.Result = CloneResult(r.Result)
	r.History = cloneSlice(r.History)
	for i := range r.History {
		r.History[i].Result = CloneResult(r.History[i].Result)
		r.History[i].RiichiSeats = cloneSlice(r.History[i].RiichiSeats)
	}
	return r
}

func cloneSlice[S ~[]E, E any](s S) S {
	if len(s) == 0 {
		return nil
	}
	return slices.Clone(s)
}

func cloneMeld(m play.MeldView) play.MeldView {
	m.Tiles = cloneSlice(m.Tiles)
	return m
}

func cloneMelds(melds []play.MeldView) []play.MeldView {
	if len(melds) == 0 {
		return nil
	}
	cloned := make([]play.MeldView, len(melds))
	for i, m := range melds {
		cloned[i] = cloneMeld(m)
	}
	return cloned
}

func cloneShown(hands []play.ShownHand) []play.ShownHand {
	hands = cloneSlice(hands)
	for i := range hands {
		hands[i].Hand = cloneSlice(hands[i].Hand)
		hands[i].Melds = cloneMelds(hands[i].Melds)
	}
	return hands
}

func cloneWin(win play.WinResult) play.WinResult {
	win.Hand = cloneSlice(win.Hand)
	win.Melds = cloneMelds(win.Melds)
	win.Yaku = cloneSlice(win.Yaku)
	win.UraIndicators = cloneSlice(win.UraIndicators)
	return win
}

// CloneResult returns a copy of result that shares no slice with it, down to every hand, meld,
// river and yaku it shows. An empty slice of result is nil in the copy; a nil result stays nil.
func CloneResult(result play.RoundResult) play.RoundResult {
	switch r := result.(type) {
	case play.ExhaustiveDraw:
		r.Tenpai = cloneShown(r.Tenpai)
		r.Nagashi = cloneSlice(r.Nagashi)
		for i := range r.Nagashi {
			r.Nagashi[i].River = cloneSlice(r.Nagashi[i].River)
		}
		return r
	case play.Tsumo:
		r.Win = cloneWin(r.Win)
		return r
	case play.Ron:
		r.Wins = cloneSlice(r.Wins)
		for i := range r.Wins {
			r.Wins[i] = cloneWin(r.Wins[i])
		}
		r.HeadBumped = cloneSlice(r.HeadBumped)
		return r
	case play.Abortive:
		r.Kind = cloneAbort(r.Kind)
		return r
	}
	return nil
}

func cloneAbort(kind play.AbortKind) play.AbortKind {
	switch k := kind.(type) {
	case play.KyuushuKyuuhai:
		k.Hand = cloneSlice(k.Hand)
		return k
	case play.FourRiichi:
		k.Hands = cloneShown(k.Hands)
		return k
	case play.TripleRon:
		k.Hands = cloneShown(k.Hands)
		return k
	case play.FourWinds, play.FourKans:
	}
	return kind
}
