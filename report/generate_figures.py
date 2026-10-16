#!/usr/bin/env python3

import argparse
import csv
import html
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "report"
FIGURES = REPORT / "figures"
PROFILING = ROOT / "results/profiling"

COLORS = {
    "blue": "#2563a6",
    "teal": "#16847a",
    "coral": "#d55e4f",
    "gold": "#c58b18",
    "green": "#3f7d44",
    "ink": "#17212b",
    "muted": "#586675",
    "grid": "#d9e0e6",
    "paper": "#ffffff",
}


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def available_stages():
    return sorted(
        path for path in PROFILING.iterdir()
        if path.is_dir() and (path / "summary.csv").is_file()
    )


def resolve_stage(value):
    requested = Path(value).expanduser()
    candidates = [requested, PROFILING / requested]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "summary.csv").is_file():
            return candidate.resolve()

    choices = ", ".join(path.name for path in available_stages()) or "none"
    raise FileNotFoundError(
        f"Profiling stage {value!r} does not contain summary.csv. Available stages: {choices}"
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate comparison figures for any two profiling result stages."
    )
    parser.add_argument(
        "first_stage", nargs="?", default="baseline-compiler-opt",
        help="stage name under results/profiling or a stage directory path",
    )
    parser.add_argument(
        "second_stage", nargs="?", default="pearson-optim1-normalize",
        help="stage name under results/profiling or a stage directory path",
    )
    parser.add_argument(
        "--metric", choices=("mean", "median"), default="mean",
        help="elapsed-time statistic used for runtime and speedup charts (default: mean)",
    )
    parser.add_argument("--first-label", help="display label for the first stage")
    parser.add_argument("--second-label", help="display label for the second stage")
    parser.add_argument("--prefix", help="output filename prefix")
    parser.add_argument(
        "--output-dir", type=Path, default=FIGURES,
        help="directory for generated SVG files (default: report/figures)",
    )
    parser.add_argument(
        "--list-stages", action="store_true",
        help="list available profiling stages and exit",
    )
    parser.add_argument(
        "--report-suite", action="store_true",
        help=(
            "generate the complete baseline, Optimization 1, Optimization 2, "
            "and parallel Pearson figure set"
        ),
    )
    return parser.parse_args()


def display_name(stage):
    return stage.name.replace("_", " ").replace("-", " ").title()


def filename_part(value):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    if not cleaned:
        raise ValueError("The output prefix must contain at least one letter or number")
    return cleaned


def rows_for_program(rows, program):
    selected = [row for row in rows if row["program"] == program]
    if not selected:
        raise ValueError(f"No {program} rows were found in summary.csv")
    return selected


def aligned_rows(first_rows, second_rows, program):
    first = rows_for_program(first_rows, program)
    second_by_input = {
        row["input"]: row for row in rows_for_program(second_rows, program)
    }
    first_inputs = [row["input"] for row in first]
    if set(first_inputs) != set(second_by_input):
        missing_from_second = sorted(set(first_inputs) - set(second_by_input))
        extra_in_second = sorted(set(second_by_input) - set(first_inputs))
        raise ValueError(
            f"Summary inputs do not match for {program}: "
            f"missing from second={missing_from_second}, extra in second={extra_in_second}"
        )
    return first, [second_by_input[input_name] for input_name in first_inputs]


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


def grouped_log_bars(
        lines, x, y, width, height, labels, first, second,
        first_name, second_name, axis_label):
    left = x + 64
    right = x + width - 20
    top = y + 16
    bottom = y + height - 58
    plot_height = bottom - top
    plot_width = right - left
    positive_values = [value for value in first + second if value > 0]
    if len(positive_values) != len(first) + len(second):
        raise ValueError("Logarithmic charts require values greater than zero")
    minimum = 10 ** math.floor(math.log10(min(positive_values)))
    maximum = 10 ** math.ceil(math.log10(max(positive_values)))
    if minimum == maximum:
        maximum *= 10

    def scale(value):
        return bottom - (math.log10(value) - math.log10(minimum)) / (math.log10(maximum) - math.log10(minimum)) * plot_height

    tick_count = int(round(math.log10(maximum) - math.log10(minimum)))
    for exponent in range(tick_count + 1):
        value = minimum * (10 ** exponent)
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
    second_legend_x = left + plot_width / 2
    lines.append(f'<rect x="{second_legend_x}" y="{legend_y - 12}" width="14" height="14" fill="{COLORS["coral"]}"/><text x="{second_legend_x + 21}" y="{legend_y}" class="label">{esc(second_name)}</text>')
    lines.append(f'<text x="{x + 12}" y="{top + plot_height / 2:.1f}" transform="rotate(-90 {x + 12} {top + plot_height / 2:.1f})" text-anchor="middle" class="axis">{esc(axis_label)} (log scale)</text>')


def grouped_percent_bars(lines, x, y, width, height, labels, first, second, first_name, second_name, maximum):
    left = x + 64
    right = x + width - 20
    top = y + 16
    bottom = y + height - 64
    plot_height = bottom - top
    plot_width = right - left

    for tick in range(5):
        fraction = tick / 4
        yy = bottom - fraction * plot_height
        value = fraction * maximum
        lines.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" stroke="{COLORS["grid"]}"/>')
        lines.append(f'<text x="{left - 9}" y="{yy + 4:.1f}" text-anchor="end" class="axis">{value:.0f}%</text>')

    slot = plot_width / len(labels)
    bar_width = slot * 0.24
    for index, label in enumerate(labels):
        center = left + slot * (index + 0.5)
        for offset, value, color in [
            (-bar_width * 0.58, first[index], COLORS["blue"]),
            (bar_width * 0.58, second[index], COLORS["coral"]),
        ]:
            bx = center + offset - bar_width / 2
            bar_height = value / maximum * plot_height
            by = bottom - bar_height
            lines.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="2" fill="{color}"/>')
            lines.append(f'<text x="{bx + bar_width / 2:.1f}" y="{by - 6:.1f}" text-anchor="middle" class="value">{value:.0f}%</text>')
        lines.append(f'<text x="{center:.1f}" y="{bottom + 21}" text-anchor="middle" class="label">{esc(label)}</text>')

    legend_y = y + height - 18
    lines.append(f'<rect x="{left}" y="{legend_y - 12}" width="14" height="14" fill="{COLORS["blue"]}"/><text x="{left + 21}" y="{legend_y}" class="label">{esc(first_name)}</text>')
    second_legend_x = left + plot_width / 2
    lines.append(f'<rect x="{second_legend_x}" y="{legend_y - 12}" width="14" height="14" fill="{COLORS["coral"]}"/><text x="{second_legend_x + 21}" y="{legend_y}" class="label">{esc(second_name)}</text>')
    lines.append(f'<text x="{x + 12}" y="{top + plot_height / 2:.1f}" transform="rotate(-90 {x + 12} {top + plot_height / 2:.1f})" text-anchor="middle" class="axis">Relative event count</text>')


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


def series_legend(lines, x, y, series, spacing=220):
    for index, (name, _, color) in enumerate(series):
        legend_x = x + index * spacing
        lines.append(
            f'<rect x="{legend_x}" y="{y - 12}" width="14" height="14" '
            f'rx="2" fill="{color}"/>'
        )
        lines.append(
            f'<text x="{legend_x + 21}" y="{y}" class="label">{esc(name)}</text>'
        )


def multi_grouped_bars(
        lines, x, y, width, height, labels, series, axis_label,
        minimum=0.0, maximum=None, logarithmic=False):
    left = x + 78
    right = x + width - 24
    top = y + 10
    bottom = y + height - 58
    plot_width = right - left
    plot_height = bottom - top
    values = [value for _, series_values, _ in series for value in series_values]

    if logarithmic:
        if any(value <= 0 for value in values):
            raise ValueError("Logarithmic charts require positive values")
        minimum = 10 ** math.floor(math.log10(min(values)))
        maximum = 10 ** math.ceil(math.log10(max(values)))
        if minimum == maximum:
            maximum *= 10

        def scale(value):
            relative = (
                (math.log10(value) - math.log10(minimum)) /
                (math.log10(maximum) - math.log10(minimum))
            )
            return bottom - relative * plot_height

        first_exponent = int(round(math.log10(minimum)))
        last_exponent = int(round(math.log10(maximum)))
        ticks = [10 ** exponent for exponent in range(first_exponent, last_exponent + 1)]
    else:
        maximum = maximum if maximum is not None else max(values) * 1.1
        if maximum <= minimum:
            maximum = minimum + 1

        def scale(value):
            return bottom - (value - minimum) / (maximum - minimum) * plot_height

        ticks = [minimum + (maximum - minimum) * tick / 5 for tick in range(6)]

    for value in ticks:
        yy = scale(value)
        tick_label = f"{value:g}" if logarithmic else f"{value:.0f}"
        lines.append(
            f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" '
            f'stroke="{COLORS["grid"]}"/>'
        )
        lines.append(
            f'<text x="{left - 9}" y="{yy + 4:.1f}" text-anchor="end" '
            f'class="axis">{tick_label}</text>'
        )

    group_width = plot_width / len(labels)
    bar_width = min(42, group_width * 0.72 / len(series))
    gap = bar_width * 0.14
    total_width = len(series) * bar_width + (len(series) - 1) * gap
    for label_index, label in enumerate(labels):
        center = left + group_width * (label_index + 0.5)
        group_start = center - total_width / 2
        for series_index, (_, series_values, color) in enumerate(series):
            value = series_values[label_index]
            bx = group_start + series_index * (bar_width + gap)
            by = scale(value)
            lines.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_width:.1f}" '
                f'height="{bottom - by:.1f}" rx="2" fill="{color}"/>'
            )
        lines.append(
            f'<text x="{center:.1f}" y="{bottom + 22}" text-anchor="middle" '
            f'class="label">{esc(label)}</text>'
        )

    scale_note = " (log scale)" if logarithmic else ""
    lines.append(
        f'<text x="{x + 13}" y="{top + plot_height / 2:.1f}" '
        f'transform="rotate(-90 {x + 13} {top + plot_height / 2:.1f})" '
        f'text-anchor="middle" class="axis">{esc(axis_label + scale_note)}</text>'
    )


def multi_series_line_chart(
        lines, x, y, width, height, labels, series, axis_label,
        minimum, maximum, suffix="", reference=None, show_values=False):
    left = x + 72
    right = x + width - 28
    top = y + 10
    bottom = y + height - 48
    plot_width = right - left
    plot_height = bottom - top

    def scale(value):
        return bottom - (value - minimum) / (maximum - minimum) * plot_height

    for tick in range(6):
        value = minimum + (maximum - minimum) * tick / 5
        yy = scale(value)
        lines.append(
            f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" '
            f'stroke="{COLORS["grid"]}"/>'
        )
        lines.append(
            f'<text x="{left - 9}" y="{yy + 4:.1f}" text-anchor="end" '
            f'class="axis">{value:.1f}{esc(suffix)}</text>'
        )

    denominator = max(1, len(labels) - 1)
    x_positions = [left + index * plot_width / denominator for index in range(len(labels))]

    if reference is not None:
        reference_name, reference_values = reference
        points = [
            (xx, scale(value)) for xx, value in zip(x_positions, reference_values)
        ]
        lines.append(
            '<polyline points="' +
            " ".join(f"{xx:.1f},{yy:.1f}" for xx, yy in points) +
            f'" fill="none" stroke="{COLORS["muted"]}" stroke-width="2" '
            'stroke-dasharray="7 6"/>'
        )
        lines.append(
            f'<text x="{right}" y="{max(top + 14, points[-1][1] - 8):.1f}" '
            f'text-anchor="end" class="axis">{esc(reference_name)}</text>'
        )

    for _, values, color in series:
        points = [(xx, scale(value)) for xx, value in zip(x_positions, values)]
        lines.append(
            '<polyline points="' +
            " ".join(f"{xx:.1f},{yy:.1f}" for xx, yy in points) +
            f'" fill="none" stroke="{color}" stroke-width="3"/>'
        )
        for value, (xx, yy) in zip(values, points):
            lines.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="5" fill="{color}"/>')
            if show_values:
                lines.append(
                    f'<text x="{xx:.1f}" y="{yy - 10:.1f}" text-anchor="middle" '
                    f'class="value">{value:.2f}{esc(suffix)}</text>'
                )

    for label, xx in zip(labels, x_positions):
        lines.append(
            f'<text x="{xx:.1f}" y="{bottom + 22}" text-anchor="middle" '
            f'class="label">{esc(label)}</text>'
        )

    lines.append(
        f'<text x="{x + 13}" y="{top + plot_height / 2:.1f}" '
        f'transform="rotate(-90 {x + 13} {top + plot_height / 2:.1f})" '
        f'text-anchor="middle" class="axis">{esc(axis_label)}</text>'
    )


def generate_report_suite(metric, output_directory):
    global FIGURES

    stage_directories = {
        "Baseline": PROFILING / "baseline-compiler-opt",
        "Optimization 1": PROFILING / "pearson-optim1-normalize",
        "Optimization 2": PROFILING / "pearson-opt2-reference",
        "Parallel": PROFILING / "parallel_pearson",
    }
    required_files = ("summary.csv", "callgrind_metrics.csv")
    for stage_name, directory in stage_directories.items():
        for filename in required_files:
            if not (directory / filename).is_file():
                raise FileNotFoundError(
                    f"{stage_name} is missing {directory / filename}"
                )

    FIGURES = output_directory.expanduser().resolve()
    FIGURES.mkdir(parents=True, exist_ok=True)
    metric_directory = REPORT / "metrics"
    metric_directory.mkdir(parents=True, exist_ok=True)

    input_names = ["128.data", "256.data", "512.data", "1024.data"]
    input_labels = [Path(name).stem for name in input_names]
    colors = {
        "Baseline": COLORS["ink"],
        "Optimization 1": COLORS["blue"],
        "Optimization 2": COLORS["gold"],
        "Parallel": COLORS["teal"],
    }

    summaries = {
        name: read_csv(directory / "summary.csv")
        for name, directory in stage_directories.items()
    }
    sequential_rows = {}
    for stage_name in ("Baseline", "Optimization 1", "Optimization 2"):
        by_input = {
            row["input"]: row
            for row in summaries[stage_name]
            if row["program"] == "pearson"
        }
        sequential_rows[stage_name] = [by_input[name] for name in input_names]

    parallel_rows = [
        row for row in summaries["Parallel"] if row["program"] == "pearson_par"
    ]
    thread_counts = sorted({int(row["threads"]) for row in parallel_rows})
    maximum_threads = max(thread_counts)
    parallel_by_key = {
        (row["input"], int(row["threads"])): row for row in parallel_rows
    }
    stage_rows = dict(sequential_rows)
    stage_rows["Parallel"] = [
        parallel_by_key[(name, maximum_threads)] for name in input_names
    ]

    metric_field = f"{metric}_elapsed_seconds"
    metric_title = metric.title()
    generated = []

    def emit(name, lines):
        write_svg(name, lines)
        generated.append(FIGURES / name)

    runtime_series = [
        (
            f"{stage} ({maximum_threads} threads)" if stage == "Parallel" else stage,
            [float(row[metric_field]) for row in stage_rows[stage]],
            colors[stage],
        )
        for stage in ("Baseline", "Optimization 1", "Optimization 2", "Parallel")
    ]
    lines = svg_start(1240, 620)
    panel_title(
        lines, 34, 36, "Pearson runtime across all implementation stages",
        f"{metric_title} elapsed time per execution; parallel stage uses {maximum_threads} threads",
    )
    series_legend(lines, 82, 94, runtime_series, spacing=270)
    multi_grouped_bars(
        lines, 28, 112, 1184, 470, input_labels, runtime_series,
        f"{metric_title} seconds", logarithmic=True,
    )
    emit("pearson_all_stages_runtime.svg", lines)

    baseline_times = [
        float(row[metric_field]) for row in stage_rows["Baseline"]
    ]
    speedup_series = []
    for stage in ("Baseline", "Optimization 1", "Optimization 2", "Parallel"):
        stage_times = [float(row[metric_field]) for row in stage_rows[stage]]
        speedup_series.append(
            (
                f"{stage} ({maximum_threads} threads)" if stage == "Parallel" else stage,
                [before / after for before, after in zip(baseline_times, stage_times)],
                colors[stage],
            )
        )
    speedup_maximum = math.ceil(
        max(value for _, values, _ in speedup_series for value in values) * 1.2
    )
    lines = svg_start(1240, 600)
    panel_title(
        lines, 34, 36, "Pearson speedup relative to the sequential baseline",
        f"Calculated from {metric} elapsed time; baseline is 1.0x",
    )
    series_legend(lines, 82, 94, speedup_series, spacing=270)
    multi_series_line_chart(
        lines, 28, 112, 1184, 440, input_labels, speedup_series,
        "Speedup over baseline", 0, max(2, speedup_maximum), suffix="x",
    )
    emit("pearson_all_stages_speedup.svg", lines)

    memory_series = []
    baseline_memory = [
        float(row["max_rss_kb"]) for row in stage_rows["Baseline"]
    ]
    for stage in ("Baseline", "Optimization 1", "Optimization 2", "Parallel"):
        values = [
            100 * float(row["max_rss_kb"]) / baseline
            for row, baseline in zip(stage_rows[stage], baseline_memory)
        ]
        memory_series.append(
            (
                f"{stage} ({maximum_threads} threads)" if stage == "Parallel" else stage,
                values,
                colors[stage],
            )
        )
    all_memory_values = [value for _, values, _ in memory_series for value in values]
    memory_minimum = math.floor(min(all_memory_values) - 1)
    memory_maximum = math.ceil(max(all_memory_values) + 1)
    lines = svg_start(1240, 600)
    panel_title(
        lines, 34, 36, "Pearson peak resident memory across stages",
        "Baseline normalized to 100%; magnified vertical scale",
    )
    series_legend(lines, 82, 94, memory_series, spacing=270)
    multi_series_line_chart(
        lines, 28, 112, 1184, 440, input_labels, memory_series,
        "Peak RSS relative to baseline", memory_minimum, memory_maximum,
        suffix="%",
    )
    emit("pearson_all_stages_memory.svg", lines)

    callgrind_fields = [
        ("Instructions", "instruction_refs"),
        ("Data refs", "data_refs"),
        ("D1 misses", "data_l1_misses"),
        ("LL misses", "data_ll_misses"),
        ("Branches", "branches"),
        ("Branch misses", "branch_mispredicts"),
    ]
    profiles = {}
    for stage in ("Baseline", "Optimization 1", "Optimization 2"):
        matches = [
            row for row in read_csv(stage_directories[stage] / "callgrind_metrics.csv")
            if row["program"] == "pearson" and row["input"] == "512.data"
        ]
        if len(matches) != 1:
            raise ValueError(f"Expected one matched Pearson Callgrind row for {stage}")
        profiles[stage] = matches[0]

    parallel_profiles = [
        row for row in read_csv(
            stage_directories["Parallel"] / "callgrind_metrics.csv"
        )
        if row["program"] == "pearson_par" and row["input"] == "512.data"
    ]
    parallel_profile = max(parallel_profiles, key=lambda row: int(row["threads"]))
    profile_thread_count = int(parallel_profile["threads"])
    profiles["Parallel"] = parallel_profile
    baseline_profile = profiles["Baseline"]
    callgrind_series = []
    for stage in ("Baseline", "Optimization 1", "Optimization 2", "Parallel"):
        label = (
            f"Parallel ({profile_thread_count} threads)"
            if stage == "Parallel" else stage
        )
        callgrind_series.append(
            (
                label,
                [
                    100 * float(profiles[stage][field]) / float(baseline_profile[field])
                    for _, field in callgrind_fields
                ],
                colors[stage],
            )
        )
    callgrind_maximum = 25 * math.ceil(
        max(value for _, values, _ in callgrind_series for value in values) / 25
    )
    lines = svg_start(1320, 620)
    panel_title(
        lines, 34, 36, "Matched Pearson Callgrind events on 512.data",
        "Baseline normalized to 100%; counts explain work, not native parallel runtime",
    )
    series_legend(lines, 88, 94, callgrind_series, spacing=285)
    multi_grouped_bars(
        lines, 28, 112, 1264, 470,
        [label for label, _ in callgrind_fields], callgrind_series,
        "Event count relative to baseline (%)", maximum=callgrind_maximum,
    )
    emit("pearson_all_stages_callgrind.svg", lines)

    dataset_colors = [COLORS["blue"], COLORS["teal"], COLORS["gold"], COLORS["coral"]]
    parallel_speedup_series = []
    parallel_efficiency_series = []
    for input_name, color in zip(input_names, dataset_colors):
        rows = [parallel_by_key[(input_name, threads)] for threads in thread_counts]
        parallel_speedup_series.append(
            (Path(input_name).stem, [float(row["speedup"]) for row in rows], color)
        )
        parallel_efficiency_series.append(
            (
                Path(input_name).stem,
                [float(row["efficiency_percent"]) for row in rows],
                color,
            )
        )

    thread_labels = [str(value) for value in thread_counts]
    lines = svg_start(1240, 620)
    panel_title(
        lines, 34, 36, "Parallel Pearson speedup by thread count",
        "Median elapsed time relative to the parallel implementation's one-thread run",
    )
    series_legend(lines, 88, 94, parallel_speedup_series, spacing=220)
    multi_series_line_chart(
        lines, 28, 112, 1184, 470, thread_labels, parallel_speedup_series,
        "Speedup", 0, maximum_threads, suffix="x",
        reference=("Ideal linear speedup", [float(value) for value in thread_counts]),
    )
    emit("parallel_speedup.svg", lines)

    lines = svg_start(1240, 600)
    panel_title(
        lines, 34, 36, "Parallel Pearson efficiency by thread count",
        "Efficiency = speedup / thread count; one-thread efficiency is 100%",
    )
    series_legend(lines, 88, 94, parallel_efficiency_series, spacing=220)
    multi_series_line_chart(
        lines, 28, 112, 1184, 440, thread_labels, parallel_efficiency_series,
        "Parallel efficiency", 0, 100, suffix="%",
    )
    emit("parallel_efficiency.svg", lines)

    cpu_inputs = ("512.data", "1024.data")
    cpu_series = []
    for input_name, color in zip(cpu_inputs, (COLORS["gold"], COLORS["coral"])):
        rows = [parallel_by_key[(input_name, threads)] for threads in thread_counts]
        cpu_series.append(
            (
                Path(input_name).stem,
                [float(row["avg_cpu_percent"]) for row in rows],
                color,
            )
        )
    cpu_maximum = 50 * math.ceil(
        max(value for _, values, _ in cpu_series for value in values) * 1.15 / 50
    )
    lines = svg_start(1240, 600)
    panel_title(
        lines, 34, 36, "Parallel Pearson CPU utilization on larger workloads",
        "100% is approximately one fully occupied CPU core",
    )
    series_legend(lines, 88, 94, cpu_series, spacing=260)
    multi_series_line_chart(
        lines, 28, 112, 1184, 440, thread_labels, cpu_series,
        "Average CPU utilization", 0, cpu_maximum, suffix="%",
        show_values=True,
    )
    emit("parallel_cpu_utilization.svg", lines)

    stage_metric_path = metric_directory / "pearson_stage_comparison.csv"
    with stage_metric_path.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = [
            "stage", "input", "threads", "mean_elapsed_seconds",
            "median_elapsed_seconds", "mean_speedup_over_baseline",
            "median_speedup_over_baseline", "avg_cpu_percent",
            "avg_user_seconds", "avg_system_seconds", "max_rss_kb",
            "max_rss_mib", "correctness",
        ]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for stage in ("Baseline", "Optimization 1", "Optimization 2", "Parallel"):
            for index, row in enumerate(stage_rows[stage]):
                baseline_row = stage_rows["Baseline"][index]
                writer.writerow({
                    "stage": stage,
                    "input": row["input"],
                    "threads": maximum_threads if stage == "Parallel" else 1,
                    "mean_elapsed_seconds": row["mean_elapsed_seconds"],
                    "median_elapsed_seconds": row["median_elapsed_seconds"],
                    "mean_speedup_over_baseline": (
                        f'{float(baseline_row["mean_elapsed_seconds"]) / float(row["mean_elapsed_seconds"]):.4f}'
                    ),
                    "median_speedup_over_baseline": (
                        f'{float(baseline_row["median_elapsed_seconds"]) / float(row["median_elapsed_seconds"]):.4f}'
                    ),
                    "avg_cpu_percent": row["avg_cpu_percent"],
                    "avg_user_seconds": row["avg_user_seconds"],
                    "avg_system_seconds": row["avg_system_seconds"],
                    "max_rss_kb": row["max_rss_kb"],
                    "max_rss_mib": f'{float(row["max_rss_kb"]) / 1024:.2f}',
                    "correctness": row["correctness"],
                })

    parallel_metric_path = metric_directory / "parallel_scaling.csv"
    with parallel_metric_path.open("w", newline="", encoding="utf-8") as stream:
        fieldnames = list(parallel_rows[0].keys())
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for input_name in input_names:
            for threads in thread_counts:
                writer.writerow(parallel_by_key[(input_name, threads)])

    callgrind_metric_path = metric_directory / "pearson_callgrind_stages.csv"
    with callgrind_metric_path.open("w", newline="", encoding="utf-8") as stream:
        event_fields = [field for _, field in callgrind_fields]
        fieldnames = ["stage", "input", "threads"]
        fieldnames += event_fields
        fieldnames += [f"{field}_percent_of_baseline" for field in event_fields]
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for stage in ("Baseline", "Optimization 1", "Optimization 2", "Parallel"):
            profile = profiles[stage]
            row = {
                "stage": stage,
                "input": profile["input"],
                "threads": profile_thread_count if stage == "Parallel" else 1,
            }
            for field in event_fields:
                row[field] = profile[field]
                row[f"{field}_percent_of_baseline"] = (
                    f'{100 * float(profile[field]) / float(baseline_profile[field]):.2f}'
                )
            writer.writerow(row)

    print(
        "Generated the complete Pearson report suite using "
        f"{maximum_threads} threads for cross-stage parallel comparisons."
    )
    print(f"Elapsed-time metric: {metric}")
    for path in generated:
        print(f"  {path}")
    print(f"  {stage_metric_path}")
    print(f"  {parallel_metric_path}")
    print(f"  {callgrind_metric_path}")


def main():
    global FIGURES

    args = parse_args()
    if args.list_stages:
        for stage in available_stages():
            callgrind_status = (
                "with Callgrind" if (stage / "callgrind_metrics.csv").is_file()
                else "summary only"
            )
            print(f"{stage.name}\t{callgrind_status}")
        return

    if args.report_suite:
        generate_report_suite(args.metric, args.output_dir)
        return

    first_directory = resolve_stage(args.first_stage)
    second_directory = resolve_stage(args.second_stage)
    if first_directory == second_directory:
        raise ValueError("Select two different profiling stages to compare")

    first_name = args.first_label or display_name(first_directory)
    second_name = args.second_label or display_name(second_directory)
    prefix = filename_part(
        args.prefix or f"{first_directory.name}-vs-{second_directory.name}"
    )
    FIGURES = args.output_dir.expanduser().resolve()
    FIGURES.mkdir(parents=True, exist_ok=True)

    first_summary = read_csv(first_directory / "summary.csv")
    second_summary = read_csv(second_directory / "summary.csv")
    metric_field = f"{args.metric}_elapsed_seconds"
    metric_title = args.metric.title()
    generated = []

    first_callgrind_path = first_directory / "callgrind_metrics.csv"
    second_callgrind_path = second_directory / "callgrind_metrics.csv"
    first_callgrind = read_csv(first_callgrind_path) if first_callgrind_path.is_file() else []
    second_callgrind = read_csv(second_callgrind_path) if second_callgrind_path.is_file() else []
    callgrind_fields = [
        ("Instructions", "instruction_refs"),
        ("Data refs", "data_refs"),
        ("Branches", "branches"),
        ("Branch misses", "branch_mispredicts"),
        ("LL data misses", "data_ll_misses"),
        ("D1 data misses", "data_l1_misses"),
    ]

    def emit(name, lines):
        write_svg(name, lines)
        generated.append(FIGURES / name)

    first_programs = {row["program"] for row in first_summary}
    second_programs = {row["program"] for row in second_summary}
    program_colors = (("pearson", COLORS["blue"]), ("blur", COLORS["teal"]))
    shared_programs = [
        (program, color) for program, color in program_colors
        if program in first_programs and program in second_programs
    ]
    if not shared_programs:
        raise ValueError("The selected stages do not contain any shared programs")
    for program, _ in program_colors:
        if program not in first_programs or program not in second_programs:
            print(
                f"Warning: skipping {program} because it is not present in both stages."
            )

    for program, color in shared_programs:
        first_rows, second_rows = aligned_rows(
            first_summary, second_summary, program
        )
        labels = [Path(row["input"]).stem for row in first_rows]
        first_times = [float(row[metric_field]) for row in first_rows]
        second_times = [float(row[metric_field]) for row in second_rows]

        lines = svg_start(1000, 560)
        panel_title(
            lines, 32, 34,
            f"{program.title()} runtime: {first_name} vs {second_name}",
            f"{metric_title} normalized elapsed time; lower is better",
        )
        grouped_log_bars(
            lines, 30, 76, 940, 450, labels, first_times, second_times,
            first_name, second_name, f"{metric_title} seconds",
        )
        emit(f"{prefix}_{program}_runtime.svg", lines)

        speedups = [
            before / after for before, after in zip(first_times, second_times)
        ]
        speedup_maximum = max(1.1, math.ceil(max(speedups) * 1.15 * 10) / 10)
        lines = svg_start(1000, 500)
        panel_title(
            lines, 32, 34,
            f"{program.title()} speedup: {second_name} over {first_name}",
            f"Calculated from {args.metric} elapsed time; above 1.0x is faster",
        )
        line_chart(
            lines, 34, 80, 920, 380, labels, speedups,
            color, speedup_maximum, "Speedup",
        )
        emit(f"{prefix}_{program}_speedup.svg", lines)

        first_memory = [100.0 for _ in first_rows]
        second_memory = [
            100 * float(after["max_rss_kb"]) / float(before["max_rss_kb"])
            for before, after in zip(first_rows, second_rows)
        ]
        memory_maximum = max(
            125.0, math.ceil(max(first_memory + second_memory) / 25) * 25
        )
        lines = svg_start(1000, 560)
        panel_title(
            lines, 32, 34,
            f"{program.title()} peak memory: {first_name} vs {second_name}",
            f"{first_name} normalized to 100%; lower is better",
        )
        grouped_percent_bars(
            lines, 28, 80, 944, 440, labels,
            first_memory, second_memory, first_name, second_name, memory_maximum,
        )
        emit(f"{prefix}_{program}_memory.svg", lines)

        first_profiles = [
            row for row in first_callgrind if row["program"] == program
        ]
        second_profiles = [
            row for row in second_callgrind if row["program"] == program
        ]
        if len(first_profiles) != 1 or len(second_profiles) != 1:
            print(
                f"Warning: skipping {program} Callgrind chart because each stage "
                "must contain exactly one matching profile."
            )
            continue

        first_profile = first_profiles[0]
        second_profile = second_profiles[0]
        if first_profile["input"] != second_profile["input"]:
            print(
                f"Warning: skipping {program} Callgrind chart: inputs differ "
                f"({first_profile['input']} vs {second_profile['input']})."
            )
            continue

        normalized_first = [100.0 for _ in callgrind_fields]
        normalized_second = [
            100 * float(second_profile[field]) / float(first_profile[field])
            for _, field in callgrind_fields
        ]
        callgrind_maximum = max(
            125.0,
            math.ceil(max(normalized_first + normalized_second) / 25) * 25,
        )
        lines = svg_start(1100, 560)
        panel_title(
            lines, 32, 34,
            f"{program.title()} Callgrind events: {first_name} vs {second_name}",
            f"Matched {first_profile['input']} input; {first_name} normalized to 100%",
        )
        grouped_percent_bars(
            lines, 28, 80, 1044, 440,
            [label for label, _ in callgrind_fields],
            normalized_first, normalized_second,
            first_name, second_name, callgrind_maximum,
        )
        emit(f"{prefix}_{program}_callgrind.svg", lines)

    print(f"Compared {first_directory.name} with {second_directory.name}")
    print(f"Elapsed-time metric: {args.metric}")
    print(f"Generated {len(generated)} figure(s) in {FIGURES}")
    for path in generated:
        print(f"  {path.name}")


if __name__ == "__main__":
    main()
