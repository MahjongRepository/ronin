package record_test

import (
	"slices"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/record"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

const spareCapacity = 4

func toAll(event play.Event) play.Emitted {
	return play.Emitted{To: play.ToAll(), Event: event}
}

func toSeat(s tile.Seat, event play.Event) play.Emitted {
	return play.Emitted{To: play.ToSeat(s), Event: event}
}

func ponOfHaku(t *testing.T) play.MeldView {
	t.Helper()
	return play.MeldView{
		Kind: play.MeldPon, Tiles: copies(t, 0, "555z"), Called: play.Some(tileOf(t, "5z")), From: play.Some(seat(t, 3)),
	}
}

func recordWithSpareCapacity(t *testing.T) play.SeatRecord {
	t.Helper()
	r := play.SeatRecord{
		Seat:           seat(t, 0),
		Hand:           slices.Grow(copies(t, 0, "1234567m123p5z"), spareCapacity),
		DoraIndicators: slices.Grow(copies(t, 0, "1s"), spareCapacity),
		History:        slices.Grow([]play.FinishedRound{{Result: play.Abortive{Kind: play.FourWinds{}}}}, spareCapacity),
		LiveTiles:      60,
	}

	for _, s := range tile.Seats() {
		r.Players[s.Index()].Seat = s
		r.Players[s.Index()].ClosedTiles = 13
	}

	r.Players[0].ClosedTiles = 11
	r.Players[0].River = slices.Grow([]play.RiverTile{{Tile: tileOf(t, "9s")}}, spareCapacity)
	r.Players[0].Melds = slices.Grow([]play.MeldView{ponOfHaku(t)}, spareCapacity)
	return r
}

func TestApply_WhenTwoEventsBranchFromOneRecord_ShouldLeaveTheRecordAndEachBranchApart(t *testing.T) {
	addedKan := ponOfHaku(t)
	addedKan.Kind = play.MeldAddedKan
	addedKan.Tiles = copies(t, 0, "5555z")
	closedKan := play.MeldView{Kind: play.MeldClosedKan, Tiles: copies(t, 0, "1111m")}
	chi := play.MeldView{Kind: play.MeldChi, Tiles: copies(t, 0, "123p"), Called: play.Some(tileOf(t, "2p")), From: play.Some(seat(t, 3))}
	pon := play.MeldView{Kind: play.MeldPon, Tiles: copies(t, 0, "111p"), Called: play.Some(tileOf(t, "1p")), From: play.Some(seat(t, 3))}
	ended := func(result play.RoundResult) play.Emitted { return toAll(play.RoundEnded{Result: result}) }
	own := seat(t, 0)

	tests := []struct {
		name  string
		first play.Emitted
		other play.Emitted
	}{
		{
			name:  "draws",
			first: toSeat(own, play.Drew{Seat: own, Tile: tileOf(t, "8m")}),
			other: toSeat(own, play.Drew{Seat: own, Tile: tileOf(t, "9m")}),
		},
		{
			name:  "discards",
			first: toAll(play.Discarded{Seat: own, Tile: tileOf(t, "1m")}),
			other: toAll(play.Discarded{Seat: own, Tile: tileOf(t, "2m")}),
		},
		{name: "calls", first: toAll(play.Called{Seat: own, Meld: chi}), other: toAll(play.Called{Seat: own, Meld: pon})},
		{
			name:  "kans",
			first: toAll(play.Called{Seat: own, Meld: addedKan}),
			other: toAll(play.Called{Seat: own, Meld: closedKan}),
		},
		{
			name:  "dora reveals",
			first: toAll(play.DoraRevealed{Indicator: tileOf(t, "2s")}),
			other: toAll(play.DoraRevealed{Indicator: tileOf(t, "3s")}),
		},
		{name: "round ends", first: ended(play.Abortive{Kind: play.FourKans{}}), other: ended(play.ExhaustiveDraw{})},
	}
	for _, c := range tests {
		t.Run(c.name, func(t *testing.T) {
			base := recordWithSpareCapacity(t)
			kept := record.Clone(base)

			first := record.Apply(base, c.first)
			other := record.Apply(base, c.other)

			assertEqual(t, c.name+": record", base, kept)
			assertEqual(t, c.name+": first branch", first, record.Apply(record.Clone(kept), c.first))
			assertEqual(t, c.name+": other branch", other, record.Apply(record.Clone(kept), c.other))
		})
	}
}

func TestApply_WhenACountIsAlreadyZero_ShouldKeepItAtZero(t *testing.T) {
	r := recordWithSpareCapacity(t)
	r.LiveTiles = 0
	r.Players[1].ClosedTiles = 0
	r.Players[2].ClosedTiles = 1
	chi := play.MeldView{Kind: play.MeldChi, Tiles: copies(t, 0, "789s"), Called: play.Some(tileOf(t, "7s")), From: play.Some(seat(t, 1))}

	r = record.Apply(r, toSeat(seat(t, 0), play.DrewNotice{Seat: seat(t, 3)}))
	r = record.Apply(r, toAll(play.Discarded{Seat: seat(t, 1), Tile: tileOf(t, "1z")}))
	r = record.Apply(r, toAll(play.Called{Seat: seat(t, 2), Meld: chi}))

	assertEqual(t, "live tiles", r.LiveTiles, 0)
	assertEqual(t, "discarder's closed tiles", r.Players[1].ClosedTiles, 0)
	assertEqual(t, "caller's closed tiles", r.Players[2].ClosedTiles, 0)
}
