package wire

import "testing"

func TestKeyString_ShouldNameTheKeyAndAnAliasAsTheKeyItSharesANumberWith(t *testing.T) {
	tests := []struct {
		key  Key
		want string
	}{
		{KeyEventType, "EVENT_TYPE"},
		{KeyShownHands, "SHOWN_HANDS"},
		{KeyPaysHonba, "HONBA_BONUS"},
		{Key(keyCount), "Key(114)"},
	}
	for _, tc := range tests {
		t.Run(tc.want, func(t *testing.T) {
			if got := tc.key.String(); got != tc.want {
				t.Errorf("Key(%d).String() = %q, want %q", tc.key, got, tc.want)
			}
		})
	}
}
