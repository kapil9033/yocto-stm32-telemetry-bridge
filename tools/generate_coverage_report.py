#!/usr/bin/env python3
"""Render the host test results and native coverage summary as standalone HTML."""

import argparse
from html import escape
from pathlib import Path
import re
import xml.etree.ElementTree as ET


NATIVE_SOURCE_BY_TEST = {
    "gateway_protocol_test": "gatewayd/src/frame_protocol.cpp",
    "telemetry_protocol_test": "stm32-firmware/Core/Src/telemetry_protocol.c",
    "firmware_package_test": "stm32-firmware/Core/Src/firmware_package.c",
    "sensors_driver_test": "stm32-firmware/Core/Src/sensors_driver.c",
}


def read_python_results(path):
    root = ET.parse(path).getroot()
    cases = []
    for case in root.iter("testcase"):
        skipped_node = case.find("skipped")
        skipped = skipped_node is not None
        failed = case.find("failure") is not None or case.find("error") is not None
        status = "Skipped" if skipped else "Failed" if failed else "Passed"
        cases.append({
            "suite": case.get("classname", "Python"),
            "name": case.get("name", "unnamed test"),
            "status": status,
            "time": float(case.get("time", "0") or 0),
            "detail": (
                (skipped_node.get("message") or skipped_node.text or "").strip()
                if skipped_node is not None else ""
            ),
        })
    return cases


def read_native_results(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    cases = []
    pattern = re.compile(
        r"^\s*\d+/\d+\s+Test\s+#\d+:\s+(\S+).*?\b(Passed|Failed|Not Run)\b",
        re.MULTILINE,
    )
    for name, result in pattern.findall(text):
        status = "Skipped" if result == "Not Run" else result
        cases.append({"name": name, "status": status})
    return cases


def read_coverage(path):
    files = {}
    current = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        file_match = re.match(r"File '(.+)'", line)
        if file_match:
            current = file_match.group(1)
            files[current] = {}
            continue
        if current is None:
            continue
        for metric, pattern in (
            ("line", r"Lines executed:([\d.]+)%"),
            ("branch", r"Branches executed:([\d.]+)%"),
            ("mcdc", r"Condition outcomes covered:([\d.]+)%"),
        ):
            match = re.match(pattern, line)
            if match:
                files[current][metric] = float(match.group(1))
    return files


def percentage_bar(value):
    if value is None:
        return '<span class="na">N/A</span>'
    width = max(0.0, min(100.0, value))
    return (
        '<div class="bar-wrap"><div class="bar" style="width:'
        f'{width:.2f}%"></div></div><span class="percent">{value:.2f}%</span>'
    )


def status_badge(status):
    return f'<span class="badge {escape(status.lower())}">{escape(status)}</span>'


def render(args):
    python_cases = read_python_results(args.python_results)
    native_cases = read_native_results(args.native_results)
    coverage = read_coverage(args.coverage_summary)

    python_counts = {
        status: sum(case["status"] == status for case in python_cases)
        for status in ("Passed", "Failed", "Skipped")
    }
    native_counts = {
        status: sum(case["status"] == status for case in native_cases)
        for status in ("Passed", "Failed", "Skipped")
    }

    native_rows = []
    for case in native_cases:
        source_suffix = NATIVE_SOURCE_BY_TEST.get(case["name"])
        source_path = next(
            (name for name in coverage if source_suffix and name.endswith(source_suffix)),
            None,
        )
        metrics = coverage.get(source_path, {})
        native_rows.append(
            "<tr>"
            f"<td><code>{escape(case['name'])}</code></td>"
            f"<td>{status_badge(case['status'])}</td>"
            f"<td><code>{escape(source_suffix or 'unmapped')}</code></td>"
            f"<td>{percentage_bar(metrics.get('line'))}</td>"
            f"<td>{percentage_bar(metrics.get('branch'))}</td>"
            f"<td>{percentage_bar(metrics.get('mcdc'))}</td>"
            "</tr>"
        )

    python_groups = {"Unit": [], "Integration": [], "System": []}
    for case in python_cases:
        level = next(
            (name for name in ("Integration", "System") if f".{name.lower()}." in f".{case['suite']}."),
            "Unit",
        )
        python_groups[level].append(case)

    def python_table_rows(cases):
        rows = []
        for case in cases:
            detail = escape(case["detail"])
            rows.append(
            "<tr>"
            f"<td><code>{escape(case['suite'])}::{escape(case['name'])}</code></td>"
            f"<td>{status_badge(case['status'])}</td>"
            f"<td>{case['time']:.3f}s</td>"
            f"<td>{detail}</td>"
            "</tr>"
            )
        return "".join(rows)

    def group_count(level, status):
        return sum(case["status"] == status for case in python_groups[level])

    summary_link = "../unit-mcdc-coverage/gcov-report/summary.txt"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Host Test Coverage Report</title>
  <style>
    :root {{ color-scheme: light; font: 15px/1.5 system-ui, sans-serif; color: #18212b; background: #f3f6f9; }}
    body {{ margin: 0; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 56px; }}
    h1 {{ margin: 0 0 4px; font-size: 2rem; }}
    h2 {{ margin: 32px 0 12px; font-size: 1.3rem; }}
    p {{ color: #526171; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(175px,1fr)); gap: 12px; margin: 22px 0; }}
    .card {{ background: white; border: 1px solid #dce4ec; border-radius: 10px; padding: 16px; box-shadow: 0 1px 2px #1020300a; }}
    .card strong {{ display: block; font-size: 1.7rem; }}
    .card span {{ color: #526171; }}
    .table-wrap {{ overflow-x: auto; background: white; border: 1px solid #dce4ec; border-radius: 10px; }}
    table {{ border-collapse: collapse; width: 100%; min-width: 820px; }}
    th,td {{ padding: 11px 12px; border-bottom: 1px solid #e7edf2; text-align: left; vertical-align: middle; }}
    th {{ background: #f8fafc; font-size: .84rem; color: #526171; }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{ font-size: .9em; }}
    .badge {{ display: inline-block; padding: 2px 9px; border-radius: 20px; font-size: .8rem; font-weight: 650; }}
    .passed {{ color: #12613a; background: #e0f5e9; }} .failed {{ color: #9b1c1c; background: #fde7e7; }} .skipped {{ color: #77550a; background: #fff2cb; }}
    .bar-wrap {{ display: inline-block; vertical-align: middle; width: 90px; height: 9px; margin-right: 7px; background: #e7edf2; border-radius: 8px; overflow: hidden; }}
    .bar {{ height: 100%; background: linear-gradient(90deg,#14a36f,#54c78f); border-radius: inherit; }}
    .percent {{ display: inline-block; min-width: 55px; font-variant-numeric: tabular-nums; }}
    .na {{ color: #82909d; }} .note {{ margin-top: 14px; padding: 12px 14px; background: #eaf2fb; border-radius: 8px; }}
    a {{ color: #1769aa; }} footer {{ margin-top: 28px; color: #697887; font-size: .9rem; }}
  </style>
</head>
<body><main>
  <h1>Host Test Coverage</h1>
  <p>Coverage and test outcomes collected by <code>run_host_tests.sh</code>.</p>
  <section class="cards" aria-label="Test totals">
    <div class="card"><strong>{len(python_cases)}</strong><span>pytest cases (Python)</span></div>
    <div class="card"><strong>{group_count('Unit', 'Passed')}/{len(python_groups['Unit'])}</strong><span>Unit tests passed</span></div>
    <div class="card"><strong>{group_count('Integration', 'Passed')}/{len(python_groups['Integration'])}</strong><span>Integration tests passed</span></div>
    <div class="card"><strong>{group_count('System', 'Passed')}/{len(python_groups['System'])}</strong><span>System tests passed</span></div>
    <div class="card"><strong>{native_counts['Passed']}/{len(native_cases)}</strong><span>Native tests passed</span></div>
  </section>

  <h2>Native coverage by test step</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Test step</th><th>Result</th><th>Source file</th><th>Lines</th><th>Branches</th><th>MC/DC</th></tr></thead>
    <tbody>{''.join(native_rows)}</tbody>
  </table></div>
  <p class="note">MC/DC is masking modified condition/decision coverage. Coverage is collected for native C/C++ production files. Python and shell test cases are listed below; their source coverage is not measured by this GCC report.</p>

  <h2>Unit tests (pytest)</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Test case</th><th>Result</th><th>Duration</th><th>Details</th></tr></thead>
    <tbody>{python_table_rows(python_groups['Unit'])}</tbody>
  </table></div>

  <h2>Integration tests (pytest)</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Test case</th><th>Result</th><th>Duration</th><th>Details</th></tr></thead>
    <tbody>{python_table_rows(python_groups['Integration'])}</tbody>
  </table></div>

  <h2>System tests (pytest)</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Test case</th><th>Result</th><th>Duration</th><th>Details</th></tr></thead>
    <tbody>{python_table_rows(python_groups['System'])}</tbody>
  </table></div>

  <footer>Raw native summary: <a href="{summary_link}">summary.txt</a></footer>
</main></body></html>
"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-results", type=Path, required=True)
    parser.add_argument("--native-results", type=Path, required=True)
    parser.add_argument("--coverage-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    render(parser.parse_args())


if __name__ == "__main__":
    main()
