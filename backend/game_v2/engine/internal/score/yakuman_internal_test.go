package score

import "testing"

func TestHasChuurenPoutouRanks_WhenRanksAreNotTheChuurenShape_ShouldReject(t *testing.T) {
	for _, mpsz := range []string{"111m234m567m899m9m", "11112233488999m", "11123444678999p", "111m1m22m345m678m999m"} {
		if hasChuurenPoutouRanks(countsOf(t, mpsz)) {
			t.Errorf("hasChuurenPoutouRanks(%s) = true, want false", mpsz)
		}
	}
}

func TestHasChuurenPoutouRanks_WhenEveryRankHoldsTheShapeAndOneMore_ShouldAccept(t *testing.T) {
	for _, mpsz := range []string{
		"11112345678999m",
		"11122345678999p",
		"11123345678999s",
		"11123445678999s",
		"11123455678999s",
		"11123456678999s",
		"11123456778999s",
		"11123456788999s",
		"11123456789999s",
	} {
		if !hasChuurenPoutouRanks(countsOf(t, mpsz)) {
			t.Errorf("hasChuurenPoutouRanks(%s) = false, want true", mpsz)
		}
	}
}

func TestHonorYakuman_WhenTheHandHoldsTheirSets_ShouldAccept(t *testing.T) {
	for _, tc := range []struct {
		name  string
		check func([34]uint8) bool
		mpsz  string
	}{
		{"isDaisangen", isDaisangen, "22m123s555666777z"},
		{"isShousuushii", isShousuushii, "123s11122233344z"},
		{"isDaisuushii", isDaisuushii, "22s111222333444z"},
		{"isKokushiMusou", isKokushiMusou, "19m19p119s1234567z"},
	} {
		if !tc.check(countsOf(t, tc.mpsz)) {
			t.Errorf("%s(%s) = false, want true", tc.name, tc.mpsz)
		}
	}
}

func TestTileYakuman_ShouldAcceptOnlyWhenEveryKindFits(t *testing.T) {
	for _, tc := range []struct {
		name  string
		check func(uint64) bool
		mpsz  string
		want  bool
	}{
		{"isTsuuiisou", isTsuuiisou, "11122233366677z", true},
		{"isTsuuiisou", isTsuuiisou, "11223344556677z", true},
		{"isTsuuiisou", isTsuuiisou, "88p11s1133445577z", false},
		{"isChinroutou", isChinroutou, "111999m99p111999s", true},
		{"isRyuuiisou", isRyuuiisou, "22334466888s666z", true},
	} {
		if got := tc.check(kindsOf(t, tc.mpsz)); got != tc.want {
			t.Errorf("%s(%s) = %v, want %v", tc.name, tc.mpsz, got, tc.want)
		}
	}
}

func TestIsKokushiMusou_WhenTheHandHoldsMoreOrFewerThanTheThirteenOrphansAndOnePair_ShouldReject(t *testing.T) {
	for _, mpsz := range []string{
		"12349m19p119s1234567z",
		"122229m19p119s1234567z",
		"1559m19p119s1234567z",
		"19m19p19s1234567z",
		"11m19p119s1234567z",
	} {
		if isKokushiMusou(countsOf(t, mpsz)) {
			t.Errorf("isKokushiMusou(%s) = true, want false", mpsz)
		}
	}
}
