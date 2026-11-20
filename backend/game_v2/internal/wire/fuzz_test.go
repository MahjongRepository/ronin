package wire

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
)

const rewrittenReplaysDir = "testdata/rewritten"

func addFrameSeeds(f *testing.F, goldenPath string) {
	f.Helper()
	for _, frame := range goldenFrames(f, readJSONFile(f, goldenPath)) {
		f.Add(goldenBytes(f, frame.get("hex")))
	}
}

func addReplaySeeds(f *testing.F) {
	f.Helper()
	for _, goldenPath := range []string{replayGoldenPath, pythonReplayGoldenPath} {
		f.Add(goldenBytes(f, readJSONFile(f, goldenPath).get("hex")))
	}

	entries, err := os.ReadDir(rewrittenReplaysDir)
	if err != nil {
		f.Fatalf("read %s: %v", rewrittenReplaysDir, err)
	}
	for _, entry := range entries {
		content, readErr := os.ReadFile(filepath.Join(rewrittenReplaysDir, entry.Name()))
		if readErr != nil {
			f.Fatalf("read %s: %v", entry.Name(), readErr)
		}
		f.Add(content)
	}
}

func FuzzDecode_WhenItAcceptsAMessage_ShouldReencodeItToStableBytes(f *testing.F) {
	addFrameSeeds(f, liveGoldenPath)
	addFrameSeeds(f, pythonLiveGoldenPath)

	f.Fuzz(func(t *testing.T, data []byte) {
		message, err := Decode(data)
		if err != nil {
			return
		}

		content, err := Encode(message)
		if err != nil {
			t.Fatalf("Encode(Decode(%x)): %v", data, err)
		}
		if len(content) > MaxMessageBytes {
			return
		}
		again, err := Decode(content)
		if err != nil {
			t.Fatalf("Decode(Encode(Decode(%x))): %v", data, err)
		}
		reencoded, err := Encode(again)
		if err != nil || !bytes.Equal(reencoded, content) {
			t.Fatalf("Encode(Decode(%x)) = %x, %v; want %x", content, reencoded, err, content)
		}
	})
}

func FuzzDecodeReplay_WhenItAcceptsAReplay_ShouldReencodeItToStableBytes(f *testing.F) {
	addReplaySeeds(f)

	f.Fuzz(func(t *testing.T, data []byte) {
		records, err := DecodeReplay(data)
		if err != nil {
			return
		}

		content, err := EncodeReplay(records)
		if err != nil {
			t.Fatalf("EncodeReplay(DecodeReplay(%x)): %v", data, err)
		}
		again, err := DecodeReplay(content)
		if err != nil {
			t.Fatalf("DecodeReplay(EncodeReplay(DecodeReplay(%x))): %v", data, err)
		}
		reencoded, err := EncodeReplay(again)
		if err != nil || !bytes.Equal(reencoded, content) {
			t.Fatalf("EncodeReplay(DecodeReplay(%x)) = %x, %v; want %x", content, reencoded, err, content)
		}
	})
}
