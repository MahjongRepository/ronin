// Package rules holds the fixed rules the engine plays by, the Tenhou preset, hanchan only, as
// scalars. Each constant replaces one field of ronin's GameSettings, named in its doc, and keeps
// its default value, except double yakuman, which follows Tenhou and is off. The constants that
// mahjong-rs derives from its hand-scoring rules or its scoring helpers are literals here; the
// hand-scoring rules themselves are built with scoring.
//
// Ported from the rules module of mahjong-rs's mahjong-game (rules::tenhou).
package rules

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

// AkaDora, has_akadora: the three red fives, ids 16, 52 and 88, are aka dora.
const AkaDora = tile.AkaDoraEnabled

const (
	// Hanchan, game_type = HANCHAN: a game plays the East and South winds.
	Hanchan = true
	// StartingScore, starting_score: every seat starts with this score.
	StartingScore = 25000
	// TargetScore, target_score: the return the final points and the oka are counted from.
	TargetScore = 30000
	// WinningScoreThreshold, winning_score_threshold: the score that ends the game after the last
	// South round, in the West extension and for agariyame.
	WinningScoreThreshold = 30000
	// EnchousenSuddenDeath, enchousen = SUDDEN_DEATH: below the threshold after South 4, play goes
	// on into West until a seat reaches it.
	EnchousenSuddenDeath = true
	// Tobi, tobi_enabled: the game ends when a seat's score falls below TobiThreshold.
	Tobi = true
	// TobiThreshold, tobi_threshold: a score below this ends the game.
	TobiThreshold = 0
)

const (
	// Kuitan, has_kuitan: tanyao counts on an open hand.
	Kuitan = true
	// Ippatsu, has_ippatsu.
	Ippatsu = true
	// UraDora, has_uradora: a riichi winner counts the ura dora.
	UraDora = true
	// DoubleYakuman, has_double_yakuman: off, unlike ronin; the double forms score as one yakuman.
	DoubleYakuman = false
	// KazoeYakuman, has_kazoe_yakuman: 13 han or more score as yakuman.
	KazoeYakuman = true
	// KiriageMangan, has_kiriage_mangan.
	KiriageMangan = false
	// NagashiMangan, has_nagashi_mangan.
	NagashiMangan = true
	// FuForOpenPinfu, fu_for_open_pinfu: an open hand with no other fu gets 2 fu.
	FuForOpenPinfu = true
	// FuForPinfuTsumo, fu_for_pinfu_tsumo: a pinfu tsumo gets no tsumo fu.
	FuForPinfuTsumo = false
	// Daisharin, has_daisharin.
	Daisharin = false
	// DaisharinOtherSuits, has_daisharin_other_suits.
	DaisharinOtherSuits = false
	// Daichisei, has_daichisei.
	Daichisei = false
	// LimitToSextupleYakuman, limit_to_sextuple_yakuman: a hand scores at most six yakuman.
	LimitToSextupleYakuman = true
)

const (
	// OmoteDora, has_omote_dora: the revealed indicators give dora.
	OmoteDora = true
	// KanDora, has_kandora: a kan reveals a new indicator.
	KanDora = true
	// KanDoraImmediateForClosedKan, kandora_immediate_for_closed_kan: a closed kan reveals at once.
	KanDoraImmediateForClosedKan = true
	// KanDoraDeferredForOpenKan, kandora_deferred_for_open_kan: an open or added kan reveals its
	// indicator after the caller's discard or the next kan.
	KanDoraDeferredForOpenKan = true
)

const (
	// Kuikae, has_kuikae: after a call the caller may not discard the called kind.
	Kuikae = true
	// KuikaeSuji, has_kuikae_suji: after a chi the caller may not discard the kind at the other end
	// of the sequence either.
	KuikaeSuji = true
	// MinWallForKan, min_wall_for_kan: a kan needs at least this many live tiles.
	MinWallForKan = 1
	// MaxKans, max_kans_per_round: the dead wall holds this many rinshan tiles.
	MaxKans = 4
)

const (
	// Suukaikan, has_suukaikan: four kans by more than one seat abort the round.
	Suukaikan = true
	// SuufonRenda, has_suufon_renda: four same winds as the first discards abort.
	SuufonRenda = true
	// SuuchaRiichi, has_suucha_riichi: four riichi abort.
	SuuchaRiichi = true
	// KyuushuKyuuhai, has_kyuushu_kyuuhai: a first-turn hand of enough terminal and honor kinds may
	// abort.
	KyuushuKyuuhai = true
	// TripleRonAbort, has_triple_ron_abort: three rons on one discard abort.
	TripleRonAbort = true
	// KyuushuMinKinds, kyuushu_min_types: the distinct terminal and honor kinds kyuushu needs.
	KyuushuMinKinds = 9
	// MinPlayersForKanAbort, min_players_for_kan_abort: suukaikan needs kans by this many seats.
	MinPlayersForKanAbort = 2
	// FourWindsDiscardCount, four_winds_discard_count: the first discards suufon renda looks at.
	FourWindsDiscardCount = 4
)

const (
	// DoubleRon, has_double_ron: two seats may ron one discard.
	DoubleRon = true
	// DoubleRonCount, double_ron_count: the most rons on one discard that all score.
	DoubleRonCount = 2
	// Agariyame, has_agariyame: from the last South round on, a dealer who wins or stays tenpai in
	// first place at the winning threshold ends the game.
	Agariyame = true
	// TieBreakBySeatOrder, tie_break_by_seat_order: equal final scores rank by seat order.
	TieBreakBySeatOrder = true
	// LeftoverSticksToWinner, leftover_riichi_bets = WINNER: riichi sticks left at the game's end
	// go to the first-placed seat.
	LeftoverSticksToWinner = true
)

const (
	// RiichiCost, riichi_cost: the points a riichi declaration deposits.
	RiichiCost = 1000
	// MinWallForRiichi, min_wall_for_riichi: riichi needs at least this many live tiles.
	MinWallForRiichi = 4
	// RiichiStickValue, riichi_stick_value: the points one riichi stick pays its taker.
	RiichiStickValue = 1000
	// HonbaTsumoBonusPerLoser, honba_tsumo_bonus_per_loser: what each tsumo payer adds per honba.
	HonbaTsumoBonusPerLoser = 100
	// HonbaRonBonus, honba_ron_bonus: what the discarder of a ron adds per honba.
	HonbaRonBonus = 300
	// NotenPenaltyTotal, noten_penalty_total: what the noten seats pay the tenpai seats in all at an
	// exhaustive draw.
	NotenPenaltyTotal = 3000
	// RenchanOnAbortiveDraw, renchan_on_abortive_draw: the dealer stays after an abortive draw.
	RenchanOnAbortiveDraw = true
	// RenchanOnDealerTenpaiDraw, renchan_on_dealer_tenpai_draw: the dealer stays after an
	// exhaustive draw in tenpai.
	RenchanOnDealerTenpaiDraw = true
	// RenchanOnDealerWin, renchan_on_dealer_win: the dealer stays after winning.
	RenchanOnDealerWin = true
	// NagashiManganDealerPayment, nagashi_mangan_dealer_payment: what the dealer pays a
	// non-dealer's nagashi mangan, and each seat pays the dealer's.
	NagashiManganDealerPayment = 4000
	// NagashiManganNonDealerPayment, nagashi_mangan_non_dealer_payment: what a non-dealer pays a
	// non-dealer's nagashi mangan.
	NagashiManganNonDealerPayment = 2000
)

const (
	// DaisangenPao, has_daisangen_pao: the seat that fed the third dragon pon pays for daisangen.
	DaisangenPao = true
	// DaisuushiiPao, has_daisuushii_pao: the seat that fed the fourth wind pon pays for daisuushii.
	DaisuushiiPao = true
)
