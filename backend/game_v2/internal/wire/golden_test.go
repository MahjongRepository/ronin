package wire

import (
	"bytes"
	"encoding/hex"
	"flag"
	"reflect"
	"testing"
)

var update = flag.Bool("update", false, "rewrite the goldens' bytes and named keys from their payloads")

const (
	liveGoldenPath         = "testdata/live-protocol-golden.json"
	replayGoldenPath       = "testdata/replay-format-golden.json"
	pythonLiveGoldenPath   = "../../../game/tests/fixtures/live-protocol-golden.json"
	pythonReplayGoldenPath = "../../../game/tests/fixtures/replay-format-golden.json"
)

func goldenBytes(tb testing.TB, node any) []byte {
	tb.Helper()
	text, _ := node.(string)
	content, err := hex.DecodeString(text)
	if err != nil {
		tb.Fatalf("hex %q: %v", text, err)
	}
	return content
}

func goldenFrames(tb testing.TB, golden jsonObject) []jsonObject {
	tb.Helper()
	nodes, _ := golden.get("frames").([]any)
	frames := make([]jsonObject, 0, len(nodes))
	for _, node := range nodes {
		frame, ok := node.(jsonObject)
		if !ok {
			tb.Fatalf("frame %v is no object", node)
		}
		frames = append(frames, frame)
	}
	return frames
}

func goldenRecords(t *testing.T, golden jsonObject) []Map {
	t.Helper()
	nodes, _ := golden.get("records").([]any)
	records := make([]Map, 0, len(nodes))
	for _, node := range nodes {
		records = append(records, wireRecordOf(t, node))
	}
	return records
}

func TestLiveGolden_ShouldEncodeAndDecodeEveryFrameByteForByte(t *testing.T) {
	golden := readJSONFile(t, liveGoldenPath)
	frames := goldenFrames(t, golden)

	if *update {
		updated := make([]any, 0, len(frames))
		for _, frame := range frames {
			payload := wireRecordOf(t, frame.get("payload"))
			content, err := Encode(payload)
			if err != nil {
				t.Fatalf("encode frame %v: %v", frame.get("name"), err)
			}
			updated = append(updated, frame.with("hex", hex.EncodeToString(content)))
		}
		golden = golden.with("frames", updated).with("named_keys", namedKeys(&liveKeys))
		writeJSONFile(t, liveGoldenPath, golden)
		frames = goldenFrames(t, golden)
	}

	for _, frame := range frames {
		payload := wireRecordOf(t, frame.get("payload"))
		want := goldenBytes(t, frame.get("hex"))
		content, err := Encode(payload)
		if err != nil || !bytes.Equal(content, want) {
			t.Errorf("Encode(%v) = %x, %v; want %x", frame.get("name"), content, err, want)
		}
		decoded, err := Decode(want)
		if err != nil || !reflect.DeepEqual(decoded, payload) {
			t.Errorf("Decode(%v) = %v, %v; want %v", frame.get("name"), decoded, err, payload)
		}
	}
	if names := golden.get("named_keys"); !reflect.DeepEqual(names, namedKeys(&liveKeys)) {
		t.Errorf("named_keys = %v, want %v", names, namedKeys(&liveKeys))
	}
}

func TestReplayGolden_ShouldEncodeAndDecodeTheRecordsByteForByte(t *testing.T) {
	golden := readJSONFile(t, replayGoldenPath)
	records := goldenRecords(t, golden)

	if *update {
		content, err := EncodeReplay(records)
		if err != nil {
			t.Fatalf("encode records: %v", err)
		}
		golden = golden.with("hex", hex.EncodeToString(content)).with("named_keys", namedKeys(&replayKeys))
		writeJSONFile(t, replayGoldenPath, golden)
	}

	want := goldenBytes(t, golden.get("hex"))
	content, err := EncodeReplay(records)
	if err != nil || !bytes.Equal(content, want) {
		t.Errorf("EncodeReplay = %x, %v; want %x", content, err, want)
	}
	decoded, err := DecodeReplay(want)
	if err != nil || !reflect.DeepEqual(decoded, records) {
		t.Errorf("DecodeReplay = %v, %v; want %v", decoded, err, records)
	}
	if names := golden.get("named_keys"); !reflect.DeepEqual(names, namedKeys(&replayKeys)) {
		t.Errorf("named_keys = %v, want %v", names, namedKeys(&replayKeys))
	}
}

func TestLiveGolden_WhenAPythonFrameKeepsItsShape_ShouldEncodeToThePythonBytes(t *testing.T) {
	goFrames := map[string]jsonObject{}
	for _, frame := range goldenFrames(t, readJSONFile(t, liveGoldenPath)) {
		name, _ := frame.get("name").(string)
		goFrames[name] = frame
	}

	var reshaped []string
	for _, frame := range goldenFrames(t, readJSONFile(t, pythonLiveGoldenPath)) {
		name, _ := frame.get("name").(string)
		pythonBytes := goldenBytes(t, frame.get("hex"))
		decoded, err := Decode(pythonBytes)
		if err != nil {
			t.Errorf("Decode(python %s): %v", name, err)
			continue
		}
		content, err := Encode(decoded)
		if err != nil || !bytes.Equal(content, pythonBytes) {
			t.Errorf("Encode(Decode(python %s)) = %x, %v; want %x", name, content, err, pythonBytes)
		}

		goFrame, ok := goFrames[name]
		if !ok || !reflect.DeepEqual(wireRecordOf(t, goFrame.get("payload")), decoded) {
			reshaped = append(reshaped, name)
			continue
		}
		if goBytes := goldenBytes(t, goFrame.get("hex")); !bytes.Equal(goBytes, pythonBytes) {
			t.Errorf("go golden %s = %x, want the python bytes %x", name, goBytes, pythonBytes)
		}
	}

	if !reflect.DeepEqual(reshaped, []string{"snapshot"}) {
		t.Errorf("frames whose shape changed = %v, want only the snapshot's double ron", reshaped)
	}
}

func TestReplayGolden_WhenPythonRecordsKeepTheirShape_ShouldEncodeToThePythonBytesPastTheVersion(t *testing.T) {
	python := readJSONFile(t, pythonReplayGoldenPath)
	records := goldenRecords(t, python)
	pythonBytes := goldenBytes(t, python.get("hex"))
	pythonVersion := appendValue(nil, records[0])

	records[0] = VersionRecord()
	content, err := EncodeReplay(records)
	if err != nil {
		t.Fatalf("EncodeReplay(python records): %v", err)
	}

	goVersion := appendValue(nil, VersionRecord())
	if !bytes.Equal(content[len(goVersion):], pythonBytes[len(pythonVersion):]) {
		t.Errorf("records past the version = %x, want the python bytes %x", content[len(goVersion):],
			pythonBytes[len(pythonVersion):])
	}
}
