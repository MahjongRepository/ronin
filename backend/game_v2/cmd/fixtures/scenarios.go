package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	player           = "Alice"
	robber           = "Bob"
	anchorCharlie    = "Charlie"
	startConfirmedAt = 3
)

type env struct {
	ctx    context.Context
	logger *slog.Logger
}

type scenario struct {
	name  string
	build func(env) ([]transcript, error)
}

func seatScenarios() []scenario {
	return []scenario{
		{"call_prompt", callPrompt},
		{"chi_prompt", chiPrompt},
		{"red_five_pon", redFivePon},
		{"ron_call", ronCall},
		{"added_kan", addedKan},
		{"full_turn", fullTurn},
		{"kan_choice", kanChoice},
		{"own_turn", ownTurn},
		{"riichi_kan", riichiKan},
		{"bank_reconnect", bankReconnect},
		{"reconnect", reconnect},
		{"riichi_reconnect", riichiReconnect},
		{"chankan_robbed", chankanRobbed},
		{"chankan_passed", chankanPassed},
		{"double_ron", doubleRon},
		{"final_round", finalRound},
		{"game_end_reconnect", gameEndReconnect},
		{"resync_before_deal", resyncBeforeDeal},
		{"resync", resync},
		{"seat_left", seatLeft},
		{"first_turn_win", firstTurnWin},
		{"anchor", anchor},
	}
}

func generateSeatTranscripts(ctx context.Context, logger *slog.Logger) (map[string][]byte, error) {
	generated := map[string][]byte{}
	for _, sc := range seatScenarios() {
		transcripts, err := sc.build(env{ctx: ctx, logger: logger})
		if err != nil {
			return nil, err
		}
		for _, t := range transcripts {
			if t.scenario != sc.name {
				return nil, fmt.Errorf("scenario %s wrote a transcript named %s", sc.name, t.scenario)
			}
			text, textErr := t.text()
			if textErr != nil {
				return nil, textErr
			}
			generated[t.fileName()] = []byte(text)
		}
	}
	return generated, nil
}

const maxDealerPasses = 8

func (e env) play(
	s *staging, setup gameSetup, script func(g *seatedGame) ([]transcript, error),
) ([]transcript, error) {
	if s.err != nil {
		return nil, s.err
	}

	setup.dealers = fillerDealers{}
	for range maxDealerPasses {
		g, err := openSeatedGame(e.ctx, e.logger, setup)
		if err != nil {
			return nil, err
		}
		transcripts, playErr := script(g)
		playErr = errors.Join(playErr, s.err)
		dealt := g.dealtDealers()
		closeErr := g.close(e.ctx)
		if closeErr != nil {
			return nil, errors.Join(playErr, closeErr)
		}

		if s.err != nil || fillersMatch(setup.rounds, setup.start, setup.dealers, dealt) {
			return transcripts, playErr
		}
		setup.dealers = dealt
	}
	return nil, fmt.Errorf("%s: the seed's later rounds found no dealers in %d passes", setup.gameID, maxDealerPasses)
}

func fillersMatch(
	rounds []stagedWall, start play.Option[play.StartPosition], planned, dealt fillerDealers,
) bool {
	first := firstFillerRound(rounds, start)
	lastStaged := rounds[len(rounds)-1].dealer
	for roundNumber, dealer := range dealt {
		if roundNumber >= first && planned.of(roundNumber, lastStaged) != dealer {
			return false
		}
	}
	return true
}

func alone(gameID string, rounds ...stagedWall) gameSetup {
	return gameSetup{gameID: gameID, players: []string{player}, rounds: rounds}
}

func withRobber(gameID string, rounds ...stagedWall) gameSetup {
	return gameSetup{gameID: gameID, players: []string{player, robber}, rounds: rounds}
}

func (g gameSetup) from(start play.StartPosition) gameSetup {
	g.start = play.Some(start)
	return g
}

func joinAndConfirm(g *seatedGame, names ...string) {
	for _, name := range names {
		g.client(name).join()
	}
	for _, name := range names {
		g.client(name).confirmRound(secs(startConfirmedAt), "start confirmed")
	}
}

func south1() play.StartPosition {
	return play.StartPosition{Scores: [tile.SeatCount]int{32000, 24000, 23000, 21000}, Wind: tile.South}
}

func callPrompt(e env) ([]transcript, error) {
	var s staging
	called := s.id(0, "3m")
	staged := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(3, "1245689m13579p1s"),
			slices.Concat(s.ids(0, "12m"), s.ids(1, "333m"), s.ids(0, "4m678p2s7s"), s.ids(1, "7s"), s.ids(0, "3z")),
			s.ids(2, "1245689m24689p2s"),
			s.ids(1, "12456m1359p4569s"),
		},
		draws: []stagedDraw{
			s.draw(0, called), s.draw(2, s.id(2, "7s")), s.draw(3, s.id(0, "7z")), s.draw(0, s.id(0, "6z")),
			s.draw(1, s.id(0, "1s")),
		},
	}

	return e.play(&s, alone("seat-call-prompt", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.labelEvent("dealt", wire.EventRoundStarted)
		alice.labelEvent("prompt", wire.EventCallPrompt)
		alice.chi(secs(5), "chi chosen", called, s.id(0, "1m"), s.id(0, "2m"))
		alice.labelEvent("turn", wire.EventTurn)
		alice.dropUnseen(secs(6))
		alice.reconnect(secs(7))
		alice.labelSession("reconnected", gameReconnectedType)
		alice.labelEvent("turn re-sent", wire.EventTurn)
		alice.discard(secs(12), "discarded", s.id(0, "3z"))
		alice.labelEvent("pon prompt", wire.EventCallPrompt)
		alice.labelEvent("seat 2 drew", wire.EventDrawNotice)
		alice.pass(secs(14))
		alice.labelEvent("next turn", wire.EventDraw)
		return g.transcripts("call_prompt", player)
	})
}

func chiPrompt(e env) ([]transcript, error) {
	var s staging
	staged := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(3, "1245689m13579p1s"),
			s.ids(0, "459m2468p1357s34z"),
			s.ids(2, "1245689m24689p2s"),
			s.ids(1, "12456m1359p4569s"),
		},
		draws: []stagedDraw{s.draw(0, s.id(0, "3m")), s.draw(1, s.id(0, "7z"))},
	}

	return e.play(&s, alone("seat-chi-prompt", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.labelEvent("prompt", wire.EventCallPrompt)
		alice.pass(secs(5))
		alice.labelEvent("turn", wire.EventDraw)
		return g.transcripts("chi_prompt", player)
	})
}

func redFivePon(e env) ([]transcript, error) {
	var s staging
	fives := s.ids(0, "5555m")
	staged := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(3, "124689m13579p1s1z"),
			slices.Concat(fives[:3], s.ids(0, "2468p1357s34z")),
			s.ids(2, "124689m24689p2s2z"),
			s.ids(1, "1246m1359p4569s1z"),
		},
		draws: []stagedDraw{s.draw(0, fives[3])},
	}

	return e.play(&s, alone("seat-red-five-pon", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.labelEvent("prompt", wire.EventCallPrompt)
		alice.pon(secs(5), "pon chosen", fives[3], fives[1], fives[2])
		alice.labelEvent("turn", wire.EventTurn)
		return g.transcripts("red_five_pon", player)
	})
}

func ronCall(e env) ([]transcript, error) {
	var s staging
	staged := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(3, "1245689m13579p1s"),
			slices.Concat(s.ids(0, "45m123456789p"), s.ids(1, "33m")),
			s.ids(2, "1245689m24689p2s"),
			s.ids(1, "12456m1359p4569s"),
		},
		draws: []stagedDraw{s.draw(0, s.id(0, "3m")), s.draw(1, s.id(0, "7z"))},
	}

	return e.play(&s, alone("seat-ron-call", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.labelEvent("prompt", wire.EventCallPrompt)
		alice.pass(secs(5))
		alice.labelEvent("turn", wire.EventDraw)
		return g.transcripts("ron_call", player)
	})
}

func addedKan(e env) ([]transcript, error) {
	var s staging
	chun := s.id(2, "7z")
	junk := s.id(0, "4z")
	staged := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(3, "156789m1234p123s"),
			slices.Concat(s.ids(0, "77z"), s.ids(0, "234m78s"), s.ids(1, "567p"), s.ids(1, "55s"), []tile.TileID{junk}),
			s.ids(2, "156789m1234p123s"),
			s.ids(1, "156789m1234p123s"),
		},
		draws: []stagedDraw{
			s.draw(0, chun), s.draw(2, s.id(0, "1z")), s.draw(3, s.id(0, "2z")), s.draw(0, s.id(0, "3z")),
			s.draw(1, s.id(3, "7z")),
		},
	}

	return e.play(&s, alone("seat-added-kan", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.pon(secs(5), "pon chosen", chun, s.id(0, "7z"), s.id(1, "7z"))
		alice.discard(secs(6), "discarded", junk)
		g.waitUntil(secs(12))
		alice.labelEvent("kan offer", wire.EventDraw)
		return g.transcripts("added_kan", player)
	})
}

func fullTurn(e env) ([]transcript, error) {
	var s staging
	staged := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(3, "1245689m13579p1s"),
			slices.Concat(s.ids(0, "3333m"), s.ids(0, "45m456789p9s")),
			s.ids(2, "1245689m24689p2s"),
			s.ids(1, "12456m1359p4569s"),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(0, "7z")), s.draw(1, s.id(0, "6z")), s.draw(2, s.id(0, "3z")), s.draw(3, s.id(0, "2z")),
			s.draw(0, s.id(0, "1z")), s.draw(1, s.id(2, "9s")),
		},
	}

	return e.play(&s, alone("seat-full-turn", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.discard(secs(5), "discarded", s.id(0, "6z"))
		g.waitUntil(secs(12))
		alice.labelEvent("win offer", wire.EventDraw)
		return g.transcripts("full_turn", player)
	})
}

func kanChoice(e env) ([]transcript, error) {
	var s staging
	staged := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(1, "2345678m12p1346s"),
			slices.Concat(s.ids(0, "1111m"), s.ids(0, "999p"), s.ids(0, "246p258s")),
			s.ids(2, "2345678m12p1346s"),
			s.ids(3, "2345678m12p1346s"),
		},
		draws:   []stagedDraw{s.draw(0, s.id(0, "1z")), s.draw(1, s.id(3, "9p"))},
		rinshan: []tile.TileID{s.id(0, "4z")},
	}

	return e.play(&s, alone("seat-kan-choice", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.labelEvent("dealt", wire.EventRoundStarted)
		alice.labelEvent("kan offer", wire.EventDraw)
		alice.kan(secs(5), s.id(0, "9p"), kanClosed)
		alice.labelEvent("rinshan", wire.EventDraw)
		return g.transcripts("kan_choice", player)
	})
}

func ownTurnWall(s *staging) stagedWall {
	return stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(3, "2456789m19p1234s"),
			slices.Concat(s.ids(0, "111m"), s.ids(0, "234p"), s.ids(1, "567p"), s.ids(0, "78s"), s.ids(1, "55s")),
			s.ids(2, "2345678m123p123s"),
			s.ids(1, "2345678m189p123s"),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(0, "2z")), s.draw(1, s.id(3, "1m")), s.draw(2, s.id(0, "6s")), s.draw(3, s.id(0, "3z")),
			s.draw(0, s.id(0, "6z")), s.draw(1, s.id(0, "9s")),
		},
		rinshan: []tile.TileID{s.id(0, "4z")},
	}
}

func ownTurn(e env) ([]transcript, error) {
	var s staging
	staged := ownTurnWall(&s)

	return e.play(&s, alone("seat-own-turn", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		alice.labelEvent("game started", wire.EventGameStarted)
		alice.labelEvent("dealt", wire.EventRoundStarted)
		alice.dropUnseen(secs(3.5))
		alice.labelEvent("first draw", wire.EventDraw)
		alice.reconnect(secs(4.5))
		alice.labelSession("reconnected", gameReconnectedType)
		alice.labelEvent("draw re-sent", wire.EventDraw)
		alice.kan(secs(5), s.id(0, "1m"), kanClosed)
		alice.labelEvent("rinshan", wire.EventDraw)
		alice.riichi(secs(11), "riichi chosen", s.id(0, "4z"))
		alice.labelEvent("ron prompt", wire.EventCallPrompt)
		alice.pass(secs(13))
		alice.labelEvent("furiten", wire.EventFuriten)
		alice.labelEvent("tsumo draw", wire.EventDraw)
		alice.tsumo(secs(15), "tsumo chosen")
		alice.labelEvent("round end", wire.EventRoundEnd)
		alice.confirmRound(secs(16), "confirmed")
		alice.labelEvent("next round", wire.EventRoundStarted)
		alice.labelEvent("dealer draw", wire.EventDraw)
		return g.transcripts("own_turn", player)
	})
}

func riichiKan(e env) ([]transcript, error) {
	var s staging
	declaration := s.id(0, "4z")
	staged := ownTurnWall(&s)
	staged.draws = []stagedDraw{
		s.draw(0, s.id(0, "2z")), s.draw(1, declaration), s.draw(2, s.id(0, "3z")), s.draw(3, s.id(0, "6z")),
		s.draw(0, s.id(0, "7z")), s.draw(1, s.id(3, "1m")),
	}
	staged.rinshan = []tile.TileID{s.id(0, "9s")}

	return e.play(&s, alone("seat-riichi-kan", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.labelEvent("riichi offer", wire.EventDraw)
		alice.riichi(secs(5), "riichi chosen", declaration)
		alice.labelEvent("kan offer", wire.EventDraw)
		alice.kan(secs(6), s.id(0, "1m"), kanClosed)
		alice.labelEvent("tsumo draw", wire.EventDraw)
		return g.transcripts("riichi_kan", player)
	})
}

func bankReconnect(e env) ([]transcript, error) {
	var s staging
	staged := ownTurnWall(&s)

	return e.play(&s, alone("seat-bank-reconnect", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.labelEvent("first draw", wire.EventDraw)
		alice.dropUnseen(secs(8.5))
		alice.reconnect(secs(9.5))
		alice.labelSession("reconnected", gameReconnectedType)
		alice.labelEvent("draw re-sent", wire.EventDraw)
		alice.discard(secs(11), "discarded", s.id(3, "1m"))
		return g.transcripts("bank_reconnect", player)
	})
}

func reconnect(e env) ([]transcript, error) {
	var s staging
	haku := s.id(2, "5z")
	junk := s.id(0, "4z")
	staged := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(3, "156789m1234p123s"),
			slices.Concat(s.ids(0, "55z"), s.ids(0, "234m78s"), s.ids(1, "567p"), s.ids(1, "55s"), []tile.TileID{junk}),
			s.ids(2, "156789m1234p123s"),
			s.ids(1, "156789m1234p123s"),
		},
		draws: []stagedDraw{s.draw(0, haku), s.draw(2, s.id(0, "6s"))},
	}

	return e.play(&s, alone("seat-reconnect", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.labelEvent("prompt", wire.EventCallPrompt)
		alice.dropUnseen(secs(4.5))
		alice.reconnect(secs(5.5))
		alice.labelSession("reconnected", gameReconnectedType)
		alice.labelEvent("prompt re-sent", wire.EventCallPrompt)
		alice.pon(secs(6.5), "pon chosen", haku, s.id(0, "5z"), s.id(1, "5z"))
		alice.labelEvent("turn", wire.EventTurn)
		alice.discard(secs(8), "discarded", junk)
		alice.labelEvent("ron prompt", wire.EventCallPrompt)
		alice.ron(secs(10), "ron chosen")
		alice.labelEvent("round end", wire.EventRoundEnd)
		alice.replacedByAnotherTab(secs(10.5), "replaced")
		return g.transcripts("reconnect", player)
	})
}

func riichiReconnect(e env) ([]transcript, error) {
	var s staging
	staged := ownTurnWall(&s)

	setup := alone("seat-riichi-reconnect", staged).from(south1())
	return e.play(&s, setup, func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.labelEvent("first draw", wire.EventDraw)
		alice.riichi(secs(5), "riichi chosen", s.id(0, "1m"))
		alice.labelEvent("riichi accepted", wire.EventRiichiDeclared)
		alice.labelEvent("ron prompt", wire.EventCallPrompt)
		alice.dropUnseen(secs(5.5))
		alice.reconnect(secs(6.5))
		alice.labelSession("reconnected", gameReconnectedType)
		alice.labelEvent("ron prompt re-sent", wire.EventCallPrompt)
		alice.ron(secs(7), "ron chosen")
		alice.labelEvent("round end", wire.EventRoundEnd)
		g.waitUntil(secs(18))
		alice.labelEvent("next round", wire.EventRoundStarted)
		g.waitUntil(secs(6000))
		alice.labelEvent("game end", wire.EventGameEnd)
		return g.transcripts("riichi_reconnect", player)
	})
}

func chankanRobbed(e env) ([]transcript, error) {
	var s staging
	kanTile := s.id(0, "9m")
	staged := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(2, "357m357p35789s12z"),
			slices.Concat(s.ids(0, "999m"), s.ids(1, "246m2468p246s")),
			s.ids(3, "357m357p35789s12z"),
			s.ids(0, "11m19p19s1234567z"),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(1, "3z")), s.draw(1, s.id(1, "4z")), s.draw(2, s.id(1, "5z")), s.draw(3, s.id(1, "6z")),
			s.draw(0, s.id(1, "7z")), s.draw(1, s.id(3, "9m")),
		},
	}

	start := play.StartPosition{Scores: [tile.SeatCount]int{22000, 34000, 22000, 22000}}
	return e.play(&s, withRobber("seat-chankan-robbed", staged).from(start), func(g *seatedGame) ([]transcript, error) {
		alice, bob := g.client(player), g.client(robber)
		joinAndConfirm(g, player, robber)
		g.waitUntil(secs(4))
		alice.discard(secs(5), "discarded", s.id(1, "4z"))
		bob.discard(secs(6), "discarded", s.id(1, "6z"))
		alice.labelEvent("kan draw", wire.EventDraw)
		alice.kan(secs(7), kanTile, kanClosed)
		bob.labelEvent("chankan prompt", wire.EventCallPrompt)
		bob.ron(secs(8), "ron chosen")
		bob.labelEvent("round end", wire.EventRoundEnd)
		alice.labelEvent("round end", wire.EventRoundEnd)
		alice.dropUnseen(secs(8.25))
		bob.confirmRound(secs(9), "confirmed")
		alice.reconnect(secs(9.25))
		alice.labelSession("reconnected", gameReconnectedType)
		alice.confirmRound(secs(10.25), "confirmed")
		alice.labelEvent("next round", wire.EventRoundStarted)
		return g.transcripts("chankan_robbed", player, robber)
	})
}

func chankanPassed(e env) ([]transcript, error) {
	var s staging
	ponned := s.id(2, "6p")
	staged := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(2, "258m17p369s12345z"),
			slices.Concat(s.ids(0, "66p"), s.ids(1, "147m19p258s123z")),
			s.ids(3, "258m17p369s12345z"),
			s.ids(0, "123456789m45p19s"),
		},
		draws: []stagedDraw{
			s.draw(0, ponned), s.draw(2, s.id(0, "7z")), s.draw(3, s.id(1, "1s")), s.draw(0, s.id(1, "7z")),
			s.draw(1, s.id(3, "6p")),
		},
	}

	return e.play(&s, withRobber("seat-chankan-passed", staged), func(g *seatedGame) ([]transcript, error) {
		alice, bob := g.client(player), g.client(robber)
		joinAndConfirm(g, player, robber)
		g.waitUntil(secs(4))
		alice.pon(secs(5), "pon chosen", ponned, s.id(0, "6p"), s.id(1, "6p"))
		alice.discard(secs(6), "discarded", s.id(1, "1z"))
		bob.discard(secs(7), "discarded", s.id(0, "9s"))
		alice.kan(secs(8), s.id(3, "6p"), kanAdded)
		bob.labelEvent("chankan prompt", wire.EventCallPrompt)
		bob.dropUnseen(secs(8.25))
		bob.reconnect(secs(9.25))
		bob.labelSession("reconnected", gameReconnectedType)
		bob.labelEvent("prompt re-sent", wire.EventCallPrompt)
		bob.pass(secs(9.75))
		bob.labelEvent("kan", wire.EventMeld)
		return g.transcripts("chankan_passed", robber)
	})
}

func doubleRonWall(s *staging, alice []tile.TileID) stagedWall {
	return stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(2, "258m258p258s1234z"),
			alice,
			s.ids(3, "258m258p258s1234z"),
			slices.Concat(s.ids(1, "345678m234s"), s.ids(0, "568p"), s.ids(1, "8p")),
		},
	}
}

func doubleRon(e env) ([]transcript, error) {
	var s staging
	staged := doubleRonWall(&s, s.ids(0, "234567m23p34566s"))
	staged.draws = []stagedDraw{s.draw(0, s.id(2, "4p"))}

	return e.play(&s, withRobber("seat-double-ron", staged), func(g *seatedGame) ([]transcript, error) {
		alice, bob := g.client(player), g.client(robber)
		joinAndConfirm(g, player, robber)
		g.waitUntil(secs(4))
		alice.labelEvent("ron prompt", wire.EventCallPrompt)
		alice.ron(secs(5), "ron chosen")
		bob.ron(secs(5.5), "ron chosen")
		alice.labelEvent("round end", wire.EventRoundEnd)
		alice.dropUnseen(secs(5.75))
		bob.confirmRound(secs(6.5), "confirmed")
		alice.reconnect(secs(6.75))
		alice.labelSession("reconnected", gameReconnectedType)
		alice.confirmRound(secs(7.75), "confirmed")
		alice.labelEvent("next round", wire.EventRoundStarted)
		return g.transcripts("double_ron", player)
	})
}

func finalRound(e env) ([]transcript, error) {
	var s staging
	staged := doubleRonWall(&s, s.ids(0, "11m19p19s1234567z"))
	staged.draws = []stagedDraw{s.draw(0, s.id(0, "9m"))}

	return e.play(&s, alone("seat-final-round", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.labelEvent("ron prompt", wire.EventCallPrompt)
		alice.ron(secs(5), "ron chosen")
		alice.labelEvent("round end", wire.EventRoundEnd)
		alice.labelEvent("game end", wire.EventGameEnd)
		g.waitUntil(secs(6))
		return g.transcripts("final_round", player)
	})
}

func kyuushuWall(s *staging) stagedWall {
	return stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(2, "258m258p258s1234z"),
			s.ids(0, "159m159p159s1234z"),
			s.ids(3, "258m258p258s1234z"),
			s.ids(1, "2345678m2346p23s"),
		},
		draws: []stagedDraw{s.draw(0, s.id(0, "5z")), s.draw(1, s.id(1, "5z"))},
	}
}

func resyncBeforeDeal(e env) ([]transcript, error) {
	var s staging
	staged := kyuushuWall(&s)

	return e.play(&s, alone("seat-resync-before-deal", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		alice.join()
		alice.labelEvent("game started", wire.EventGameStarted)
		alice.labelEvent("dealt", wire.EventRoundStarted)
		alice.resync(secs(1), "resync asked", "")
		alice.labelSession("start snapshot", gameReconnectedType)
		g.waitUntil(startConfirmTimeout + secs(1))
		alice.labelEvent("first draw", wire.EventDraw)
		return g.transcripts("resync_before_deal", player)
	})
}

func resync(e env) ([]transcript, error) {
	var s staging
	staged := kyuushuWall(&s)

	return e.play(&s, alone("seat-resync", staged), func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		alice.labelSession("joined", gameJoinedType)
		alice.labelEvent("game started", wire.EventGameStarted)
		g.waitUntil(secs(4))
		alice.labelEvent("dealt", wire.EventRoundStarted)
		alice.labelEvent("first draw", wire.EventDraw)
		alice.resync(secs(4), "turn resync asked", "")
		alice.labelSession("turn snapshot", gameReconnectedType)
		alice.labelEvent("draw re-sent", wire.EventDraw)
		alice.kyuushu(secs(5), "kyuushu chosen")
		alice.labelEvent("round end", wire.EventRoundEnd)
		alice.resync(secs(6.5), "advance resync asked", "")
		alice.labelSession("advance snapshot", gameReconnectedType)
		alice.confirmRound(secs(7.5), "confirmed")
		alice.labelEvent("next round", wire.EventRoundStarted)
		return g.transcripts("resync", player)
	})
}

func gameEndReconnect(e env) ([]transcript, error) {
	var s staging
	staged := kyuushuWall(&s)

	setup := alone("seat-game-end-reconnect", staged).from(south1())
	return e.play(&s, setup, func(g *seatedGame) ([]transcript, error) {
		alice := g.client(player)
		joinAndConfirm(g, player)
		g.waitUntil(secs(4))
		alice.labelEvent("first draw", wire.EventDraw)
		alice.kyuushu(secs(5), "kyuushu chosen")
		alice.labelEvent("kyuushu round end", wire.EventRoundEnd)
		alice.confirmRound(secs(6), "confirmed")
		alice.labelEvent("second deal", wire.EventRoundStarted)
		alice.dropUnseen(secs(7.5))
		alice.reconnect(secs(8.5))
		alice.labelSession("reconnected", gameReconnectedType)
		g.waitUntil(secs(6000))
		alice.labelEvent("last round end", wire.EventRoundEnd)
		alice.labelEvent("game end", wire.EventGameEnd)
		return g.transcripts("game_end_reconnect", player)
	})
}

func seatLeft(e env) ([]transcript, error) {
	var s staging
	aliceDraw := s.id(0, "6z")
	staged := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(2, "258m258p258s1234z"),
			s.ids(0, "147m147p147s1234z"),
			s.ids(3, "369m369p369s1234z"),
			s.ids(1, "258m369p147s1234z"),
		},
		draws: []stagedDraw{s.draw(0, s.id(0, "5z")), s.draw(1, aliceDraw)},
	}

	return e.play(&s, withRobber("seat-left", staged), func(g *seatedGame) ([]transcript, error) {
		alice, bob := g.client(player), g.client(robber)
		joinAndConfirm(g, player, robber)
		g.waitUntil(secs(4))
		alice.labelEvent("first draw", wire.EventDraw)
		bob.dropSeen(secs(4.5))
		alice.labelSession("player left", seatControlType)
		alice.dropUnseen(secs(4.5))
		alice.reconnect(secs(5.5))
		alice.labelSession("reconnected", gameReconnectedType)
		bob.reconnect(secs(5.5))
		bob.labelSession("reconnected", gameReconnectedType)
		alice.labelSession("player back", seatControlType)
		alice.discard(secs(5.75), "discarded", aliceDraw)
		return g.transcripts("seat_left", player, robber)
	})
}

func firstTurnWin(e env) ([]transcript, error) {
	var s staging
	eastWind := s.id(1, "1z")
	east1 := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(1, "123456789m1234p"),
			s.ids(0, "456789p13579s56z"),
			s.ids(2, "123456789m1234p"),
			s.ids(0, "123456789m123p1z"),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(0, "2z")), s.draw(1, s.id(0, "3z")), s.draw(2, s.id(0, "4z")), s.draw(3, eastWind),
		},
	}
	east2 := stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(3, "123456789m1234s"),
			slices.Concat(s.ids(0, "123456789m123p"), s.ids(1, "1p")),
			s.ids(1, "123456789m1234s"),
			s.ids(2, "123456789m1234s"),
		},
		draws:  []stagedDraw{s.draw(1, s.id(0, "4p"))},
		dealer: s.seat(1),
	}

	setup := withRobber("seat-first-turn-win", east1, east2).from(play.StartPosition{
		Scores: [tile.SeatCount]int{33000, 25000, 25000, 17000},
	})
	return e.play(&s, setup, func(g *seatedGame) ([]transcript, error) {
		alice, bob := g.client(player), g.client(robber)
		joinAndConfirm(g, player, robber)
		g.waitUntil(secs(3.5))
		alice.labelEvent("first draw", wire.EventDraw)
		alice.discard(secs(4), "discarded", s.id(0, "3z"))
		bob.labelEvent("chiihou draw", wire.EventDraw)
		bob.tsumo(secs(5), "tsumo chosen")
		bob.labelEvent("round end", wire.EventRoundEnd)
		alice.labelEvent("chiihou round end", wire.EventRoundEnd)
		alice.confirmRound(secs(7), "confirmed")
		bob.confirmRound(secs(7), "confirmed")
		alice.labelEvent("tenhou deal", wire.EventRoundStarted)
		alice.labelEvent("tenhou draw", wire.EventDraw)
		alice.tsumo(secs(8), "tsumo chosen")
		alice.labelEvent("round end", wire.EventRoundEnd)
		return g.transcripts("first_turn_win", player, robber)
	})
}

func anchorEast1(s *staging) stagedWall {
	return stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(0, "123456789m1234p"),
			s.ids(1, "13579m24689p129s"),
			s.ids(2, "2468m13579p3469s"),
			slices.Concat(s.ids(3, "234567m2345p67s"), s.ids(2, "2p")),
		},
		draws: []stagedDraw{
			s.draw(0, s.id(0, "4z")), s.draw(1, s.id(0, "3z")), s.draw(2, s.id(0, "2z")), s.draw(3, s.id(0, "6z")),
			s.draw(0, s.id(1, "5s")),
		},
	}
}

func anchorEast2(s *staging) stagedWall {
	turns := [][]play.Option[tile.TileID]{
		{some(s.id(0, "3z")), some(s.id(2, "2p")), some(s.id(0, "6z")), some(s.id(2, "9m"))},
		{some(s.id(2, "7z")), {}, some(s.id(1, "6p")), some(s.id(2, "1s"))},
		{some(s.id(0, "7m")), some(s.id(1, "3z")), some(s.id(1, "9s")), some(s.id(2, "5z"))},
		{some(s.id(1, "5s")), some(s.id(3, "9p")), some(s.id(1, "2p")), some(s.id(0, "4s"))},
		{some(s.id(0, "1s")), some(s.id(1, "1z")), some(s.id(2, "9p")), some(s.id(2, "3z"))},
		{some(s.id(1, "6z")), some(s.id(2, "3p")), some(s.id(1, "4m")), some(s.id(0, "9s"))},
		{some(s.id(1, "9p")), some(s.id(3, "9s")), some(s.id(1, "4z")), some(s.id(2, "2s"))},
		{some(s.id(0, "2s")), some(s.id(3, "4p")), some(s.id(2, "3s")), some(s.id(3, "7z"))},
		{some(s.id(1, "2z")), some(s.id(1, "5z")), some(s.id(1, "6m")), some(s.id(0, "6s"))},
		{some(s.id(0, "6p")), some(s.id(2, "5s")), some(s.id(1, "1p")), some(s.id(0, "3s"))},
		{some(s.id(0, "7s"))},
	}
	order := []int{1, 2, 3, 0}
	var draws []stagedDraw
	for _, round := range turns {
		for i, drawn := range round {
			if drawn.OK {
				draws = append(draws, s.draw(order[i], drawn.Value))
			}
		}
	}

	return stagedWall{
		hands: [tile.SeatCount][]tile.TileID{
			s.ids(3, "1234567m23567p8s"),
			slices.Concat(s.ids(0, "23469m134p58s4z"), s.ids(1, "5m5p")),
			slices.Concat(s.ids(2, "136m458p679s"), s.ids(0, "257z"), s.ids(1, "7z")),
			slices.Concat(s.ids(1, "123789m7p1234s"), s.ids(0, "9p1z")),
		},
		draws:  draws,
		dealer: s.seat(1),
	}
}

func some(id tile.TileID) play.Option[tile.TileID] {
	return play.Some(id)
}

type anchorMove struct {
	client *seatClient
	pon    play.Option[[2]tile.TileID]
	riichi bool
	id     tile.TileID
}

func anchor(e env) ([]transcript, error) {
	var s staging
	east1, east2 := anchorEast1(&s), anchorEast2(&s)

	setup := gameSetup{
		gameID: "seat-anchor", players: []string{player, robber, anchorCharlie}, rounds: []stagedWall{east1, east2},
	}
	return e.play(&s, setup, func(g *seatedGame) ([]transcript, error) {
		alice, bob, charlie := g.client(player), g.client(robber), g.client(anchorCharlie)
		for _, c := range []*seatClient{alice, bob, charlie} {
			c.join()
		}
		for _, c := range []*seatClient{alice, bob, charlie} {
			c.confirmRound(secs(startConfirmedAt), "")
		}
		alice.discard(secs(3.5), "", s.id(0, "3z"))
		charlie.discard(secs(4), "", s.id(0, "2z"))
		bob.discard(secs(4.5), "", s.id(0, "6z"))
		bob.ron(secs(5), "")
		alice.confirmRound(secs(5.5), "")
		bob.confirmRound(secs(5.5), "")
		charlie.confirmRound(secs(6), "")
		alice.labelEvent("east 2 dealt", wire.EventRoundStarted)

		moves := []anchorMove{
			{client: alice, id: s.id(0, "4z")},
			{client: charlie, id: s.id(0, "2z")},
			{client: bob, id: s.id(0, "1z")},
			{client: alice, id: s.id(2, "7z")},
			{client: charlie, id: s.id(2, "7z"), pon: play.Some([2]tile.TileID{s.id(0, "7z"), s.id(1, "7z")})},
			{client: charlie, id: s.id(0, "5z")},
			{client: bob, id: s.id(1, "1s")},
			{client: alice, id: s.id(0, "1p")},
			{client: charlie, id: s.id(1, "3z")},
			{client: bob, id: s.id(1, "9s")},
			{client: alice, id: s.id(0, "3z")},
			{client: charlie, id: s.id(3, "9p")},
			{client: bob, id: s.id(1, "2p")},
			{client: alice, id: s.id(0, "1s")},
			{client: charlie, id: s.id(1, "1z")},
			{client: bob, id: s.id(0, "6z"), riichi: true},
			{client: alice, id: s.id(1, "6z")},
			{client: charlie, id: s.id(2, "3p")},
			{client: bob, id: s.id(1, "4m")},
			{client: alice, id: s.id(1, "9p")},
			{client: charlie, id: s.id(3, "9s")},
			{client: bob, id: s.id(1, "4z")},
			{client: alice, id: s.id(0, "2s")},
			{client: charlie, id: s.id(3, "4p")},
			{client: bob, id: s.id(2, "3s")},
			{client: alice, id: s.id(1, "2z")},
			{client: charlie, id: s.id(1, "5z")},
			{client: bob, id: s.id(1, "6m")},
		}
		at := secs(6.5)
		for _, m := range moves {
			switch {
			case m.pon.OK:
				m.client.pon(at, "", m.id, m.pon.Value[0], m.pon.Value[1])
			case m.riichi:
				m.client.riichi(at, "", m.id)
			default:
				m.client.discard(at, "", m.id)
			}
			at += secs(0.5)
		}

		alice.labelEvent("own turn", wire.EventDraw)
		alice.discard(at, "discarded", s.id(0, "9m"))
		charlie.discard(at+secs(0.5), "", s.id(2, "5s"))
		alice.labelEvent("call offer", wire.EventCallPrompt)
		alice.pass(at + secs(1.5))
		bob.discard(at+secs(2), "", s.id(1, "1p"))
		alice.labelEvent("riichi offer", wire.EventDraw)
		return g.transcripts("anchor", player)
	})
}
