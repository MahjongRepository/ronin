package replayfile_test

import (
	"bytes"
	"compress/gzip"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/MahjongRepository/ronin/backend/game_v2/internal/replayfile"
)

func decompress(t *testing.T, compressed []byte) []byte {
	t.Helper()
	reader, err := gzip.NewReader(bytes.NewReader(compressed))
	if err != nil {
		t.Fatalf("gzip header: %v", err)
	}

	content, err := io.ReadAll(reader)
	if err != nil {
		t.Fatalf("gunzip: %v", err)
	}

	return content
}

func assertMode(t *testing.T, path string, want fs.FileMode) {
	t.Helper()
	info, err := os.Stat(path)
	if err != nil || info.Mode().Perm() != want {
		t.Errorf("%s mode = %v, %v; want %v", path, info, err, want)
	}
}

func TestDirSave_WhenGivenAReplay_ShouldStoreItGzippedInOwnerOnlyShards(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "replays")
	err := os.Mkdir(dir, 0o755)
	if err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	replays := replayfile.New(dir)
	content := []byte("encoded replay records")

	err = replays.Save("abcd-game_1", content)
	if err != nil {
		t.Fatalf("Save: %v", err)
	}

	file := filepath.Join(dir, "ab", "cd", "abcd-game_1.msgpack.gz")
	stored, err := os.ReadFile(file)
	if err != nil {
		t.Fatalf("read stored replay: %v", err)
	}

	if got := decompress(t, stored); !bytes.Equal(got, content) {
		t.Errorf("stored replay = %q, want %q", got, content)
	}

	assertMode(t, file, 0o600)
	for _, d := range []string{dir, filepath.Join(dir, "ab"), filepath.Join(dir, "ab", "cd")} {
		assertMode(t, d, 0o700)
	}

	entries, err := os.ReadDir(filepath.Join(dir, "ab", "cd"))
	if err != nil || len(entries) != 1 {
		t.Errorf("shard entries = %v, %v; want only the replay", entries, err)
	}

	read, err := replays.Read("abcd-game_1")
	if err != nil || !bytes.Equal(read, stored) {
		t.Errorf("Read = %d bytes, %v; want the %d stored bytes", len(read), err, len(stored))
	}

	if got, decompressErr := replayfile.Decompress(read, len(content)); decompressErr != nil || !bytes.Equal(got, content) {
		t.Errorf("Decompress = %q, %v; want %q", got, decompressErr, content)
	}
}

func TestDecompress_WhenTheContentIsOverTheLimit_ShouldReadOneBytePastIt(t *testing.T) {
	replays := replayfile.New(t.TempDir())
	err := replays.Save("game-1", []byte("0123456789"))
	if err != nil {
		t.Fatalf("Save: %v", err)
	}

	read, err := replays.Read("game-1")
	if err != nil {
		t.Fatalf("Read: %v", err)
	}

	got, err := replayfile.Decompress(read, 4)
	if err != nil || string(got) != "01234" {
		t.Errorf("Decompress = %q, %v; want the limit and one byte more", got, err)
	}
}

func TestDirSave_WhenTheGameHasAReplay_ShouldReplaceIt(t *testing.T) {
	replays := replayfile.New(t.TempDir())
	err := errors.Join(replays.Save("game-1", []byte("first")), replays.Save("game-1", []byte("second")))
	if err != nil {
		t.Fatalf("Save: %v", err)
	}

	read, err := replays.Read("game-1")
	if err != nil {
		t.Fatalf("Read: %v", err)
	}

	if got := decompress(t, read); string(got) != "second" {
		t.Errorf("stored replay = %q, want the second", got)
	}

	if want := freshBestCompression(t, []byte("second")); !bytes.Equal(read, want) {
		t.Errorf("stored replay = %x, want the bytes of a fresh best-compression writer %x", read, want)
	}
}

func freshBestCompression(t *testing.T, content []byte) []byte {
	t.Helper()
	var compressed bytes.Buffer
	writer, err := gzip.NewWriterLevel(&compressed, gzip.BestCompression)
	if err == nil {
		_, err = writer.Write(content)
	}

	if err == nil {
		err = writer.Close()
	}

	if err != nil {
		t.Fatalf("gzip: %v", err)
	}

	return compressed.Bytes()
}

func TestDir_WhenTheGameIDCannotNameAReplay_ShouldRefuseIt(t *testing.T) {
	replays := replayfile.New(t.TempDir())
	for _, id := range []string{"abc", strings.Repeat("a", 51), "ab/cd", "../../etc", "abcd\n", "abcd.e", "абвг"} {
		saveErr := replays.Save(id, []byte("x"))
		_, readErr := replays.Read(id)
		if !errors.Is(saveErr, replayfile.ErrInvalidGameID) || !errors.Is(readErr, replayfile.ErrInvalidGameID) {
			t.Errorf("%q: Save, Read errors = %v, %v; want %v", id, saveErr, readErr, replayfile.ErrInvalidGameID)
		}
	}
}

func TestDirRead_WhenTheFileIsOverTheCap_ShouldRefuseIt(t *testing.T) {
	dir := t.TempDir()
	shard := filepath.Join(dir, "at", "ca")
	err := os.MkdirAll(shard, 0o700)
	if err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	for name, size := range map[string]int{"atcap": replayfile.MaxFileSize, "atcapplus1": replayfile.MaxFileSize + 1} {
		err = os.WriteFile(filepath.Join(shard, name+".msgpack.gz"), make([]byte, size), 0o600)
		if err != nil {
			t.Fatalf("write %s: %v", name, err)
		}
	}

	replays := replayfile.New(dir)

	atCap, err := replays.Read("atcap")
	if err != nil || len(atCap) != replayfile.MaxFileSize {
		t.Errorf("Read at the cap = %d bytes, %v; want %d", len(atCap), err, replayfile.MaxFileSize)
	}

	_, err = replays.Read("atcapplus1")
	if !errors.Is(err, replayfile.ErrTooLarge) {
		t.Errorf("Read over the cap error = %v, want %v", err, replayfile.ErrTooLarge)
	}
}

func TestDir_WhenALinkLeadsOutOfTheDirectory_ShouldNotFollowIt(t *testing.T) {
	dir, outside := t.TempDir(), t.TempDir()
	err := os.WriteFile(filepath.Join(outside, "game-1.msgpack.gz"), []byte("outside"), 0o600)
	if err != nil {
		t.Fatalf("write outside: %v", err)
	}

	err = os.Mkdir(filepath.Join(dir, "ga"), 0o700)
	if err != nil {
		t.Fatalf("mkdir: %v", err)
	}

	err = os.Symlink(outside, filepath.Join(dir, "ga", "me"))
	if err != nil {
		t.Fatalf("symlink: %v", err)
	}

	replays := replayfile.New(dir)

	_, readErr := replays.Read("game-1")
	saveErr := replays.Save("game-2", []byte("x"))
	if readErr == nil || saveErr == nil {
		t.Errorf("Read, Save errors = %v, %v; want both refused", readErr, saveErr)
	}

	entries, err := os.ReadDir(outside)
	if err != nil || len(entries) != 1 {
		t.Errorf("outside entries = %v, %v; want only its own file", entries, err)
	}
}

func TestDirRead_WhenNoReplayIsStored_ShouldAnswerNotExist(t *testing.T) {
	for _, dir := range []string{t.TempDir(), filepath.Join(t.TempDir(), "missing")} {
		_, err := replayfile.New(dir).Read("abcd-1")
		if !errors.Is(err, fs.ErrNotExist) {
			t.Errorf("%s: Read error = %v, want %v", dir, err, fs.ErrNotExist)
		}
	}
}
