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
        "second_stage", nargs="?", default="optim1",
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
