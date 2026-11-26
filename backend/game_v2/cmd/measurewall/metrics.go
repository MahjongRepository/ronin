package main

import (
	"math"
	"slices"
)

const (
	familyAlarmRate     = 1e-3
	minExpectedPerCell  = 10.0
	minClusters         = 30
	minEvents           = 20
	exactTailFromZ      = 2.5
	tailTermCutoff      = 1e-18
	thresholdIterations = 64
	thresholdUpperZ     = 20.0
)

type status string

const (
	statusOK           status = "ok"
	statusWarn         status = "warn"
	statusDegenerate   status = "degenerate"
	statusInsufficient status = "insufficient"
)

func (s status) isWarning() bool {
	return s == statusWarn || s == statusDegenerate
}

func twoSidedTail(z float64) float64 {
	return math.Erfc(math.Abs(z) / math.Sqrt2)
}

func warnThreshold(cells int) float64 {
	target := familyAlarmRate / float64(cells)
	low, high := 0.0, thresholdUpperZ
	for range thresholdIterations {
		mid := (low + high) / 2
		if twoSidedTail(mid) > target {
			low = mid
		} else {
			high = mid
		}
	}

	return high
}

func binomialTwoSidedTail(trials int, probability float64, count int) float64 {
	if trials == 0 || probability <= 0 || probability >= 1 {
		return 1
	}

	n, k := float64(trials), float64(count)
	logPMF := lgamma(n+1) - lgamma(k+1) - lgamma(n-k+1) + k*math.Log(probability) + (n-k)*math.Log1p(-probability)
	term := math.Exp(logPMF)
	total := term
	x := count
	if k >= n*probability {
		for x < trials && term > total*tailTermCutoff {
			term *= float64(trials-x) / float64(x+1) * probability / (1 - probability)
			x++
			total += term
		}
	} else {
		for x > 0 && term > total*tailTermCutoff {
			term *= float64(x) / float64(trials-x+1) * (1 - probability) / probability
			x--
			total += term
		}
	}

	return min(1, 2*total)
}

func lgamma(x float64) float64 {
	value, _ := math.Lgamma(x)
	return value
}

func uniform(cells int) []float64 {
	probabilities := make([]float64, cells)
	for i := range probabilities {
		probabilities[i] = 1 / float64(cells)
	}

	return probabilities
}

type cell [2]int

type familySummary struct {
	Name        string  `json:"name"`
	Cells       int     `json:"cells"`
	Trials      int     `json:"trials"`
	MinExpected float64 `json:"min_expected"`
	MaxZ        float64 `json:"max_z"`
	MaxCell     cell    `json:"max_cell"`
	TailP       float64 `json:"tail_p"`
	TailCell    cell    `json:"tail_cell"`
	FamilyP     float64 `json:"family_p"`
	Exact       bool    `json:"exact"`
	Status      status  `json:"status"`
}

type cellFamily struct {
	name           string
	probabilities  []float64
	varianceFactor float64
	trials         int
	counts         [][]int
}

func newCellFamily(name string, probabilities []float64, rows int) *cellFamily {
	return newSampledCellFamily(name, probabilities, rows, 1)
}

func newSampledCellFamily(name string, probabilities []float64, rows int, varianceFactor float64) *cellFamily {
	counts := make([][]int, rows)
	for i := range counts {
		counts[i] = make([]int, len(probabilities))
	}

	return &cellFamily{name: name, probabilities: probabilities, varianceFactor: varianceFactor, counts: counts}
}

func (f *cellFamily) add(row, column int) {
	f.counts[row][column]++
}

type cellScore struct {
	z     float64
	cell  cell
	count int
}

type cellTail struct {
	p    float64
	cell cell
}

func (f *cellFamily) summary() familySummary {
	scores := f.scores()
	mostDeviant := scores[0]
	for _, s := range scores[1:] {
		if math.Abs(s.z) > math.Abs(mostDeviant.z) {
			mostDeviant = s
		}
	}

	candidates := slices.DeleteFunc(slices.Clone(scores), func(s cellScore) bool { return math.Abs(s.z) < exactTailFromZ })
	if len(candidates) == 0 {
		candidates = []cellScore{mostDeviant}
	}

	lowest := cellTail{p: math.Inf(1)}
	for _, c := range candidates {
		if p := f.tail(c); p < lowest.p {
			lowest = cellTail{p: p, cell: c.cell}
		}
	}

	cells := len(f.counts) * len(f.probabilities)
	familyP := min(1, float64(cells)*lowest.p)
	minExpected := float64(f.trials) * slices.Min(f.probabilities)
	verdict := statusOK
	switch {
	case minExpected < minExpectedPerCell:
		verdict = statusInsufficient
	case familyP < familyAlarmRate:
		verdict = statusWarn
	}

	return familySummary{
		Name:        f.name,
		Cells:       cells,
		Trials:      f.trials,
		MinExpected: minExpected,
		MaxZ:        mostDeviant.z,
		MaxCell:     mostDeviant.cell,
		TailP:       lowest.p,
		TailCell:    lowest.cell,
		FamilyP:     familyP,
		Exact:       f.varianceFactor == 1,
		Status:      verdict,
	}
}

func (f *cellFamily) scores() []cellScore {
	var scores []cellScore
	trials := float64(f.trials)
	for row, rowCounts := range f.counts {
		for column, count := range rowCounts {
			probability := f.probabilities[column]
			deviation := math.Sqrt(trials * probability * (1 - probability) * f.varianceFactor)
			z := 0.0
			if deviation > 0 {
				z = (float64(count) - trials*probability) / deviation
			}

			scores = append(scores, cellScore{z: z, cell: cell{row, column}, count: count})
		}
	}

	return scores
}

func (f *cellFamily) tail(s cellScore) float64 {
	if f.varianceFactor != 1 {
		return twoSidedTail(s.z)
	}

	return binomialTwoSidedTail(f.trials, f.probabilities[s.cell[1]], s.count)
}

type familyJSON struct {
	familySummary

	Probabilities  []float64 `json:"probabilities"`
	VarianceFactor float64   `json:"variance_factor"`
	Counts         [][]int   `json:"counts"`
}

func (f *cellFamily) json() familyJSON {
	return familyJSON{
		familySummary:  f.summary(),
		Probabilities:  f.probabilities,
		VarianceFactor: f.varianceFactor,
		Counts:         f.counts,
	}
}

type meanSummary struct {
	Name     string   `json:"name"`
	Clusters int      `json:"clusters"`
	Events   *int     `json:"events"`
	Mean     *float64 `json:"mean"`
	SE       *float64 `json:"se"`
	Expected *float64 `json:"expected"`
	Z        *float64 `json:"z"`
	Status   status   `json:"status"`
}

type meanStat struct {
	name     string
	expected *float64
	events   *int
	clusters int
	total    float64
	totalSq  float64
}

func newMeanStat(name string) *meanStat {
	return &meanStat{name: name}
}

func newExpectedMeanStat(name string, expected float64) *meanStat {
	return &meanStat{name: name, expected: &expected}
}

func newEventMeanStat(name string) *meanStat {
	return &meanStat{name: name, events: new(0)}
}

func (m *meanStat) add(value float64) {
	m.clusters++
	m.total += value
	m.totalSq += value * value
}

func (m *meanStat) mean() *float64 {
	if m.clusters == 0 {
		return nil
	}

	return new(m.total / float64(m.clusters))
}

func (m *meanStat) se() *float64 {
	if m.clusters < 2 {
		return nil
	}

	clusters := float64(m.clusters)
	variance := max(m.totalSq-m.total*m.total/clusters, 0) / (clusters - 1)
	return new(math.Sqrt(variance / clusters))
}

func (m *meanStat) summary() meanSummary {
	mean, se := m.mean(), m.se()
	var z *float64
	var verdict status
	switch {
	case m.expected == nil:
		verdict = statusOK
	case mean == nil || se == nil || !m.sufficient():
		verdict = statusInsufficient
	case *se == 0 && *mean == *m.expected:
		verdict = statusOK
	case *se == 0:
		verdict = statusDegenerate
	default:
		z = new((*mean - *m.expected) / *se)
		verdict = statusOK
		if math.Abs(*z) > warnThreshold(1) {
			verdict = statusWarn
		}
	}

	var events *int
	if m.events != nil {
		events = new(*m.events)
	}

	return meanSummary{
		Name:     m.name,
		Clusters: m.clusters,
		Events:   events,
		Mean:     mean,
		SE:       se,
		Expected: m.expected,
		Z:        z,
		Status:   verdict,
	}
}

func (m *meanStat) sufficient() bool {
	return m.clusters >= minClusters && (m.events == nil || *m.events >= minEvents)
}

type comparison struct {
	name   string
	left   meanSummary
	right  meanSummary
	z      *float64
	status status
}

func compare(left, right meanSummary, threshold float64) comparison {
	eventsKnown := left.Events != nil && right.Events != nil
	enoughEvents := !eventsKnown || *left.Events+*right.Events >= 2*minEvents
	unknown := left.Mean == nil || right.Mean == nil || left.SE == nil || right.SE == nil
	result := comparison{name: left.Name, left: left, right: right}
	switch {
	case unknown || min(left.Clusters, right.Clusters) < minClusters || !enoughEvents:
		result.status = statusInsufficient
	case *left.SE == 0 && *right.SE == 0 && *left.Mean == *right.Mean:
		result.status = statusOK
	case *left.SE == 0 && *right.SE == 0:
		result.status = statusDegenerate
	default:
		result.z = new((*left.Mean - *right.Mean) / math.Sqrt(*left.SE**left.SE+*right.SE**right.SE))
		result.status = statusOK
		if math.Abs(*result.z) > threshold {
			result.status = statusWarn
		}
	}

	return result
}

type fractionHistogram struct {
	bins  []*meanStat
	total *meanStat
}

func newFractionHistogram(name string, labels []string) fractionHistogram {
	bins := make([]*meanStat, len(labels))
	for i, label := range labels {
		bins[i] = newEventMeanStat(name + " = " + label)
	}

	return fractionHistogram{bins: bins, total: newMeanStat(name + ", mean")}
}

func (h fractionHistogram) addGame(values []int, offset int) {
	gameCounts := make([]int, len(h.bins))
	sum := 0
	for _, value := range values {
		gameCounts[value+offset]++
		sum += value
	}

	for i, stat := range h.bins {
		stat.add(float64(gameCounts[i]) / float64(len(values)))
		*stat.events += gameCounts[i]
	}

	h.total.add(float64(sum) / float64(len(values)))
}

func (h fractionHistogram) summaries() []meanSummary {
	summaries := make([]meanSummary, 0, len(h.bins)+1)
	for _, stat := range h.bins {
		summaries = append(summaries, stat.summary())
	}

	return append(summaries, h.total.summary())
}
