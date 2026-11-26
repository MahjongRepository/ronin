package main

import (
	"errors"
	"fmt"
	"slices"
	"strings"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/messaging"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/session"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	fullGameID           = "fixture-fg"
	fullGameSeedHex      = "1"
	eagerGameSeedHex     = "09"
	eagerDoubleRonSeed   = "033c"
	seedHexLength        = 2 * len(engine.Seed{})
	doubleRonOccurrence  = 3
	doubleRonRoundNumber = 3
)

func replayFixtures() []replayFixture {
	return []replayFixture{
		{"riichi.msgpack", riichiFixture},
		{"kans.msgpack", kansFixture},
		{"full_game.msgpack", fullGameFixture},
		{"truncated_mid_round.msgpack", truncatedMidRound},
		{"truncated_after_round.msgpack", truncatedAfterRound},
		{"ron_riichi_discard.msgpack", ronRiichiDiscard},
		{"double_ron.msgpack", doubleRonFixture},
		{"chankan_added.msgpack", chankanAdded},
		{"chankan_ai_replacement.msgpack", chankanAIReplacement},
		{"chankan_closed_kokushi.msgpack", chankanClosedKokushi},
		{"triple_ron.msgpack", tripleRon},
		{"pao.msgpack", paoFixture},
		{"kazoe.msgpack", kazoeFixture},
		{"exhaustive_tenpai.msgpack", exhaustiveTenpai},
		{"leftover_riichi.msgpack", leftoverRiichi},
		{"nagashi.msgpack", nagashiFixture},
		{"kyuushu.msgpack", kyuushuFixture},
		{"four_winds_riichi.msgpack", fourWindsRiichi},
		{"four_riichi.msgpack", fourRiichi},
		{"four_kans.msgpack", fourKans},
		{"ai_replacements.msgpack", aiReplacements},
		{"riichi_ai_replacement.msgpack", riichiAIReplacement},
		{"ai_dealer_absent.msgpack", aiDealerAbsent},
		{"eager_game.msgpack", eagerGame},
		{"double_ron_on_honba.msgpack", doubleRonOnHonba},
	}
}

type stagedReplay struct {
	id      string
	wall    stagedWall
	seating seating
	start   play.Option[play.StartPosition]
}

func staged(id string, wall stagedWall) stagedReplay {
	return stagedReplay{id: id, wall: wall, seating: atTheTable()}
}

func playStaged(s *staging, r stagedReplay, want outcome, script func(g *stagedGame)) (recording, error) {
	if s.err != nil {
		return recording{}, fmt.Errorf("%s: %w", r.id, s.err)
	}

	dealers := fillerDealers{}
	for range maxDealerPasses {
		g := openStagedGame(r.id, r.wall, r.seating, r.start, dealers)
		script(g)
		played, err := g.replay(want)
		if s.err != nil {
			return recording{}, fmt.Errorf("%s: %w", r.id, s.err)
		}

		if fillersMatch([]stagedWall{r.wall}, r.start, dealers, g.dealt) {
			return played, err
		}

		dealers = g.dealt
	}

	return recording{}, fmt.Errorf("%s: the seed's later rounds found no dealers in %d passes", r.id, maxDealerPasses)
}

func field(k wire.Key, v wire.Value) wire.Field {
	return wire.Field{Key: k, Value: v}
}

func n(i int) wire.Int {
	return wire.Int(i)
}

func tileValues(ids ...tile.TileID) wire.Array {
	values := make(wire.Array, 0, len(ids))
	for _, id := range ids {
		values = append(values, n(id.Index()))
	}

	return values
}

func ints(values ...int) wire.Array {
	array := make(wire.Array, 0, len(values))
	for _, v := range values {
		array = append(array, n(v))
	}

	return array
}

func result(code wire.ResultType, fields ...wire.Field) wire.Map {
	return append(wire.Map{field(wire.KeyResultType, n(int(code)))}, fields...)
}

func ronResult(loser int, winners ...wire.Map) wire.Map {
	array := make(wire.Array, 0, len(winners))
	for _, w := range winners {
		array = append(array, w)
	}

	return result(wire.ResultRon, field(wire.KeyLoserSeat, n(loser)), field(wire.KeyWinners, array))
}

func win(winner int, fields ...wire.Field) wire.Map {
	return append(wire.Map{field(wire.KeyWinnerSeat, n(winner))}, fields...)
}

func aborted(reason wire.AbortReason, fields ...wire.Field) wire.Map {
	return result(wire.ResultAbortiveDraw, append([]wire.Field{field(wire.KeyAbortiveReason, wire.Str(reason))}, fields...)...)
}

func endsAt(roundEnd wire.Map) outcome {
	return outcome{roundEnd: roundEnd}
}

func riichiFixture() (recording, error) {
	var s staging
	ponnedRiichiTile := s.id(2, "7z")
	secondRiichiTile := s.id(0, "4z")
	ura := s.id(1, "8p")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(s.ids(3, "18m268p168s1234z"), s.ids(0, "5m")),
			slices.Concat(s.ids(0, "123m456789p349s"), s.ids(1, "9s")),
			slices.Concat(s.ids(2, "147m1p147s2356z"), s.ids(0, "7z"), s.ids(1, "7z")),
			slices.Concat(s.ids(1, "234m234p"), s.ids(0, "678m678s"), []tile.TileID{secondRiichiTile}),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(3, "3m")), s.draw(1, s.id(1, "9m")), s.draw(2, s.id(0, "3z")), s.draw(3, s.id(1, "1s")),
			s.draw(0, s.id(2, "2m")), s.draw(1, ponnedRiichiTile), s.draw(3, s.id(1, "9p")), s.draw(0, s.id(0, "6z")),
			s.draw(1, s.id(0, "1p")), s.draw(2, s.id(0, "4m")), s.draw(3, s.id(1, "6z")), s.draw(0, s.id(0, "2z")),
			s.draw(1, s.id(1, "5s")),
		},
		ura: []tile.TileID{ura},
	}

	want := endsAt(result(wire.ResultTsumo, field(wire.KeyWinnerSeat, n(1)), field(wire.KeyUraDora, tileValues(ura))))
	return playStaged(&s, staged("riichi", wall), want, func(g *stagedGame) {
		g.discard(0, s.id(3, "1z"))
		g.tsumogiri(1)
		g.tsumogiri(2)
		g.tsumogiri(3)

		g.discard(0, s.id(3, "8m"))
		g.riichi(1)
		g.pon(2)
		g.discard(2, s.id(2, "2z"))

		g.riichiOn(3, secondRiichiTile)
		g.tsumogiriUntil(1)
		g.tsumogiri(1)
		g.tsumogiriUntil(1)
		g.tsumo(1)
	})
}

func kansFixture() (recording, error) {
	var s staging
	openKanTile := s.id(3, "6z")
	ponnedTile := s.id(2, "5z")
	addedKanTile := s.id(3, "5z")
	closedKanTile := s.id(3, "1s")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			slices.Concat([]tile.TileID{openKanTile}, s.ids(1, "147m147p258s123z")),
			slices.Concat(s.ids(0, "55z"), s.ids(1, "258m258p369s47z")),
			slices.Concat(s.ids(0, "66z"), s.ids(2, "36m369p479s126z")),
			slices.Concat(s.ids(0, "111s"), s.ids(0, "234m567p678s"), []tile.TileID{ponnedTile}),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(2, "4z")), s.draw(3, s.id(0, "9m")), s.draw(2, s.id(3, "2z")), s.draw(3, s.id(3, "3z")),
			s.draw(0, s.id(3, "4z")), s.draw(1, addedKanTile), s.draw(2, s.id(2, "7z")), s.draw(3, closedKanTile),
		},
		rinshan: []tile.TileID{s.id(3, "7z"), s.id(3, "3m"), s.id(1, "9m")},
	}

	want := endsAt(result(wire.ResultTsumo, field(wire.KeyWinnerSeat, n(3))))
	return playStaged(&s, staged("kans", wall), want, func(g *stagedGame) {
		g.discard(0, openKanTile)
		g.kan(2, openKanTile, play.KanOpen)
		g.tsumogiri(2)

		g.discard(3, ponnedTile)
		g.pon(1)
		g.discard(1, s.id(1, "4z"))
		g.tsumogiriUntil(1)

		g.kan(1, addedKanTile, play.KanAdded)
		g.tsumogiri(1)
		g.tsumogiriUntil(3)

		g.kan(3, closedKanTile, play.KanClosed)
		g.tsumo(3)
	})
}

func fullGameFixture() (recording, error) {
	seedHex := strings.Repeat(fullGameSeedHex, seedHexLength)
	seed, err := engine.ParseSeed(seedHex)
	if err != nil {
		return recording{}, fmt.Errorf("full_game: parse seed %s: %w", seedHex, err)
	}

	roster := messaging.Roster{GameID: fullGameID, Names: [tile.SeatCount]string{"Wanjirou", "Ojisan", "Ichihime", "Akagi"}}
	want := endsInGame(result(wire.ResultExhaustiveDraw))
	return playPolicyGame("full_game", seed, roster, defaultPolicy, want)
}

func ronRiichiDiscard() (recording, error) {
	var s staging
	riichiDiscard := s.id(1, "4p")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(2, "1m1569p1589s1234z"),
			s.ids(0, "123456789m23p11s"),
			slices.Concat(s.ids(0, "789p234567s"), s.ids(1, "5567m")),
			s.ids(3, "1m1569p1589s1234z"),
		},
		draws: []stagedDraw{s.draw(0, s.id(0, "5z")), s.draw(1, s.id(0, "6z")), s.draw(2, riichiDiscard)},
	}

	want := endsAt(ronResult(2, win(1, field(wire.KeyRiichiCollected, n(1)))))
	return playStaged(&s, staged("ron-riichi-discard", wall), want, func(g *stagedGame) {
		g.tsumogiri(0)
		g.riichi(1)
		g.riichi(2)
		g.ron(1)
	})
}

func doubleRonFixture() (recording, error) {
	var s staging
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(2, "178m129p159s1234z"),
			s.ids(0, "123456789m23p11s"),
			s.ids(1, "23499m56p456678s"),
			s.ids(3, "178m129p159s1234z"),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(0, "5z")), s.draw(1, s.id(0, "6z")), s.draw(2, s.id(0, "7z")), s.draw(3, s.id(1, "5z")),
			s.draw(0, s.id(2, "4p")),
		},
	}

	want := endsAt(ronResult(0,
		win(1, field(wire.KeyRiichiCollected, n(2))), win(2, field(wire.KeyRiichiCollected, n(0)))))
	return playStaged(&s, staged("double-ron", wall), want, func(g *stagedGame) {
		g.tsumogiri(0)
		g.riichi(1)
		g.riichi(2)
		g.tsumogiri(3)
		g.tsumogiri(0)
		g.ron(1, 2)
	})
}

func tripleRon() (recording, error) {
	var s staging
	discard := s.id(2, "3p")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(s.ids(0, "12347z"), s.ids(1, "1234z"), s.ids(2, "1234z")),
			slices.Concat(s.ids(0, "123456789m12p5z"), s.ids(1, "5z")),
			slices.Concat(s.ids(0, "45p123456789s6z"), s.ids(1, "6z")),
			slices.Concat(s.ids(1, "234567m345p678s"), s.ids(0, "6p")),
		},
		draws: []stagedDraw{s.draw(0, discard)},
	}

	want := endsAt(aborted(wire.AbortTripleRon, field(wire.KeyRonCallers, ints(1, 2, 3))))
	return playStaged(&s, staged("triple-ron", wall), want, func(g *stagedGame) {
		g.discard(0, discard)
		g.ron(1, 2, 3)
	})
}

func chankanWall(s *staging, seat3 []tile.TileID, seat3Draw tile.TileID) stagedWall {
	return stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(s.ids(2, "258m17p369s1234z"), s.ids(2, "6p")),
			slices.Concat(s.ids(0, "66p"), s.ids(1, "147m19p258s123z")),
			s.ids(0, "123456789m45p19s"),
			seat3,
		},
		draws: []stagedDraw{
			s.draw(0, s.id(0, "7z")), s.draw(2, s.id(1, "1s")), s.draw(3, seat3Draw), s.draw(0, s.id(2, "7z")),
			s.draw(1, s.id(3, "6p")),
		},
	}
}

func robbedBy(winner, declarer int, robbed tile.TileID) wire.Map {
	return append(ronResult(declarer, win(winner)), field(wire.KeyWinningTile, n(robbed.Index())))
}

func chankanAdded() (recording, error) {
	var s staging
	ponnedTile, addedKanTile := s.id(2, "6p"), s.id(3, "6p")
	wall := chankanWall(&s, s.ids(3, "258m17p369s12345z"), s.id(1, "7z"))

	want := endsAt(robbedBy(2, 1, addedKanTile))
	return playStaged(&s, staged("chankan-added", wall), want, func(g *stagedGame) {
		g.discard(0, ponnedTile)
		g.pon(1)
		g.discard(1, s.id(1, "1z"))
		g.discard(2, s.id(0, "9s"))
		g.tsumogiri(3)
		g.tsumogiri(0)

		g.kan(1, addedKanTile, play.KanAdded)
		g.ron(2)
	})
}

func chankanAIReplacement() (recording, error) {
	var s staging
	ponnedTile, addedKanTile := s.id(2, "6p"), s.id(3, "6p")
	wall := chankanWall(&s, slices.Concat(s.ids(3, "234567m4p456s1z"), s.ids(0, "55z")), s.id(3, "5p"))

	want := endsAt(robbedBy(2, 1, addedKanTile))
	return playStaged(&s, staged("chankan-ai-replacement", wall), want, func(g *stagedGame) {
		g.discard(0, ponnedTile)
		g.pon(1)
		g.discard(1, s.id(1, "1z"))
		g.discard(2, s.id(0, "9s"))
		g.discard(3, s.id(3, "1z"))
		g.tsumogiri(0)

		g.kan(1, addedKanTile, play.KanAdded)
		g.leave(3)
		g.ron(2)
	})
}

func chankanClosedKokushi() (recording, error) {
	var s staging
	closedKanTile := s.id(3, "9m")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(2, "357m357p35789s12z"),
			slices.Concat(s.ids(0, "999m"), s.ids(1, "246m2468p246s")),
			s.ids(0, "11m19p19s1234567z"),
			s.ids(3, "357m357p35789s12z"),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(1, "3z")), s.draw(1, s.id(1, "4z")), s.draw(2, s.id(1, "5z")), s.draw(3, s.id(1, "6z")),
			s.draw(0, s.id(1, "7z")), s.draw(1, closedKanTile),
		},
	}

	want := endsInGame(robbedBy(2, 1, closedKanTile))
	return playStaged(&s, staged("chankan-closed-kokushi", wall), want, func(g *stagedGame) {
		g.tsumogiriUntil(1)
		g.tsumogiri(1)
		g.tsumogiriUntil(1)
		g.kan(1, closedKanTile, play.KanClosed)
		g.ron(2)
	})
}

func paoFixture() (recording, error) {
	var s staging
	firstDragon, secondDragon, liableDragon := s.id(2, "5z"), s.id(2, "6z"), s.id(2, "7z")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(s.ids(2, "258m258p258s12z"), []tile.TileID{firstDragon, liableDragon}),
			s.ids(0, "1234m9p19s556677z"),
			slices.Concat(s.ids(1, "258m258p258s123z"), []tile.TileID{secondDragon}),
			slices.Concat(s.ids(3, "258m258p258s123z"), s.ids(3, "9s")),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(1, "1p")), s.draw(2, s.id(2, "1p")), s.draw(2, s.id(3, "1p")), s.draw(3, s.id(1, "9m")),
			s.draw(0, s.id(2, "9m")), s.draw(2, s.id(3, "9m")), s.draw(3, s.id(0, "3p")), s.draw(0, s.id(1, "3p")),
			s.draw(1, s.id(1, "4m")),
		},
	}

	want := endsInGame(result(wire.ResultTsumo, field(wire.KeyWinnerSeat, n(1)), field(wire.KeyPaoSeat, n(0))))
	return playStaged(&s, staged("pao", wall), want, func(g *stagedGame) {
		g.discard(0, firstDragon)
		g.pon(1)
		g.discard(1, s.id(0, "9p"))

		g.discard(2, secondDragon)
		g.pon(1)
		g.discard(1, s.id(0, "1s"))

		g.tsumogiriUntil(0)
		g.discard(0, liableDragon)
		g.pon(1)
		g.discard(1, s.id(0, "9s"))

		g.tsumogiriUntil(1)
		g.tsumo(1)
	})
}

func kazoeFixture() (recording, error) {
	var s staging
	const junk = "2468m2468s12345z"
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(s.ids(0, "23344667788p"), s.ids(1, "5p"), s.ids(2, "5p")),
			s.ids(1, junk),
			s.ids(2, junk),
			s.ids(3, junk),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(0, "1m")), s.draw(1, s.id(0, "9m")), s.draw(2, s.id(1, "9m")), s.draw(3, s.id(2, "9m")),
			s.draw(0, s.id(1, "2p")),
		},
	}

	want := endsAt(result(wire.ResultTsumo, field(wire.KeyWinnerSeat, n(0))))
	return playStaged(&s, staged("kazoe", wall), want, func(g *stagedGame) {
		g.riichi(0)
		g.tsumogiri(1)
		g.tsumogiri(2)
		g.tsumogiri(3)
		g.tsumo(0)
	})
}

func riichiToExhaustiveDraw(s *staging, r stagedReplay, want outcome, after func(g *stagedGame)) (recording, error) {
	r.wall = stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(s.ids(0, "777z"), s.ids(0, "147m147p258s1z")),
			slices.Concat(s.ids(1, "123456789p111s"), s.ids(3, "7z")),
			slices.Concat(s.ids(2, "234567m345678s"), s.ids(3, "6z")),
			slices.Concat(s.ids(0, "666z"), s.ids(3, "258m258p369s2z")),
		},
	}
	return playStaged(s, r, want, func(g *stagedGame) {
		g.tsumogiri(0)
		g.riichi(1)
		g.tsumogiriToRoundEnd()
		after(g)
	})
}

func twoTenpaiDraw() wire.Map {
	return result(wire.ResultExhaustiveDraw,
		field(wire.KeyTenpaiSeats, ints(1, 2)), field(wire.KeyNotenSeats, ints(0, 3)))
}

func exhaustiveTenpai() (recording, error) {
	var s staging
	want := thenRecord(twoTenpaiDraw(), wire.EventRoundStarted, wire.Map{
		field(wire.KeyDealer, n(1)), field(wire.KeyHonba, n(1)), field(wire.KeyRiichiSticks, n(1)),
	})
	return riichiToExhaustiveDraw(&s, staged("exhaustive-tenpai", stagedWall{}), want, (*stagedGame).confirmRound)
}

func leftoverRiichi() (recording, error) {
	var s staging
	r := staged("leftover-riichi", stagedWall{})
	r.start = play.Some(play.StartPosition{Scores: [tile.SeatCount]int{25000, 25000, 49000, 1000}})
	want := thenRecord(twoTenpaiDraw(), wire.EventGameEnd, wire.Map{
		field(wire.KeyWinnerSeat, n(2)), field(wire.KeyLeftoverBonus, n(10)), field(wire.KeyLeftoverRiichi, n(1)),
	})
	return riichiToExhaustiveDraw(&s, r, want, func(*stagedGame) {})
}

func nagashiFixture() (recording, error) {
	var s staging
	const nagashiSeat = 1
	hands := [tile.SeatCount][]tile.TileID{
		slices.Concat(s.ids(0, "555z"), s.ids(0, "258m258p258s1z")),
		s.ids(1, "23468m2468p2468s"),
		s.ids(2, "2468m2468p2468s2z"),
		slices.Concat(s.ids(3, "234567m234567s"), s.ids(3, "5z")),
	}

	var dealt [tile.TileIDCount]bool
	for _, hand := range hands {
		for _, id := range hand {
			dealt[id.Index()] = true
		}
	}

	drawSeats := make([]int, 0, liveWallSize-firstDrawSlot)
	for i := range liveWallSize - firstDrawSlot {
		drawSeats = append(drawSeats, i%tile.SeatCount)
	}

	var undealt, qualifying, others []tile.TileID
	for _, id := range tile.AllTileIDs() {
		if !dealt[id.Index()] {
			undealt = append(undealt, id)
		}
	}

	for _, id := range undealt {
		if id.Kind().IsTerminalOrHonor() && len(qualifying) < countOf(drawSeats, nagashiSeat) {
			qualifying = append(qualifying, id)
			continue
		}

		others = append(others, id)
	}

	if len(others) < len(drawSeats)-len(qualifying) {
		return recording{}, errors.New("nagashi: the wall holds too few draws")
	}

	draws := make([]stagedDraw, 0, len(drawSeats))
	for _, seat := range drawSeats {
		pool := &others
		if seat == nagashiSeat {
			pool = &qualifying
		}

		draws = append(draws, s.draw(seat, (*pool)[0]))
		*pool = (*pool)[1:]
	}

	want := endsAt(result(wire.ResultExhaustiveDraw, field(wire.KeyQualifyingSeats, ints(nagashiSeat))))
	return playStaged(&s, staged("nagashi", stagedWall{hands: hands, draws: draws}), want, func(g *stagedGame) {
		g.tsumogiriToRoundEnd()
	})
}

func countOf(seats []int, seat int) int {
	count := 0
	for _, s := range seats {
		if s == seat {
			count++
		}
	}

	return count
}

func kyuushuFixture() (recording, error) {
	var s staging
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(s.ids(1, "258m258p258s567z"), s.ids(1, "4m")),
			s.ids(0, "12349m19p19s1234z"),
			slices.Concat(s.ids(2, "258m258p258s567z"), s.ids(2, "4m")),
			slices.Concat(s.ids(3, "258m258p258s567z"), s.ids(3, "4m")),
		},
		draws: []stagedDraw{s.draw(0, s.id(0, "6z")), s.draw(1, s.id(0, "5z"))},
	}

	want := endsAt(aborted(wire.AbortNineTerminals, field(wire.KeySeat, n(1))))
	return playStaged(&s, staged("kyuushu", wall), want, func(g *stagedGame) {
		g.tsumogiri(0)
		g.kyuushu(1)
	})
}

func fourWindsRiichi() (recording, error) {
	var s staging
	winds := s.ids(0, "1111z")
	wall := stagedWall{
		draws: []stagedDraw{
			s.draw(0, s.id(0, "2z")), s.draw(1, s.id(1, "2z")), s.draw(2, s.id(2, "2z")), s.draw(3, s.id(0, "4p")),
		},
	}
	if len(winds) == tile.SeatCount {
		for seat := range tile.SeatCount - 1 {
			wall.hands[seat] = slices.Concat(winds[seat:seat+1], s.ids(seat+1, "258m169p258s567z"))
		}

		wall.hands[tile.SeatCount-1] = slices.Concat(s.ids(0, "123456789m223p"), winds[tile.SeatCount-1:])
	}

	want := endsAt(aborted(wire.AbortFourWinds))
	return playStaged(&s, staged("four-winds-riichi", wall), want, func(g *stagedGame) {
		for seat := range tile.SeatCount - 1 {
			g.discard(seat, winds[seat])
		}

		g.riichiOn(tile.SeatCount-1, winds[tile.SeatCount-1])
	})
}

func fourRiichi() (recording, error) {
	var s staging
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(0, "123456789m23p55z"),
			s.ids(1, "123456789m23s66z"),
			s.ids(2, "123456789p67s77z"),
			slices.Concat(s.ids(3, "67p123456789s"), s.ids(2, "55z")),
		},
		draws: []stagedDraw{s.draw(0, s.id(0, "1z")), s.draw(1, s.id(0, "2z")), s.draw(2, s.id(0, "3z")), s.draw(3, s.id(0, "4z"))},
	}

	want := endsAt(aborted(wire.AbortFourRiichi))
	return playStaged(&s, staged("four-riichi", wall), want, func(g *stagedGame) {
		for seat := range tile.SeatCount {
			g.riichi(seat)
		}
	})
}

func fourKans() (recording, error) {
	var s staging
	openKanTile := s.id(3, "7p")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			slices.Concat(s.ids(0, "11112222m"), s.ids(0, "19p19s1z")),
			slices.Concat(s.ids(0, "3333777p"), s.ids(1, "2468s23z")),
			s.ids(2, "369m258p369s4567z"),
			s.ids(3, "369m258p369s4567z"),
		},
		draws:   []stagedDraw{s.draw(0, s.id(0, "2z")), s.draw(1, s.id(2, "3z")), s.draw(2, openKanTile)},
		rinshan: []tile.TileID{s.id(0, "8m"), s.id(1, "8m"), s.id(0, "6p"), s.id(0, "4p")},
	}

	want := endsAt(aborted(wire.AbortFourKans))
	return playStaged(&s, staged("four-kans", wall), want, func(g *stagedGame) {
		g.kan(0, s.id(0, "1m"), play.KanClosed)
		g.kan(0, s.id(0, "2m"), play.KanClosed)
		g.tsumogiri(0)

		g.kan(1, s.id(0, "3p"), play.KanClosed)
		g.tsumogiri(1)
		g.tsumogiri(2)

		g.kan(1, openKanTile, play.KanOpen)
		g.tsumogiri(1)
	})
}

func aiReplacements() (recording, error) {
	var s staging
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(2, "1m1569p1589s1234z"),
			s.ids(0, "123456789m23p11s"),
			slices.Concat(s.ids(0, "789p234567s"), s.ids(1, "5567m")),
			slices.Concat(s.ids(3, "1m1569p1589s12z"), s.ids(0, "55z")),
		},
		draws: []stagedDraw{s.draw(0, s.id(0, "6z")), s.draw(1, s.id(2, "5z")), s.draw(2, s.id(1, "4p"))},
	}
	r := staged("ai-replacements", wall)
	r.seating.absent = []int{3}

	want := thenRecord(ronResult(2, win(1)), wire.EventSeatControl, wire.Map{
		field(wire.KeySeat, n(3)), field(wire.KeyAIPlayer, n(0)),
	})
	return playStaged(&s, r, want, func(g *stagedGame) {
		g.tsumogiri(0)
		g.tsumogiri(1)

		g.leave(2)
		g.ron(1)
		g.restoreHuman(3)
		g.leave(0)

		g.confirmRound()
		g.restoreHuman(2)
		g.tsumogiri(1)
		g.tsumogiri(2)
		g.tsumogiri(3)
	})
}

func riichiAIReplacement() (recording, error) {
	var s staging
	riichiTile := s.id(0, "7z")
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(2, "1m1569p1589s1234z"),
			slices.Concat(s.ids(0, "123m456789p349s"), s.ids(1, "9s")),
			slices.Concat(s.ids(0, "456789m123p56z"), s.ids(1, "7z"), s.ids(2, "7z")),
			s.ids(3, "1m1569p1589s1234z"),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(3, "9m")), s.draw(1, riichiTile), s.draw(2, s.id(1, "5m")), s.draw(3, s.id(1, "9m")),
			s.draw(0, s.id(1, "8m")), s.draw(1, s.id(0, "5s")),
		},
	}

	want := endsAt(result(wire.ResultTsumo, field(wire.KeyWinnerSeat, n(1))))
	return playStaged(&s, staged("riichi-ai-replacement", wall), want, func(g *stagedGame) {
		g.tsumogiri(0)
		g.riichi(1)
		g.leave(2)
		g.tsumogiri(3)
		g.tsumogiri(0)
		g.tsumo(1)
	})
}

func aiDealerAbsent() (recording, error) {
	var s staging
	wall := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(1, "147m147p147s1234z"),
			s.ids(2, "258m258p258s1234z"),
			slices.Concat(s.ids(0, "123456789m234p"), s.ids(0, "5s")),
			s.ids(3, "369m369p369s1234z"),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(0, "5z")), s.draw(1, s.id(0, "6z")), s.draw(2, s.id(0, "7z")), s.draw(3, s.id(1, "5z")),
			s.draw(0, s.id(1, "6z")), s.draw(1, s.id(1, "7z")), s.draw(2, s.id(1, "5s")),
		},
	}
	r := staged("ai-dealer-absent", wall)
	r.seating = seating{players: []string{"Alice", "Bob", "Charlie"}, absent: []int{1, 3}}

	want := thenRecord(result(wire.ResultTsumo, field(wire.KeyWinnerSeat, n(2))),
		wire.EventRoundStarted, wire.Map{field(wire.KeyDealer, n(1))})
	return playStaged(&s, r, want, func(g *stagedGame) {
		g.tsumogiri(2)
		g.tsumo(2)
		g.confirmRound()
	})
}

func eagerSeeded(id, seedPair string, want outcome) (recording, error) {
	seedHex := strings.Repeat(seedPair, seedHexLength/len(seedPair))
	seed, err := engine.ParseSeed(seedHex)
	if err != nil {
		return recording{}, fmt.Errorf("%s: parse seed %s: %w", id, seedHex, err)
	}

	roster, _ := session.SeatPlayers(id, atTheTable().players, seed, session.SeatingShuffled)
	return playPolicyGame(id, seed, roster, eagerPolicy, want)
}

func eagerGame() (recording, error) {
	played, err := eagerSeeded("eager-game", eagerGameSeedHex,
		endsInGame(result(wire.ResultTsumo, field(wire.KeyWinnerSeat, n(3)))))
	if err != nil {
		return recording{}, err
	}

	return played, requireWinsOffSeatZero("eager-game", played)
}

func requireWinsOffSeatZero(name string, r recording) error {
	dealer := -1
	var results []int
	for _, record := range r.records {
		switch {
		case isEvent(record, wire.EventRoundStarted):
			dealer, _ = record.Int(wire.KeyDealer)
		case isEvent(record, wire.EventRoundEnd) && dealer != 0:
			code, _ := record.Int(wire.KeyResultType)
			results = append(results, code)
		}
	}

	if !slices.Contains(results, int(wire.ResultTsumo)) || !slices.Contains(results, int(wire.ResultRon)) {
		return fmt.Errorf("%s: no tsumo and ron both in rounds dealt by a seat other than 0", name)
	}

	return nil
}

func doubleRonOnHonba() (recording, error) {
	const name = "double-ron-on-honba"
	played, err := eagerSeeded(name, eagerDoubleRonSeed, endsInGame(result(wire.ResultExhaustiveDraw)))
	if err != nil {
		return recording{}, err
	}

	dealt, err := cutAfter(name, played, wire.EventRoundStarted, doubleRonOccurrence)
	if err != nil {
		return recording{}, err
	}

	doubleRon := ronResult(0,
		win(1, field(wire.KeyScoreChanges, wire.StrMap{{Key: "0", Value: n(-22)}, {Key: "1", Value: n(22)}})),
		win(3, field(wire.KeyScoreChanges, wire.StrMap{{Key: "0", Value: n(-16)}, {Key: "3", Value: n(16)}})))
	err = requireOutcome(name, dealt, thenRecord(doubleRon, wire.EventRoundStarted, wire.Map{
		field(wire.KeyRoundNumber, n(doubleRonRoundNumber)), field(wire.KeyHonba, n(0)),
	}))
	if err != nil {
		return recording{}, err
	}

	cut, err := cutAfter(name, played, wire.EventRoundEnd, doubleRonOccurrence)
	if err != nil {
		return recording{}, err
	}

	return cut, requireOutcome(name, cut, endsAt(result(wire.ResultTsumo, field(wire.KeyWinnerSeat, n(2)))))
}

func truncatedMidRound() (recording, error) {
	played, err := kansFixture()
	if err != nil {
		return recording{}, err
	}

	return cutAfter("truncated-mid-round", played, wire.EventDoraRevealed, -1)
}

func truncatedAfterRound() (recording, error) {
	played, err := fullGameFixture()
	if err != nil {
		return recording{}, err
	}

	return cutAfter("truncated-after-round", played, wire.EventRoundEnd, 1)
}
