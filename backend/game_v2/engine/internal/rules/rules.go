package rules

import "github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"

const AkaDora = tile.AkaDoraEnabled

const (
	Hanchan               = true
	StartingScore         = 25000
	TargetScore           = 30000
	WinningScoreThreshold = 30000
	EnchousenSuddenDeath  = true
	Tobi                  = true
	TobiThreshold         = 0
)

const (
	Kuitan                 = true
	Ippatsu                = true
	UraDora                = true
	DoubleYakuman          = false
	KazoeYakuman           = true
	KiriageMangan          = false
	NagashiMangan          = true
	FuForOpenPinfu         = true
	FuForPinfuTsumo        = false
	Daisharin              = false
	DaisharinOtherSuits    = false
	Daichisei              = false
	LimitToSextupleYakuman = true
)

const (
	OmoteDora                    = true
	KanDora                      = true
	KanDoraImmediateForClosedKan = true
	KanDoraDeferredForOpenKan    = true
)

const (
	Kuikae        = true
	KuikaeSuji    = true
	MinWallForKan = 1
	MaxKans       = 4
)

const (
	Suukaikan             = true
	SuufonRenda           = true
	SuuchaRiichi          = true
	KyuushuKyuuhai        = true
	TripleRonAbort        = true
	KyuushuMinKinds       = 9
	MinPlayersForKanAbort = 2
	FourWindsDiscardCount = 4
)

const (
	DoubleRon              = true
	DoubleRonCount         = 2
	Agariyame              = true
	TieBreakBySeatOrder    = true
	LeftoverSticksToWinner = true
)

const (
	RiichiCost                    = 1000
	MinWallForRiichi              = 4
	RiichiStickValue              = 1000
	HonbaTsumoBonusPerLoser       = 100
	HonbaRonBonus                 = 300
	NotenPenaltyTotal             = 3000
	RenchanOnAbortiveDraw         = true
	RenchanOnDealerTenpaiDraw     = true
	RenchanOnDealerWin            = true
	NagashiManganDealerPayment    = 4000
	NagashiManganNonDealerPayment = 2000
)

const (
	DaisangenPao  = true
	DaisuushiiPao = true
)
