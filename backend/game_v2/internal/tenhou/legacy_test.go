package tenhou

import (
	"errors"
	"os"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/wire"
)

const (
	rewrittenChankanPath = "../wire/testdata/rewritten/chankan_added.msgpack"
	pythonChankanExport  = `<mjloggm ver="2.3">` +
		`<SHUFFLE seed="555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555` +
		`555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555555" ref="shake256-v1"/>` +
		`<GO type="9" lobby="0"/>` +
		`<UN n0="Diana" n1="Alice" n2="Charlie" n3="Bob" dan="0,0,0,0" rate="1500.00,1500.00,1500.00,1500.00" sx="M,M,M,M"/>` +
		`<TAIKYOKU oya="0"/>` +
		`<INIT seed="0,0,0,1,1,112" ten="250,250,250,250" oya="0" hai0="6,18,30,38,58,62,82,94,106,110,114,118,122"` +
		` hai1="1,13,25,37,56,57,69,77,89,101,109,113,117" hai2="0,4,8,12,16,20,24,28,32,48,52,72,104"` +
		` hai3="7,19,31,39,63,83,95,107,111,115,119,123,127"/>` +
		`<T132/><D58/><N who="1" m="22635" /><E109/><V73/><F104/><W133/><G133/><T134/><D134/><U59/>` +
		`<N who="1" m="22643" />` +
		`<AGARI ba="0,0" hai="0,4,8,12,16,20,24,28,32,48,52,59,72,73" machi="59" ten="30,12000,2"` +
		` yaku="3,1,7,1,24,2,54,2" doraHai="112" who="2" fromWho="1" sc="250,0,250,-120,250,120,250,0" />`
)

func TestConvertEvents_WhenTheRewrittenChankanReplayConverts_ShouldWriteThePythonExportOfTheOriginal(t *testing.T) {
	content, err := os.ReadFile(rewrittenChankanPath)
	if err != nil {
		t.Fatalf("read %s: %v", rewrittenChankanPath, err)
	}
	records, err := wire.DecodeReplay(content)
	if err != nil {
		t.Fatalf("DecodeReplay error = %v", err)
	}

	got, err := convertEvents(records[1:])
	if err != nil {
		t.Fatalf("convertEvents error = %v", err)
	}
	if got != pythonChankanExport {
		t.Errorf("convertEvents =\n%s\nwant the Python export\n%s", got, pythonChankanExport)
	}

	if _, err := Convert(content); !errors.Is(err, ErrNoGameEnd) {
		t.Errorf("Convert error = %v, want ErrNoGameEnd", err)
	}
}
