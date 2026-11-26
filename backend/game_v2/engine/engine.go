// Package engine is the only public API of the game engine: a riichi mahjong game under ronin's
// fixed rules, played as a value through its calls. A Game says what it awaits, offers the awaited
// seat a play.Decision, applies its play.Action or refuses it with a play.Refusal, and returns the
// events each seat may see, each with its play.Visibility. View gives what one seat may see of the
// game, and CheckInvariants checks what every step keeps.
//
// A Game is a value: every method that moves it returns the new game and leaves its receiver as it
// was, so a caller may keep or branch from any state. Every slice a method returns is the caller's
// own, down to the slices of the events, decisions and views it holds: writing into it changes no
// game.
//
// A game's randomness comes from a seed by the shake256-v1 scheme, whose functions are exposed for
// the tools that sample it: each round's wall and dice, the round as it is dealt, the first dealer
// and the seating. Shanten is exposed for the tools that play by a policy, and SettleTsumo and
// SettleRon for the tools that check how wins are scored and settled against another engine.
package engine

import (
	"slices"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/game"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/record"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rng"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/shanten"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Setup is everything a game is built from: the ruleset it plays under, its zero value the default
// play.RulesetTenhou; where its walls come from; and the position it starts at, absent for East 1
// with every seat at the starting score.
type Setup struct {
	Ruleset play.Ruleset
	Walls   play.WallSource
	Start   play.Option[play.StartPosition]
}

// Game is the full state of a game, held by its caller. Its zero value is not a game and must not
// be played or read; build one with NewGame.
type Game struct {
	game game.Game
}

// NewGame sets a game up and deals its first round, returning the game awaiting
// play.AwaitingDealt and its first events; Begin makes the dealer's first draw. A play.Fixed
// source deals seat 0 first with every throw (1, 1) and ends the game with
// play.EndFixedWallsDealt once its walls run out.
func NewGame(setup Setup) (Game, []play.Emitted, error) {
	g, events, err := game.New(setup.Ruleset, setup.Walls, setup.Start)
	if err != nil {
		return Game{}, nil, err
	}

	return Game{game: g}, detachFreshEvents(events), nil
}

// UnknownRulesetError reports a setup whose Ruleset names no ruleset.
type UnknownRulesetError = rules.UnknownRulesetError

// InvalidWallError reports a fixed wall that does not hold every tile id exactly once; it wraps
// the error naming the first tile listed twice.
type InvalidWallError = game.InvalidWallError

// NoFixedWallError reports a setup with no wall to deal: an empty Fixed list, or no source.
type NoFixedWallError = game.NoFixedWallError

// StartScoreOffHundredsError reports a start score that is not a whole number of hundreds.
type StartScoreOffHundredsError = game.StartScoreOffHundredsError

// StartScoreBelowTobiError reports a start score below the tobi threshold, which ends a game.
type StartScoreBelowTobiError = game.StartScoreBelowTobiError

// NegativeStartCountError reports a start position with negative honba or riichi sticks.
type NegativeStartCountError = game.NegativeStartCountError

// StartPointsOffTotalError reports start scores and riichi sticks that do not add up to the points
// every game holds.
type StartPointsOffTotalError = game.StartPointsOffTotalError

// StartInNorthError reports a start in North, which a hanchan never reaches, or past it.
type StartInNorthError = game.StartInNorthError

// Act applies one answer of seat and returns the game after it and the events it caused. A
// refusal returns the receiver unchanged and no events.
func (g Game) Act(seat tile.Seat, action play.Action) (Game, []play.Emitted, play.Option[play.Refusal]) {
	next, events, refusal := g.game.Act(seat, action)
	return Game{game: next}, detachFreshEvents(events), refusal
}

// DealNextRound deals the round that follows the one just over: one RoundStarted per seat, the
// game then awaiting play.AwaitingDealt until Begin makes its dealer's first draw. Once every fixed
// wall has been dealt it ends the game instead with play.EndFixedWallsDealt and a GameEnded.
// Refused as not awaited unless the game awaits play.AwaitingRoundOver.
func (g Game) DealNextRound() (Game, []play.Emitted, play.Option[play.Refusal]) {
	next, events, refusal := g.game.DealNextRound()
	return Game{game: next}, detachFreshEvents(events), refusal
}

// Begin makes the dealer's first draw of the round just dealt and returns its events. Refused as
// not awaited unless the game awaits play.AwaitingDealt.
func (g Game) Begin() (Game, []play.Emitted, play.Option[play.Refusal]) {
	next, events, refusal := g.game.Begin()
	return Game{game: next}, detachFreshEvents(events), refusal
}

// Decision returns the prompt of seat: where it stands, its legal actions and its default action.
// False for a seat the game does not await.
func (g Game) Decision(seat tile.Seat) (play.Decision, bool) {
	return g.game.Decision(seat)
}

// Awaiting returns what the game waits for now: the dealer's first draw of a round just dealt, a
// seat's turn, the answers of the seats a call prompt still waits on, in seat order, the next
// round's deal, or nothing once the game is over.
func (g Game) Awaiting() play.Awaiting {
	return g.game.Awaiting()
}

// Outranked reports whether seat still owes an answer to the open call prompt that can no longer
// change its outcome: another seat's claim outranks every offer it holds. The seat keeps its
// prompt and its answer is taken, but the call settles without waiting for it.
func (g Game) Outranked(seat tile.Seat) bool {
	return g.game.Outranked(seat)
}

// LegalActions returns every action seat may take now, none for a seat the game does not await.
func (g Game) LegalActions(seat tile.Seat) []play.Action {
	return g.game.LegalActions(seat)
}

// DefaultAction returns the action a timeout plays for seat: on a turn the drawn tile when it is
// a legal discard, else the last legal discard; on a call prompt pass. False for a seat the game
// does not await.
func (g Game) DefaultAction(seat tile.Seat) (play.Action, bool) {
	return g.game.DefaultAction(seat)
}

// Disguised returns action naming other held copies of the same tiles, each picked by pick, which
// returns an index below the count it is given; the engine accepts either action alike. Any other
// action is returned as it is.
func (g Game) Disguised(seat tile.Seat, action play.Action, pick func(n int) int) play.Action {
	return g.game.Disguised(seat, action, pick)
}

// View returns what seat may see of the game now: the facts it knows, which its visible events
// alone rebuild, and its decision when the game awaits it. It holds no other seat's concealed
// tiles, decision, furiten or pending answer.
func (g Game) View(seat tile.Seat) play.SeatView {
	return g.game.SeatView(seat)
}

// Follow returns seen after one more event of the game, taken in the order the game returned it;
// an event seen's seat may not see changes nothing.
func Follow(seen play.SeatRecord, event play.Emitted) play.SeatRecord {
	return record.Apply(seen, event)
}

// Standings returns the final standings once the game is over.
func (g Game) Standings() play.Option[play.Standings] {
	return g.game.Standings()
}

// CheckInvariants checks what every step of a game keeps: each of the 136 tiles in exactly one
// place, the scores and riichi sticks adding up to the points the game started with, and once the
// game is over final scores that add up to them too, points that sum to 0 and the places 1 to 4.
// The first broken one is returned.
func (g Game) CheckInvariants() error {
	return g.game.CheckInvariants()
}

// OwnershipError reports a tile missing or in more than one place; it wraps the error naming the
// lowest tile id at fault.
type OwnershipError = game.OwnershipError

// TablePointsError reports scores and riichi sticks that no longer add up to the starting points.
type TablePointsError = game.TablePointsError

// FinalScoresError reports final scores that do not add up to the starting points.
type FinalScoresError = game.FinalScoresError

// FinalPointsError reports final points that do not sum to 0.
type FinalPointsError = game.FinalPointsError

// PlacementsError reports final places, by seat, that are not 1 to 4.
type PlacementsError = game.PlacementsError

func detachFreshEvents(freshEvents []play.Emitted) []play.Emitted {
	for i := range freshEvents {
		freshEvents[i].Event = cloneEvent(freshEvents[i].Event)
	}

	return freshEvents
}

func cloneEvent(event play.Event) play.Event {
	switch e := event.(type) {
	case play.Called:
		e.Meld.Tiles = slices.Clone(e.Meld.Tiles)
		return e
	case play.RoundEnded:
		e.Result = record.CloneResult(e.Result)
		return e
	case play.GameStarted, play.RoundStarted, play.Drew, play.DrewNotice, play.Discarded, play.RiichiDeposited,
		play.FuritenChanged, play.PaoAssigned, play.DoraRevealed, play.GameEnded:
	}

	return event
}

const (
	SeedBytes  = rng.SeedBytes
	RNGVersion = rng.Version
)

// Seed is a game seed: SeedBytes bytes, written as twice as many hex characters. A play.Seeded
// source takes it as is.
type Seed = rng.Seed

// SeedLengthError reports a seed string of the wrong length.
type SeedLengthError = rng.SeedLengthError

// SeedNotHexError reports a seed string holding a character that is not a hex digit.
type SeedNotHexError = rng.SeedNotHexError

// ParseSeed reads a seed from its hex form, upper or lower case, with nothing around it: a
// SeedLengthError or SeedNotHexError otherwise.
func ParseSeed(hex string) (Seed, error) {
	return rng.ParseSeed(hex)
}

// RoundWall returns the shuffled tile ids and the dice of the round seed deals as roundNumber,
// which counts every hand of the game from 0, repeats included.
func RoundWall(seed Seed, roundNumber uint32) ([tile.TileIDCount]tile.TileID, tile.Dice) {
	return rng.RoundWall(seed, roundNumber)
}

// FirstDealer returns the first dealer seed picks and the two throws that pick it.
func FirstDealer(seed Seed) (dealer tile.Seat, first, second tile.Dice) {
	return rng.FirstDealer(seed)
}

// SeatPermutation returns the order seed seats a game's players in: the first player at the first
// seat it lists, and so on.
func SeatPermutation(seed Seed) [tile.SeatCount]tile.Seat {
	return rng.SeatPermutation(seed)
}

// DealRound returns the round seed deals as roundNumber with dealer dealing: its wall broken at the
// dice and dealt, as a game deals that round.
func DealRound(seed Seed, roundNumber uint32, dealer tile.Seat) play.RoundDeal {
	w := wall.FromSeed(seed, roundNumber, dealer)
	tiles := w.Tiles()
	live := w.LiveCount()
	deal := play.RoundDeal{
		Live:          tiles[:live:live],
		DeadWall:      tiles[live:],
		DoraIndicator: w.DoraIndicators()[0],
	}

	hands := w.Deal(dealer)
	for i := range hands {
		deal.Hands[i] = slices.Clone(hands[i][:])
	}

	deal.DealerDraw, _ = w.Draw()
	return deal
}

// Shanten returns how many tiles a closed hand is from ready, -1 once complete: the lowest over the
// regular, chiitoitsu and kokushi shapes, the last two counted only for a hand of 13 or 14 tiles.
// It returns an error for a tile count no hand holds: over 14, or a multiple of 3.
func Shanten(hand tile.Counts) (int, error) {
	return shanten.Lowest(hand)
}
