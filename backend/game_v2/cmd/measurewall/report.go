package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"
)

const schemaVersion = 1

type metadata struct {
	RNGVersion     string  `json:"rng_version"`
	SeedBytes      int     `json:"seed_bytes"`
	Games          int     `json:"games"`
	Rounds         int     `json:"rounds"`
	ExperimentSeed int     `json:"experiment_seed"`
	ControlMethod  string  `json:"control_method"`
	Go             string  `json:"go"`
	StartedAt      string  `json:"started_at"`
	ElapsedSeconds float64 `json:"elapsed_seconds"`
	WallsPerSecond float64 `json:"walls_per_second"`
}

func formatNumber(value *float64, digits int) string {
	if value == nil {
		return "-"
	}
	return strconv.FormatFloat(*value, 'f', digits, 64)
}

func formatProbability(value float64) string {
	if value >= 0.001 {
		return fmt.Sprintf("%.3f", value)
	}
	return fmt.Sprintf("%.1e", value)
}

func alarmRatePercent() string {
	return strconv.FormatFloat(familyAlarmRate*100, 'f', 1, 64) + "%"
}

func renderText(r report) string {
	var sections []string
	for _, section := range []string{
		renderHeader(r),
		renderFamilies(r),
		renderMeans(r),
		renderComparisons(r),
		renderCrossRound(r),
		renderVerdict(r),
	} {
		if section != "" {
			sections = append(sections, section)
		}
	}
	return strings.Join(sections, "\n\n")
}

func renderHeader(r report) string {
	meta := r.metadata
	size := fmt.Sprintf("%d games x %d rounds = %d walls", meta.Games, meta.Rounds, r.walls)
	lines := []string{
		"WALL GENERATOR MEASUREMENT",
		fmt.Sprintf("  rng %s, seed %d bytes, %s, experiment %d", meta.RNGVersion, meta.SeedBytes, size, meta.ExperimentSeed),
		fmt.Sprintf("  elapsed %.1fs, %.0f walls/s, go %s", meta.ElapsedSeconds, meta.WallsPerSecond, meta.Go),
	}
	if len(r.errors) == 0 {
		lines = append(lines, fmt.Sprintf(
			"  structure: ok (%d walls own every tile once, the first game regenerates equal)", r.walls,
		))
		return strings.Join(lines, "\n")
	}

	lines = append(lines, fmt.Sprintf("  structure: %d ERRORS", len(r.errors)))
	for _, problem := range r.errors {
		lines = append(lines, "    "+problem)
	}
	return strings.Join(lines, "\n")
}

func renderFamilies(r report) string {
	columns := fmt.Sprintf("%6s %7s %8s %6s %8s %8s %8s  status", "cells", "trials", "min exp", "max z", "tail p", "at", "x cells")
	lines := []string{
		"CELL FAMILIES (exact reference; warn when the extreme cell's tail x cells is under " + alarmRatePercent() + ")",
		fmt.Sprintf("  %-56s %s", "name", columns),
	}
	for _, family := range r.families {
		at := fmt.Sprintf("%d,%d", family.TailCell[0], family.TailCell[1])
		tail := formatProbability(family.TailP)
		if !family.Exact {
			tail += "~"
		}
		lines = append(lines, fmt.Sprintf(
			"  %-56s %6d %7d %8.1f %6.2f %8s %8s %8s  %s",
			family.Name, family.Cells, family.Trials, family.MinExpected, family.MaxZ, tail, at,
			formatProbability(family.FamilyP), family.Status,
		))
	}
	lines = append(lines, "  tail p: exact binomial, or ~ normal with hypergeometric variance; x cells: a union bound")
	return strings.Join(lines, "\n")
}

func renderMeans(r report) string {
	lines := []string{
		"MEANS PER GAME (exact reference; the standard error treats each game as one observation)",
		fmt.Sprintf("  %-56s %9s %9s %7s %6s  status", "name", "observed", "expected", "se", "z"),
	}
	for _, summary := range r.means {
		lines = append(lines, fmt.Sprintf(
			"  %-56s %9s %9s %7s %6s  %s",
			summary.Name, formatNumber(summary.Mean, 3), formatNumber(summary.Expected, 3),
			formatNumber(summary.SE, 4), formatNumber(summary.Z, 1), summary.Status,
		))
	}
	return strings.Join(lines, "\n")
}

func renderComparisons(r report) string {
	lines := []string{
		"STARTING HANDS vs control (" + r.metadata.ControlMethod + ")",
		fmt.Sprintf("  %-56s %9s %9s %6s  status   %9s %9s", "name", "engine", "control", "z", "engine n", "control n"),
	}
	for _, c := range r.comparisons {
		counts := ""
		if c.left.Events != nil && c.right.Events != nil {
			counts = fmt.Sprintf("%9d %9d", *c.left.Events, *c.right.Events)
		}
		lines = append(lines, fmt.Sprintf(
			"  %-56s %9s %9s %6s  %-12s %s",
			c.name, formatNumber(c.left.Mean, 4), formatNumber(c.right.Mean, 4), formatNumber(c.z, 1), c.status, counts,
		))
	}
	return strings.Join(lines, "\n")
}

func renderCrossRound(r report) string {
	if r.consecutivePairs == 0 {
		return ""
	}
	verdict := "ok"
	if r.identicalWalls != 0 {
		verdict = "WARN"
	}
	return fmt.Sprintf(
		"CONSECUTIVE ROUNDS OF ONE SEED\n  identical walls: %d of %d pairs  %s", r.identicalWalls, r.consecutivePairs, verdict,
	)
}

func renderVerdict(r report) string {
	var warnings []string
	for _, family := range r.families {
		if family.Status.isWarning() {
			warnings = append(warnings, family.Name)
		}
	}
	for _, summary := range r.means {
		if summary.Status.isWarning() {
			warnings = append(warnings, summary.Name)
		}
	}
	for _, c := range r.comparisons {
		if c.status.isWarning() {
			warnings = append(warnings, c.name)
		}
	}
	if r.identicalWalls != 0 {
		warnings = append(warnings, "identical consecutive walls")
	}

	if len(warnings) == 0 {
		return "No statistical warnings. Under a correct generator each family warns with at most a " +
			alarmRatePercent() + " chance (a union bound over its cells), so a warning is a prompt to rerun, not a proof."
	}
	return "STATISTICAL WARNINGS (rerun with another experiment seed before reading anything into one):\n  " +
		strings.Join(warnings, "\n  ")
}

type comparisonJSON struct {
	Name   string   `json:"name"`
	Z      *float64 `json:"z"`
	Status status   `json:"status"`
}

type reportJSON struct {
	SchemaVersion    int              `json:"schema_version"`
	Metadata         metadata         `json:"metadata"`
	Errors           []string         `json:"errors"`
	Games            int              `json:"games"`
	Walls            int              `json:"walls"`
	ConsecutivePairs int              `json:"consecutive_pairs"`
	IdenticalWalls   int              `json:"identical_walls"`
	Families         []familyJSON     `json:"families"`
	Means            []meanSummary    `json:"means"`
	Comparisons      []comparisonJSON `json:"comparisons"`
	EngineHands      []meanSummary    `json:"engine_hands"`
	ControlHands     []meanSummary    `json:"control_hands"`
}

func toJSON(r report, families []familyJSON) reportJSON {
	out := reportJSON{
		SchemaVersion:    schemaVersion,
		Metadata:         r.metadata,
		Errors:           append([]string{}, r.errors...),
		Games:            r.games,
		Walls:            r.walls,
		ConsecutivePairs: r.consecutivePairs,
		IdenticalWalls:   r.identicalWalls,
		Families:         families,
		Means:            r.means,
	}
	for _, c := range r.comparisons {
		out.Comparisons = append(out.Comparisons, comparisonJSON{Name: c.name, Z: c.z, Status: c.status})
		out.EngineHands = append(out.EngineHands, c.left)
		out.ControlHands = append(out.ControlHands, c.right)
	}
	return out
}

func comparableMeans(r report) ([]string, map[string]meanSummary) {
	var names []string
	byName := map[string]meanSummary{}
	summaries := append([]meanSummary{}, r.means...)
	for _, c := range r.comparisons {
		summaries = append(summaries, c.left)
	}
	for _, summary := range summaries {
		if _, seen := byName[summary.Name]; !seen {
			names = append(names, summary.Name)
		}
		byName[summary.Name] = summary
	}
	return names, byName
}

type baselineJSON struct {
	SchemaVersion *int          `json:"schema_version"`
	Metadata      metadata      `json:"metadata"`
	Errors        []string      `json:"errors"`
	Means         []meanSummary `json:"means"`
	EngineHands   []meanSummary `json:"engine_hands"`
}

func renderBaseline(r report, path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read baseline: %w", err)
	}
	var base baselineJSON
	err = json.Unmarshal(data, &base)
	if err != nil {
		return "", fmt.Errorf("parse baseline %s: %w", path, err)
	}
	if base.SchemaVersion == nil || *base.SchemaVersion != schemaVersion {
		found := "None"
		if base.SchemaVersion != nil {
			found = strconv.Itoa(*base.SchemaVersion)
		}
		return fmt.Sprintf("BASELINE %s: schema %s is not %d, not compared", path, found, schemaVersion), nil
	}

	baseline := map[string]meanSummary{}
	for _, summary := range append(base.Means, base.EngineHands...) {
		baseline[summary.Name] = summary
	}
	names, current := comparableMeans(r)
	var shared []string
	for _, name := range names {
		if _, ok := baseline[name]; ok {
			shared = append(shared, name)
		}
	}

	meta := base.Metadata
	paired := meta.ExperimentSeed == r.metadata.ExperimentSeed && meta.SeedBytes == r.metadata.SeedBytes
	size := fmt.Sprintf("%d games x %d rounds, %s, seed %d bytes", meta.Games, meta.Rounds, meta.RNGVersion, meta.SeedBytes)
	lines := []string{fmt.Sprintf("BASELINE %s (%s)", path, size)}
	if len(base.Errors) > 0 {
		lines = append(lines, fmt.Sprintf("  the baseline run had %d structural errors", len(base.Errors)))
	}

	if paired {
		lines = append(lines,
			"  same experiment seed: the runs share their engine seeds, so only the differences are shown; "+
				"rerun with another --experiment-seed for an independent comparison with a z score",
			fmt.Sprintf("  %-56s %9s %9s %8s", "name", "baseline", "current", "diff"),
		)
		for _, name := range shared {
			lines = append(lines, pairedRow(name, baseline[name], current[name]))
		}
		return strings.Join(lines, "\n"), nil
	}

	threshold := warnThreshold(max(len(shared), 1))
	lines = append(lines, fmt.Sprintf("  %-56s %9s %9s %6s  status", "name", "baseline", "current", "z"))
	for _, name := range shared {
		c := compare(current[name], baseline[name], threshold)
		lines = append(lines, fmt.Sprintf(
			"  %-56s %9s %9s %6s  %s",
			c.name, formatNumber(c.right.Mean, 4), formatNumber(c.left.Mean, 4), formatNumber(c.z, 1), c.status,
		))
	}
	return strings.Join(lines, "\n"), nil
}

func pairedRow(name string, baseline, current meanSummary) string {
	var difference *float64
	if baseline.Mean != nil && current.Mean != nil {
		difference = new(*current.Mean - *baseline.Mean)
	}
	return fmt.Sprintf(
		"  %-56s %9s %9s %8s", name, formatNumber(baseline.Mean, 4), formatNumber(current.Mean, 4), formatNumber(difference, 4),
	)
}
