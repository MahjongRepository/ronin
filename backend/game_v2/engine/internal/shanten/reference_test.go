package shanten_test

import (
	"bufio"
	"compress/gzip"
	"os"
	"strconv"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/engine/internal/shanten"
	"github.com/MahjongRepository/ronin/backend/game_v2/engine/tile"
)

type referenceHand struct {
	counts     tile.Counts
	tiles      int
	lowest     int
	regular    int
	chiitoitsu int
	kokushi    int
}

func parseReferenceLine(t *testing.T, line string) referenceHand {
	t.Helper()
	fields := strings.Fields(line)
	if len(fields) != 5 || len(fields[0]) != tile.KindCount {
		t.Fatalf("reference line %q: want 34 count digits and 4 shanten", line)
	}

	var digits [tile.KindCount]uint8
	tiles := 0
	for kind, digit := range []byte(fields[0]) {
		digits[kind] = digit - '0'
		tiles += int(digits[kind])
	}
	counts, err := tile.CountsFromArray(digits)
	if err != nil {
		t.Fatalf("reference line %q: %v", line, err)
	}

	var values [4]int
	for i, field := range fields[1:] {
		values[i], err = strconv.Atoi(field)
		if err != nil {
			t.Fatalf("reference line %q: %v", line, err)
		}
	}
	return referenceHand{counts, tiles, values[0], values[1], values[2], values[3]}
}

func readReferenceSet(t *testing.T) []referenceHand {
	t.Helper()
	file, err := os.Open("testdata/reference.txt.gz")
	if err != nil {
		t.Fatalf("open reference set: %v", err)
	}
	t.Cleanup(func() { _ = file.Close() })
	unzipped, err := gzip.NewReader(file)
	if err != nil {
		t.Fatalf("read reference set: %v", err)
	}

	var hands []referenceHand
	scanner := bufio.NewScanner(unzipped)
	for scanner.Scan() {
		hands = append(hands, parseReferenceLine(t, scanner.Text()))
	}
	if err := scanner.Err(); err != nil {
		t.Fatalf("read reference set: %v", err)
	}
	if len(hands) == 0 {
		t.Fatal("reference set holds no hand")
	}
	return hands
}

func TestShanten_WhenHandIsInTheReferenceSet_ShouldMatchTheRecordedShanten(t *testing.T) {
	for _, hand := range readReferenceSet(t) {
		minimum := hand.regular
		if hand.tiles >= 13 {
			minimum = min(minimum, hand.chiitoitsu, hand.kokushi)
		}
		got, err := shanten.Lowest(hand.counts)
		if err != nil || got != hand.lowest || got != minimum {
			t.Errorf("Lowest(%v) = %d, %v, want %d, the minimum %d", hand.counts.Array(), got, err, hand.lowest, minimum)
		}
		if got := shanten.Chiitoitsu(hand.counts); got != hand.chiitoitsu {
			t.Errorf("Chiitoitsu(%v) = %d, want %d", hand.counts.Array(), got, hand.chiitoitsu)
		}
		if got := shanten.Kokushi(hand.counts); got != hand.kokushi {
			t.Errorf("Kokushi(%v) = %d, want %d", hand.counts.Array(), got, hand.kokushi)
		}
	}
}
