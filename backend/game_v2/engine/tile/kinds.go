package tile

import (
	"iter"
	"math/bits"
)

// Kinds is a set of kinds. Its zero value is the empty set.
type Kinds struct {
	bits uint64
}

// KindsFromBits returns the set of the kinds whose bits are set, kind 0 the lowest bit.
func KindsFromBits(mask uint64) Kinds {
	return Kinds{bits: mask}
}

// Contains reports whether kind is in k.
func (k Kinds) Contains(kind Kind) bool {
	return k.bits>>kind&1 == 1
}

// IsEmpty reports whether k holds no kind.
func (k Kinds) IsEmpty() bool {
	return k.bits == 0
}

// Len returns how many kinds are in k.
func (k Kinds) Len() int {
	return bits.OnesCount64(k.bits)
}

// All yields the kinds in k, lowest first.
func (k Kinds) All() iter.Seq[Kind] {
	return func(yield func(Kind) bool) {
		for rest := k.bits; rest != 0; rest &= rest - 1 {
			if !yield(Kind(bits.TrailingZeros64(rest))) {
				return
			}
		}
	}
}

// With returns k with kind added.
func (k Kinds) With(kind Kind) Kinds {
	return Kinds{bits: k.bits | 1<<kind}
}

// Difference returns the kinds of k that are not in other.
func (k Kinds) Difference(other Kinds) Kinds {
	return Kinds{bits: k.bits &^ other.bits}
}
