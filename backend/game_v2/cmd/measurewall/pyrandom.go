package main

import (
	"crypto/sha512"
	"encoding/binary"
	"math/bits"
	"slices"
)

const (
	mtStateWords   = 624
	mtShiftWords   = 397
	mtMatrixA      = 0x9908b0df
	mtUpperMask    = 0x80000000
	mtLowerMask    = 0x7fffffff
	mtGenrandSeed  = 19650218
	mtInitFactor   = 1812433253
	mtArrayFactor1 = 1664525
	mtArrayFactor2 = 1566083941
	bitsPerWord    = 32
)

type pythonRandom struct {
	state [mtStateWords]uint32
	index int
}

func newPythonRandom(seed string) *pythonRandom {
	data := []byte(seed)
	digest := sha512.Sum512(data)
	data = append(data, digest[:]...)
	r := &pythonRandom{}
	r.seedByArray(keyWords(data))
	return r
}

func keyWords(bigEndian []byte) []uint32 {
	littleEndian := slices.Clone(bigEndian)
	slices.Reverse(littleEndian)
	for len(littleEndian)%4 != 0 {
		littleEndian = append(littleEndian, 0)
	}

	words := make([]uint32, len(littleEndian)/4)
	for i := range words {
		words[i] = binary.LittleEndian.Uint32(littleEndian[4*i:])
	}
	for len(words) > 1 && words[len(words)-1] == 0 {
		words = words[:len(words)-1]
	}
	return words
}

func (r *pythonRandom) seedGenrand(seed uint32) {
	r.state[0] = seed
	for i := 1; i < mtStateWords; i++ {
		previous := r.state[i-1]
		r.state[i] = mtInitFactor*(previous^(previous>>30)) + uint32(i)
	}
	r.index = mtStateWords
}

func (r *pythonRandom) seedByArray(key []uint32) {
	r.seedGenrand(mtGenrandSeed)
	i, j := 1, 0
	for range max(mtStateWords, len(key)) {
		previous := r.state[i-1]
		r.state[i] = (r.state[i] ^ ((previous ^ (previous >> 30)) * mtArrayFactor1)) + key[j] + uint32(j)
		i++
		j++
		if i >= mtStateWords {
			r.state[0] = r.state[mtStateWords-1]
			i = 1
		}
		if j >= len(key) {
			j = 0
		}
	}
	for range mtStateWords - 1 {
		previous := r.state[i-1]
		r.state[i] = (r.state[i] ^ ((previous ^ (previous >> 30)) * mtArrayFactor2)) - uint32(i)
		i++
		if i >= mtStateWords {
			r.state[0] = r.state[mtStateWords-1]
			i = 1
		}
	}
	r.state[0] = mtUpperMask
}

func (r *pythonRandom) regenerate() {
	for k := range mtStateWords {
		y := (r.state[k] & mtUpperMask) | (r.state[(k+1)%mtStateWords] & mtLowerMask)
		next := r.state[(k+mtShiftWords)%mtStateWords] ^ (y >> 1)
		if y&1 != 0 {
			next ^= mtMatrixA
		}
		r.state[k] = next
	}

	r.index = 0
}

func (r *pythonRandom) uint32() uint32 {
	if r.index >= mtStateWords {
		r.regenerate()
	}
	y := r.state[r.index]
	r.index++

	y ^= y >> 11
	y ^= (y << 7) & 0x9d2c5680
	y ^= (y << 15) & 0xefc60000
	y ^= y >> 18
	return y
}

func (r *pythonRandom) randBytes(n int) []byte {
	out := make([]byte, 0, n+3)
	for len(out) < n {
		out = binary.LittleEndian.AppendUint32(out, r.uint32())
	}
	return out[:n]
}

func (r *pythonRandom) below(n int) int {
	width := bits.Len(uint(n))
	for {
		value := int(r.uint32() >> (bitsPerWord - width))
		if value < n {
			return value
		}
	}
}

func (r *pythonRandom) shuffle(items []int) {
	for i := len(items) - 1; i > 0; i-- {
		j := r.below(i + 1)
		items[i], items[j] = items[j], items[i]
	}
}
