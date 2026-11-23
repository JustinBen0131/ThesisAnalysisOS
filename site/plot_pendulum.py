"""Plot the recorded one-swing sensitivity tests. Requires Matplotlib."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib


def figure_inputs(source, renderer):
    return {"SourceSHA256": hashlib.sha256(source).hexdigest(),
            "RendererSHA256": hashlib.sha256(renderer.read_bytes()).hexdigest()}


def figure_issue(figure, source, renderer):
    """Read PNG chunks without importing Matplotlib, and check both build inputs."""
    data = figure.read_bytes()
    expected = figure_inputs(source, renderer)
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "the pendulum figure is not a PNG"
    pos = 8
    seen = {}
    have_pixels = False
    while pos + 12 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, pos)
        end = pos + 8 + length
        if end + 4 > len(data) or zlib.crc32(data[pos + 4:end]) != int.from_bytes(data[end:end + 4], "big"):
            return "the pendulum figure contains a damaged PNG chunk"
        body = data[pos + 8:end]
        if pos == 8 and (kind != b"IHDR" or length != 13 or 0 in struct.unpack_from(">II", body)):
            return "the pendulum figure has an invalid image header"
        pos = end + 4
        if kind == b"IDAT":
            have_pixels |= bool(body)
        elif kind == b"tEXt":
            key, _, value = body.partition(b"\0")
            name = key.decode("latin1")
            if name in expected:
                if name in seen:
                    return f"duplicate {name} in the pendulum figure"
                seen[name] = value
        if kind == b"IEND":
            if body or pos != len(data) or not have_pixels:
                return "the pendulum figure has an invalid ending"
            for key, value in expected.items():
                if seen.get(key) != value.encode("ascii"):
                    return f"pendulum figure needs regeneration ({key} differs)"
            return None
    return "the pendulum figure is incomplete"


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MultipleLocator

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("evals/results/measurement_audit.json"))
    parser.add_argument("--output", type=Path, default=Path("site/assets/pendulum-sensitivity.png"))
    args = parser.parse_args()
    source = args.input.read_bytes()
    record = json.loads(source)
    by_id = {case["id"]: case for case in record["cases"]}
    baseline = by_id["baseline"]["g"]
    lengths = [float(length) for length, _ in record["baseline_rows"]]
    low, high = 9.6 - baseline, 10.0 - baseline
    series = (
        ("0.95", "−5%", "#70d9bb", "s", "-"),
        ("0.99", "−1%", "#70d9bb", "s", "--"),
        ("1.01", "+1%", "#ffcb78", "D", "--"),
        ("1.05", "+5%", "#ffcb78", "D", "-"),
    )
    paper, ink, quiet = "#101d16", "#eff7f1", "#aabfb3"
    fig, ax = plt.subplots(figsize=(6.4, 5.05), facecolor=paper)
    fig.subplots_adjust(left=.17, right=.96, top=.74, bottom=.205)
    ax.set_facecolor(paper)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_locator(MultipleLocator(.2))
    ax.grid(axis="y", color="#2b4336", linewidth=.8)
    ax.axhline(0, color="#859a8f", linewidth=.9, zorder=1)
    for threshold in (low, high):
        ax.axhline(threshold, color=quiet, linestyle=":", linewidth=1.3, zorder=2)

    for scale, label, color, marker, line in series:
        shift = [by_id[f"row-{i}-{scale}"]["g"] - baseline for i in range(1, len(lengths) + 1)]
        ax.plot(lengths, shift, label=label, color=color, marker=marker,
                linestyle=line, linewidth=1.8, markersize=5.8, markeredgewidth=1.25,
                markerfacecolor=color if line == "-" else paper)

    ax.set(xlim=(.16, 1.24), ylim=(-.43, .46), xticks=lengths)
    ax.set_xticklabels([f"{length:.2f}" for length in lengths])
    ax.set_xlabel("Length of edited swing (m)", color=ink, fontsize=12, labelpad=9)
    ax.set_ylabel("Change in fitted gravity (m/s²)", color=ink, fontsize=12, labelpad=9)
    ax.tick_params(axis="both", colors=ink, labelsize=11, length=0, pad=5)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#65786c")
    ax.text(.185, high + .016, "g = 10.0", color=quiet, fontsize=10, va="bottom")
    ax.text(.185, low - .017, "g = 9.6", color=quiet, fontsize=10, va="top")

    fig.text(.069, .929, "Longer swings shift the fit more", color=ink, fontsize=19, weight="bold")
    fig.text(.069, .872, "One measured period changes in each trial.", color=quiet, fontsize=12)
    ax.legend(title="Period edit", ncols=4, loc="lower left", bbox_to_anchor=(0, 1.029),
              borderaxespad=0, frameon=False, labelcolor=ink, fontsize=11,
              title_fontsize=10, handlelength=2.0, columnspacing=1.22).get_title().set_color(quiet)
    fig.text(.069, .061, f"Baseline g = {baseline:.4f} m/s². Dotted lines mark the gravity limits.", color=quiet, fontsize=10)
    fig.text(.069, .025, "The check also applies a separate uncertainty limit.", color=quiet, fontsize=10)
    fig.savefig(args.output, dpi=180, facecolor=paper, metadata={
        **figure_inputs(source, Path(__file__)),
        "Title": "Pendulum sensitivity to one-swing period edits",
        "Description": "Gravity shifts from recorded one-swing period edits with fixed baseline gravity thresholds.",
    })


if __name__ == "__main__":
    main()
