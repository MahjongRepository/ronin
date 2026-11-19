package play

import "strconv"

// Value is the han and fu of a hand, or how many yakuman it is: Han or Yakuman. Its String is
// "3 han, 30 fu", "yakuman" or "2x yakuman".
//
//sumtype:decl
type Value interface {
	isValue()
	String() string
}

// Han is a hand's han and its fu, rounded as the payment uses them. 13 han and up without a
// yakuman is a counted (kazoe) yakuman, paid as a single yakuman.
type Han struct {
	Han int
	Fu  int
}

// Yakuman is Count yakuman, 1 to 6, a double yakuman counting 2; Fu is the reading's rounded fu,
// absent for kokushi musou.
type Yakuman struct {
	Count int
	Fu    Option[int]
}

func (Han) isValue()     {}
func (Yakuman) isValue() {}

// String returns v as "3 han, 30 fu".
func (v Han) String() string {
	return strconv.Itoa(v.Han) + " han, " + strconv.Itoa(v.Fu) + " fu"
}

// String returns v as "yakuman", or "2x yakuman" for more than one.
func (v Yakuman) String() string {
	if v.Count == 1 {
		return "yakuman"
	}
	return strconv.Itoa(v.Count) + "x yakuman"
}

// Limit is one of the fixed payments from mangan up: mangan (5 han, fewer han whose base points
// reach the mangan cap, or with kiriage 4 han 30 fu and 3 han 60 fu), haneman (6-7 han), baiman
// (8-10 han), sanbaiman (11-12 han) and yakuman (13 han and up, or any number of yakuman).
type Limit uint8

// The limits.
const (
	LimitMangan Limit = iota
	LimitHaneman
	LimitBaiman
	LimitSanbaiman
	LimitYakuman
)

// String names l: "mangan", "haneman", "baiman", "sanbaiman" or "yakuman".
func (l Limit) String() string {
	switch l {
	case LimitMangan:
		return "mangan"
	case LimitHaneman:
		return "haneman"
	case LimitBaiman:
		return "baiman"
	case LimitSanbaiman:
		return "sanbaiman"
	case LimitYakuman:
		return "yakuman"
	default:
		return "play.Limit(" + strconv.Itoa(int(l)) + ")"
	}
}

// TenhouCode returns the limit code of Tenhou's AGARI ten, 1 for mangan to 5 for yakuman; a win
// below mangan has code 0.
func (l Limit) TenhouCode() int {
	return int(l) + 1
}

// UnknownLimitCodeError reports a Tenhou ten limit code above 5.
type UnknownLimitCodeError struct {
	Code int
}

func (e UnknownLimitCodeError) Error() string {
	return "no Tenhou limit has code " + strconv.Itoa(e.Code)
}

// LimitFromTenhouCode returns the limit of a Tenhou ten limit code, absent for 0, a win below
// mangan; an UnknownLimitCodeError for any code but 0 to 5.
func LimitFromTenhouCode(code int) (Option[Limit], error) {
	if code < 0 || code > LimitYakuman.TenhouCode() {
		return Option[Limit]{}, UnknownLimitCodeError{Code: code}
	}
	if code == 0 {
		return Option[Limit]{}, nil
	}
	return Some(Limit(code - 1)), nil
}

// Payment is who pays the winner how much, honba included and riichi sticks not: RonPayment,
// TsumoPayment or DealerTsumoPayment.
//
//sumtype:decl
type Payment interface {
	isPayment()
	Sum() int
}

// RonPayment is a ron: the player who dealt in pays it all.
type RonPayment struct {
	Discarder int
}

// TsumoPayment is a non-dealer's tsumo: the dealer pays Dealer, the two other players NonDealer
// each.
type TsumoPayment struct {
	Dealer    int
	NonDealer int
}

// DealerTsumoPayment is the dealer's tsumo: the three other players pay NonDealer each.
type DealerTsumoPayment struct {
	NonDealer int
}

func (RonPayment) isPayment()         {}
func (TsumoPayment) isPayment()       {}
func (DealerTsumoPayment) isPayment() {}

// Sum returns what the discarder pays.
func (p RonPayment) Sum() int {
	return p.Discarder
}

// Sum returns what the three payers pay together.
func (p TsumoPayment) Sum() int {
	return p.Dealer + 2*p.NonDealer
}

// Sum returns what the three payers pay together.
func (p DealerTsumoPayment) Sum() int {
	return 3 * p.NonDealer
}

// DoraCount is the dora a hand scored, all 0 for a yakuman; UraDora counts only with a riichi.
type DoraCount struct {
	Dora    int
	AkaDora int
	UraDora int
}

// Riichi is a riichi in effect: Double when declared on the first discard before any call
// (daburu riichi), Ippatsu while a win within one go-around of it, with no call in between, would
// still score ippatsu.
type Riichi struct {
	Double  bool
	Ippatsu bool
}
