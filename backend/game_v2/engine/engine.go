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
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/meld"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/offer"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/record"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rng"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/rules"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/score"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/shanten"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/wall"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/play"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

// Setup is everything a game is built from: where its walls come from, and the position it starts
// at, absent for East 1 with every seat at the starting score.
type Setup struct {
	Walls play.WallSource
	Start play.Option[play.StartPosition]
}

// Game is the full state of a game, held by its caller. Its zero value is not a game and must not
// be played or read; build one with NewGame.
type Game struct {
	game game.Game
}

// NewGame sets a game up and deals its first round. It returns the game, awaiting
// play.AwaitingDealt, and its first events: GameStarted, then one RoundStarted per seat; Begin
// makes the dealer's first draw. A play.Fixed source deals seat 0 first with every throw (1, 1)
// and ends the game with play.EndFixedWallsDealt once its walls run out.
//
// The errors, checked in this order: the start position's StartInNorthError,
// StartScoreOffHundredsError, StartScoreBelowTobiError, NegativeStartCountError and
// StartPointsOffTotalError; an InvalidWallError for a fixed wall that repeats a tile; a
// NoFixedWallError for an empty Fixed list or a nil source.
func NewGame(setup Setup) (Game, []play.Emitted, error) {
	g, events, err := game.New(setup.Walls, setup.Start)
	if err != nil {
		return Game{}, nil, err
	}
	return Game{game: g}, detachFreshEvents(events), nil
}

// Act applies one answer of seat and returns the game after it and the events it caused. A
// refusal returns the receiver unchanged and no events: not awaited outside a round in play or
// while it awaits play.AwaitingDealt, from a seat not awaited, for a turn action while a call
// prompt is open and for a call answer outside one; not offered for a tile the seat does not hold
// or an action it was not offered; rule for a riichi discard that breaks tenpai, a discard in
// riichi other than the drawn tile and a discard kuikae forbids.
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

// LegalActions returns every action seat may take now, none for a seat the game does not await.
// On a turn the discards come first in hand order, then the riichi discards, tsumo, the closed
// kans, the added kans and kyuushu; on a call prompt ron, open kan, the pons, the chis, then pass.
func (g Game) LegalActions(seat tile.Seat) []play.Action {
	return g.game.LegalActions(seat)
}

// DefaultAction returns the action a timeout plays for seat: on a turn the drawn tile when it is
// a legal discard, else the last legal discard; on a call prompt pass. False for a seat the game
// does not await.
func (g Game) DefaultAction(seat tile.Seat) (play.Action, bool) {
	return g.game.DefaultAction(seat)
}

// View returns what seat may see of the game now: the facts it knows, which its visible events
// alone rebuild, and its decision when the game awaits it. It holds no other seat's concealed
// tiles, decision, furiten or pending answer.
func (g Game) View(seat tile.Seat) play.SeatView {
	return g.game.SeatView(seat)
}

// Standings returns the final standings once the game is over.
func (g Game) Standings() play.Option[play.Standings] {
	return g.game.Standings()
}

// CheckInvariants checks what every step of a game keeps: each of the 136 tiles in exactly one
// place, the scores and riichi sticks adding up to the points the game started with, and once the
// game is over final scores that add up to them too, points that sum to 0 and the places 1 to 4.
// The first broken one is returned, in that order: an OwnershipError, TablePointsError,
// FinalScoresError, FinalPointsError or PlacementsError.
func (g Game) CheckInvariants() error {
	return g.game.CheckInvariants()
}

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

// SeedBytes is the size of a seed; its hex form is twice as many characters.
const SeedBytes = rng.SeedBytes

// RiichiStickValue is the points one riichi stick on the table pays the winner who takes it.
const RiichiStickValue = rules.RiichiStickValue

// HonbaRonBonus is what a win adds per honba in all: a ron's discarder pays it, a tsumo's three
// payers a third each.
const HonbaRonBonus = rules.HonbaRonBonus

// RNGVersion is the name of the randomness scheme that turns a seed into a game, as ronin writes
// it into its replays.
const RNGVersion = rng.Version

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

// Table is the round a win is settled in: its dealer, its round wind, and the honba and riichi
// sticks on the table.
type Table struct {
	Dealer       tile.Seat
	RoundWind    tile.Wind
	Honba        int
	RiichiSticks int
}

// WinningHand is one winner's hand to settle: the winner's seat, the concealed tiles without the
// winning tile, the winning tile, the declared melds, the dora and ura dora indicators, how the
// tile came, the winner's riichi, absent without one, whether the win comes before the winner's
// first discard with no call made, and the seat liable for the yakuman, absent without one.
type WinningHand struct {
	Seat           tile.Seat
	Concealed      []tile.TileID
	WinTile        tile.TileID
	Melds          []play.MeldView
	DoraIndicators []tile.TileID
	UraIndicators  []tile.TileID
	Win            Win
	Riichi         play.Option[play.Riichi]
	FirstTurn      bool
	Pao            play.Option[tile.Seat]
}

// Win is how the winning tile came.
type Win = score.Win

// The wins.
const (
	WinRon     = score.WinRon
	WinChankan = score.WinChankan
	WinHoutei  = score.WinHoutei
	WinTsumo   = score.WinTsumo
	WinRinshan = score.WinRinshan
	WinHaitei  = score.WinHaitei
)

// HandValue is the value of a winning hand's most expensive reading, scored with no honba and no
// riichi sticks.
type HandValue = score.HandValue

// SettledWin is a win as a game settles it: the hand's value and what the win moves by seat, the
// table's honba and riichi sticks included.
type SettledWin struct {
	Value        HandValue
	ScoreChanges [tile.SeatCount]int
}

// MisfitMeldError reports a meld whose tiles do not fit its kind.
type MisfitMeldError = meld.MisfitMeldError

// MisfitWinError reports a win settled as the other kind.
type MisfitWinError = offer.MisfitWinError

// SettleTsumo settles a tsumo as a game does, by the engine's rules and with its aka dora: the
// winner's seat wind from the dealer, the hand scored, and the payment, the table's honba and
// riichi sticks charged and paid, all of it to a liable seat. It returns a MisfitWinError for a
// ron, a MisfitMeldError, or the scorer's errors: a wrong tile count, a fifth copy of a kind, a
// situation the hand cannot have, a hand that is not complete, or one with no yaku.
func SettleTsumo(table Table, h WinningHand) (SettledWin, error) {
	if !h.Win.IsTsumo() {
		return SettledWin{}, MisfitWinError{Win: h.Win}
	}
	value, err := settledValue(table, h)
	if err != nil {
		return SettledWin{}, err
	}

	changes := offer.TsumoScoreChanges(h.Seat, table.Dealer, value.Payment, table.Honba, table.RiichiSticks, h.Pao)
	return SettledWin{Value: value, ScoreChanges: changes}, nil
}

// SettleRon settles the winners of one ron on discarder's tile as a game does, in the order given,
// which a game sets from the discarder's next seat on: the first winner takes the table's honba
// and riichi sticks, and a liable seat other than the discarder pays half of a hand and its honba.
// It returns SettleTsumo's errors for the first winner that has one, a MisfitWinError for a
// tsumo.
func SettleRon(table Table, discarder tile.Seat, winners []WinningHand) ([]SettledWin, error) {
	settled := make([]SettledWin, 0, len(winners))
	for position, h := range winners {
		if h.Win.IsTsumo() {
			return nil, MisfitWinError{Win: h.Win}
		}
		value, err := settledValue(table, h)
		if err != nil {
			return nil, err
		}

		honba, sticks := offer.RonTableShare(position, table.Honba, table.RiichiSticks)
		changes := offer.RonScoreChanges(h.Seat, discarder, value.Payment, honba, sticks, h.Pao)
		settled = append(settled, SettledWin{Value: value, ScoreChanges: changes})
	}
	return settled, nil
}

func settledValue(table Table, h WinningHand) (HandValue, error) {
	situation := offer.BaseSituation(h.Win, h.Seat.Wind(table.Dealer), table.RoundWind, h.Riichi)
	situation.FirstTurn = h.FirstTurn
	return offer.HandValue(h.Concealed, h.WinTile, offer.Scoring{
		Situation:      situation,
		Melds:          h.Melds,
		DoraIndicators: h.DoraIndicators,
		UraIndicators:  h.UraIndicators,
	})
}

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
