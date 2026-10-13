#!/usr/bin/env python3

import csv
import html
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "report"
FIGURES = REPORT / "figures"
BASELINE_SUMMARY = ROOT / "results/profiling/baseline-compiler-opt/summary.csv"
OPT1_SUMMARY = ROOT / "results/profiling/opt1/summary.csv"
BASELINE_CALLGRIND = ROOT / "results/profiling/baseline-compiler-opt/callgrind_metrics.csv"
OPT1_CALLGRIND = ROOT / "results/profiling/opt1/callgrind_metrics.csv"

COLORS = {
    "blue": "#2563a6",
    "teal": "#16847a",
    "coral": "#d55e4f",
    "gold": "#c58b18",
    "ink": "#17212b",
    "muted": "#586675",
    "grid": "#d9e0e6",
    "paper": "#ffffff",
}


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def esc(value):
    return html.escape(str(value), quote=True)


def svg_start(width, height):
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text { font-family: Arial, Helvetica, sans-serif; fill: #17212b; letter-spacing: 0; }",
        ".title { font-size: 22px; font-weight: 700; }",
        ".subtitle { font-size: 14px; fill: #586675; }",
        ".axis { font-size: 12px; fill: #586675; }",
        ".label { font-size: 13px; }",
        ".value { font-size: 12px; font-weight: 700; }",
        "</style>",
        f'<rect width="{width}" height="{height}" fill="{COLORS["paper"]}"/>',
    ]


def write_svg(name, lines):
    lines.append("</svg>")
    (FIGURES / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def panel_title(lines, x, y, title, subtitle=None):
    lines.append(f'<text x="{x}" y="{y}" class="title">{esc(title)}</text>')
    if subtitle:
        lines.append(f'<text x="{x}" y="{y + 22}" class="subtitle">{esc(subtitle)}</text>')


def vertical_bars(lines, x, y, width, height, labels, values, color, maximum, unit, decimals=3):
    left = x + 54
    right = x + width - 12
    top = y + 10
    bottom = y + height - 46
    plot_height = bottom - top
    plot_width = right - left

    for tick in range(5):
        fraction = tick / 4
        yy = bottom - fraction * plot_height
        value = fraction * maximum
        lines.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" stroke="{COLORS["grid"]}"/>')
        lines.append(f'<text x="{left - 8}" y="{yy + 4:.1f}" text-anchor="end" class="axis">{value:.1f}</text>')

    slot = plot_width / len(values)
    bar_width = slot * 0.56
    for index, (label, value) in enumerate(zip(labels, values)):
        bx = left + index * slot + (slot - bar_width) / 2
        bar_height = value / maximum * plot_height
        by = bottom - bar_height
        lines.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="2" fill="{color}"/>')
        lines.append(f'<text x="{bx + bar_width / 2:.1f}" y="{by - 7:.1f}" text-anchor="middle" class="value">{value:.{decimals}f}</text>')
        lines.append(f'<text x="{bx + bar_width / 2:.1f}" y="{bottom + 20:.1f}" text-anchor="middle" class="label">{esc(label)}</text>')

    lines.append(f'<text x="{x + 10}" y="{top + plot_height / 2:.1f}" transform="rotate(-90 {x + 10} {top + plot_height / 2:.1f})" text-anchor="middle" class="axis">{esc(unit)}</text>')


def horizontal_bars(lines, x, y, width, labels, values, color, maximum):
    label_width = 155
    value_width = 48
    plot_x = x + label_width
    plot_width = width - label_width - value_width
    row_height = 38

    for tick in range(5):
        fraction = tick / 4
        xx = plot_x + fraction * plot_width
        lines.append(f'<line x1="{xx:.1f}" y1="{y - 8}" x2="{xx:.1f}" y2="{y + row_height * len(values) - 8}" stroke="{COLORS["grid"]}"/>')
        lines.append(f'<text x="{xx:.1f}" y="{y - 14}" text-anchor="middle" class="axis">{fraction * maximum:.0f}%</text>')

    for index, (label, value) in enumerate(zip(labels, values)):
        yy = y + index * row_height
        bar_width = value / maximum * plot_width
        lines.append(f'<text x="{plot_x - 10}" y="{yy + 17}" text-anchor="end" class="label">{esc(label)}</text>')
        lines.append(f'<rect x="{plot_x}" y="{yy}" width="{bar_width:.1f}" height="24" rx="2" fill="{color}"/>')
        lines.append(f'<text x="{plot_x + bar_width + 7:.1f}" y="{yy + 17}" class="value">{value:.2f}%</text>')


def grouped_log_bars(lines, x, y, width, height, labels, first, second, first_name, second_name):
    left = x + 64
    right = x + width - 20
    top = y + 16
    bottom = y + height - 58
    plot_height = bottom - top
    plot_width = right - left
    minimum = 0.01
    maximum = 10.0

    def scale(value):
        return bottom - (math.log10(value) - math.log10(minimum)) / (math.log10(maximum) - math.log10(minimum)) * plot_height

    for value in [0.01, 0.1, 1.0, 10.0]:
        yy = scale(value)
        lines.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" stroke="{COLORS["grid"]}"/>')
        lines.append(f'<text x="{left - 9}" y="{yy + 4:.1f}" text-anchor="end" class="axis">{value:g}</text>')

    slot = plot_width / len(labels)
    bar_width = slot * 0.24
    for index, label in enumerate(labels):
        center = left + slot * (index + 0.5)
        for offset, value, color in [(-bar_width * 0.58, first[index], COLORS["blue"]), (bar_width * 0.58, second[index], COLORS["coral"])]:
            bx = center + offset - bar_width / 2
            by = scale(value)
            lines.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_width:.1f}" height="{bottom - by:.1f}" rx="2" fill="{color}"/>')
            lines.append(f'<text x="{bx + bar_width / 2:.1f}" y="{by - 6:.1f}" text-anchor="middle" class="value">{value:.3f}</text>')
        lines.append(f'<text x="{center:.1f}" y="{bottom + 21}" text-anchor="middle" class="label">{esc(label)}</text>')

    legend_y = y + height - 18
    lines.append(f'<rect x="{left}" y="{legend_y - 12}" width="14" height="14" fill="{COLORS["blue"]}"/><text x="{left + 21}" y="{legend_y}" class="label">{esc(first_name)}</text>')
    lines.append(f'<rect x="{left + 150}" y="{legend_y - 12}" width="14" height="14" fill="{COLORS["coral"]}"/><text x="{left + 171}" y="{legend_y}" class="label">{esc(second_name)}</text>')
    lines.append(f'<text x="{x + 12}" y="{top + plot_height / 2:.1f}" transform="rotate(-90 {x + 12} {top + plot_height / 2:.1f})" text-anchor="middle" class="axis">Median seconds (log scale)</text>')


def line_chart(lines, x, y, width, height, labels, values, color, maximum, unit):
    left = x + 55
    right = x + width - 24
    top = y + 10
    bottom = y + height - 42
    plot_width = right - left
    plot_height = bottom - top

    for tick in range(6):
        fraction = tick / 5
        yy = bottom - fraction * plot_height
        lines.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" stroke="{COLORS["grid"]}"/>')
        lines.append(f'<text x="{left - 8}" y="{yy + 4:.1f}" text-anchor="end" class="axis">{fraction * maximum:.1f}</text>')

    points = []
    for index, value in enumerate(values):
        xx = left + index * plot_width / (len(values) - 1)
        yy = bottom - value / maximum * plot_height
        points.append((xx, yy))
    lines.append('<polyline points="' + " ".join(f"{xx:.1f},{yy:.1f}" for xx, yy in points) + f'" fill="none" stroke="{color}" stroke-width="4"/>')
    for label, value, (xx, yy) in zip(labels, values, points):
        lines.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="6" fill="{color}"/>')
        lines.append(f'<text x="{xx:.1f}" y="{yy - 12:.1f}" text-anchor="middle" class="value">{value:.2f}x</text>')
        lines.append(f'<text x="{xx:.1f}" y="{bottom + 21}" text-anchor="middle" class="label">{esc(label)}</text>')
    lines.append(f'<text x="{x + 12}" y="{top + plot_height / 2:.1f}" transform="rotate(-90 {x + 12} {top + plot_height / 2:.1f})" text-anchor="middle" class="axis">{esc(unit)}</text>')


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    baseline = read_csv(BASELINE_SUMMARY)
    opt1 = read_csv(OPT1_SUMMARY)
    baseline_callgrind = read_csv(BASELINE_CALLGRIND)
    opt1_callgrind = read_csv(OPT1_CALLGRIND)

    baseline_by_program = {
        program: [row for row in baseline if row["program"] == program]
        for program in ["pearson", "blur"]
    }

    lines = svg_start(1100, 540)
    panel_title(lines, 32, 34, "Baseline median elapsed time", "Original source compiled with -O2; five normalized batches per input")
    vertical_bars(lines, 24, 78, 520, 430,
                  [row["input"].split(".")[0] for row in baseline_by_program["pearson"]],
                  [float(row["median_elapsed_seconds"]) for row in baseline_by_program["pearson"]],
                  COLORS["blue"], 4.0, "Pearson seconds", 3)
    vertical_bars(lines, 560, 78, 520, 430,
                  [row["input"].split(".")[0] for row in baseline_by_program["blur"]],
                  [float(row["median_elapsed_seconds"]) for row in baseline_by_program["blur"]],
                  COLORS["teal"], 4.5, "Blur seconds", 3)
    write_svg("baseline_runtime.svg", lines)

    lines = svg_start(1100, 540)
    panel_title(lines, 32, 34, "Baseline peak resident memory", "Maximum RSS from GNU time; panels use separate scales")
    vertical_bars(lines, 24, 78, 520, 430,
                  [row["input"].split(".")[0] for row in baseline_by_program["pearson"]],
                  [float(row["max_rss_kb"]) / 1024 for row in baseline_by_program["pearson"]],
                  COLORS["gold"], 28.0, "Pearson MiB", 1)
    vertical_bars(lines, 560, 78, 520, 430,
                  [row["input"].split(".")[0] for row in baseline_by_program["blur"]],
                  [float(row["max_rss_kb"]) / 1024 for row in baseline_by_program["blur"]],
                  COLORS["coral"], 140.0, "Blur MiB", 1)
    write_svg("baseline_memory.svg", lines)

    lines = svg_start(1100, 570)
    panel_title(lines, 32, 34, "Baseline Callgrind hotspots", "Self instruction share on Pearson 512.data and Blur im2.ppm")
    lines.append('<text x="42" y="94" class="subtitle" font-weight="700">Pearson</text>')
    horizontal_bars(lines, 36, 126, 500,
                    ["operator -", "operator /", "copy constructor", "magnitude", "dot", "mean"],
                    [21.42, 21.42, 14.71, 11.77, 5.83, 4.90], COLORS["blue"], 25)
    lines.append('<text x="592" y="94" class="subtitle" font-weight="700">Blur</text>')
    horizontal_bars(lines, 578, 126, 500,
                    ["Filter::blur", "exp core", "exp wrapper", "RGB accessors"],
                    [59.02, 11.70, 7.03, 11.01], COLORS["teal"], 65)
    lines.append('<text x="42" y="548" class="subtitle">RGB accessor value combines r(), g(), and b(); exp values are shown separately.</text>')
    write_svg("baseline_hotspots.svg", lines)

    pearson_o2 = [row for row in baseline if row["program"] == "pearson"]
    pearson_opt1 = [row for row in opt1 if row["program"] == "pearson"]
    labels = [row["input"].split(".")[0] for row in pearson_o2]
    o2_medians = [float(row["median_elapsed_seconds"]) for row in pearson_o2]
    opt1_medians = [float(row["median_elapsed_seconds"]) for row in pearson_opt1]

    lines = svg_start(1000, 560)
    panel_title(lines, 32, 34, "Pearson runtime after Optimization 1", "Both versions compiled with -O2; lower is better")
    grouped_log_bars(lines, 30, 76, 940, 450, labels, o2_medians, opt1_medians, "O2 source baseline", "Optimization 1")
    write_svg("pearson_opt1_runtime.svg", lines)

    speedups = [before / after for before, after in zip(o2_medians, opt1_medians)]
    lines = svg_start(1000, 500)
    panel_title(lines, 32, 34, "Pearson Optimization 1 speedup over -O2 baseline", "Speedup calculated from median elapsed time")
    line_chart(lines, 34, 80, 920, 380, labels, speedups, COLORS["coral"], 5.0, "Speedup")
    write_svg("pearson_opt1_speedup.svg", lines)

    base_pearson = next(row for row in baseline_callgrind if row["program"] == "pearson")
    opt1_pearson = next(row for row in opt1_callgrind if row["program"] == "pearson")
    callgrind_fields = [
        ("Instructions", "instruction_refs"),
        ("Data refs", "data_refs"),
        ("Branches", "branches"),
        ("Branch misses", "branch_mispredicts"),
        ("LL data misses", "data_ll_misses"),
        ("D1 data misses", "data_l1_misses"),
    ]
    reductions = [
        100 * (1 - float(opt1_pearson[field]) / float(base_pearson[field]))
        for _, field in callgrind_fields
    ]
    lines = svg_start(1100, 540)
    panel_title(lines, 32, 34, "Pearson Callgrind reduction after Optimization 1", "Matched 512.data input; positive values mean fewer events")
    vertical_bars(lines, 36, 80, 1028, 420,
                  [label for label, _ in callgrind_fields], reductions,
                  COLORS["teal"], 100.0, "Reduction (%)", 1)
    write_svg("pearson_callgrind_reduction.svg", lines)


if __name__ == "__main__":
    main()
