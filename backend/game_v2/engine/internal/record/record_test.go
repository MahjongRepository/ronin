package record_test

import (
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/record"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/testkit"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

func dealerRiichi(r play.SeatRecord) play.Option[play.Riichi] {
	return r.Players[0].Riichi
}

func TestRecord_WhenTheDealerDeclaresADoubleRiichi_ShouldKeepItsIppatsuUntilTheDealerDiscards(t *testing.T) {
	g := begun(t, doubleRiichiWall(t, tileOf(t, "2z")))
	r := g.SeatView(seat(t, 1)).Record

	g, r = followed(t, g, r, act(seat(t, 0), play.RiichiAction(tileOf(t, "1z"))))
	standing := play.Riichi{Double: true, Ippatsu: true}
	assertEqual(t, "riichi", dealerRiichi(r), play.Some(standing))
	assertEqual(t, "sticks", r.RiichiSticks, 1)

	for _, d := range []struct {
		at   int
		wind string
	}{{1, "2z"}, {2, "3z"}, {3, "4z"}} {
		g, r = followed(t, g, r, act(seat(t, d.at), play.DiscardAction(tileOf(t, d.wind))))
	}
	assertEqual(t, "riichi after the go-around", dealerRiichi(r), play.Some(standing))

	_, r = followed(t, g, r, act(seat(t, 0), play.DiscardAction(tileOf(t, "6z"))))
	assertEqual(t, "riichi after the dealer's discard", dealerRiichi(r), play.Some(play.Riichi{Double: true}))
}

func TestRecord_WhenAPonFollowsARiichi_ShouldEndEveryIppatsu(t *testing.T) {
	g := begun(t, doubleRiichiWall(t, tileOf(t, "5z")))
	r := g.SeatView(seat(t, 3)).Record
	g, r = followed(t, g, r, act(seat(t, 0), play.RiichiAction(tileOf(t, "1z"))))
	g, r = followed(t, g, r, act(seat(t, 1), play.DiscardAction(tileOf(t, "5z"))))
	assertEqual(t, "ippatsu before the pon", dealerRiichi(r).Value.Ippatsu, true)

	_, r = followed(t, g, r, act(seat(t, 2), firstPon(t, g, seat(t, 2))))

	assertEqual(t, "ippatsu after the pon", dealerRiichi(r).Value.Ippatsu, false)
	assertEqual(t, "melds", len(r.Players[2].Melds), 1)
	assertEqual(t, "closed tiles", r.Players[2].ClosedTiles, 11)
	assertEqual(t, "latest discard", r.LatestDiscard, play.Option[tile.Seat]{})
	assertEqual(t, "current", r.Current, seat(t, 2))
}

func TestRecord_WhenTakenFromAViewBeforeADoubleRon_ShouldFollowItToTheRoundEnd(t *testing.T) {
	g := threePinWithTwoRonCallers(t)
	r := g.SeatView(seat(t, 1)).Record

	g, r = followed(t, g, r, act(seat(t, 0), play.RonAction()))
	_, r = followed(t, g, r, act(seat(t, 3), play.RonAction()))

	ron, ok := r.Result.(play.Ron)
	if !ok || len(ron.Wins) != 2 {
		t.Errorf("result = %+v, want a double ron", r.Result)
	}
	assertEqual(t, "finished rounds", len(r.History), 1)
	assertEqual(t, "latest discard", r.LatestDiscard, play.Option[tile.Seat]{})
}

func TestFromStart_WhenTheDealerAbortsOnKyuushu_ShouldFollowItsAbort(t *testing.T) {
	w := testkit.StartWall{Hands: [tile.SeatCount][]tile.TileID{copies(t, 0, "19m19p19s1234567z")}}
	source, err := testkit.FixedSetup(w, play.Option[play.StartPosition]{})
	if err != nil {
		t.Fatalf("FixedSetup error = %v", err)
	}
	g, initial, err := game.New(source, play.Option[play.StartPosition]{})
	if err != nil {
		t.Fatalf("New error = %v", err)
	}
	r, ok := record.FromStart(seat(t, 2), initial)
	if !ok {
		t.Fatal("FromStart found no start")
	}
	assertEqual(t, "record from the start", r, g.SeatView(seat(t, 2)).Record)
	g, drew, _ := g.Begin()
	for _, e := range drew {
		r = record.Apply(r, e)
	}

	g, r = followed(t, g, r, act(seat(t, 0), play.KyuushuAction()))

	assertEqual(t, "result", r.Result, play.RoundResult(play.Abortive{Kind: play.KyuushuKyuuhai{
		Seat: seat(t, 0), Hand: g.Hand(seat(t, 0)),
	}}))
	assertEqual(t, "current", r.Current, seat(t, 0))
	if _, found := record.FromStart(seat(t, 2), initial[:1]); found {
		t.Error("FromStart without the seat's RoundStarted found a start")
	}
	if _, found := record.FromStart(seat(t, 2), initial[1:]); found {
		t.Error("FromStart without the GameStarted found a start")
	}
}
