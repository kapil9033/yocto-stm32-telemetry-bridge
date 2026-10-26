#!/usr/bin/env python3
"""Generate a standalone graphical design and traceability report."""

import argparse
from html import escape
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def read_traceability(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    rows = []
    in_table = False
    for line in lines:
        if line.startswith("| ID | Parent |"):
            in_table = True
            continue
        if in_table and re.match(r"^\|\s*:?-+", line):
            continue
        if in_table and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) == 7:
                rows.append(dict(zip(
                    ("id", "parent", "requirement", "design", "implementation", "verification", "status"),
                    cells,
                )))
            continue
        if in_table:
            break
    if not rows:
        raise ValueError(f"No requirement matrix rows found in {path}")
    return rows


def resolve_repo_file(value):
    candidate = ROOT / value
    if candidate.is_file():
        return candidate
    for prefix in ("stm32-firmware", "gatewayd", "meta-telemetry-bridge"):
        candidate = ROOT / prefix / value
        if candidate.is_file():
            return candidate
    matches = list(ROOT.rglob(Path(value).name))
    matches = [m for m in matches if ".git" not in m.parts and "build" not in m.parts]
    return matches[0] if len(matches) == 1 and matches[0].is_file() else None


def render_inline(value, output_dir):
    parts = []
    cursor = 0
    for match in re.finditer(r"`([^`]+)`", value):
        parts.append(escape(value[cursor:match.start()]))
        label = match.group(1)
        path_value = label.split("::", 1)[0]
        target = resolve_repo_file(path_value)
        if target:
            href = Path(__import__("os").path.relpath(target, output_dir)).as_posix()
            parts.append(f'<a class="file-link" href="{escape(href, quote=True)}"><code>{escape(label)}</code></a>')
        else:
            parts.append(f"<code>{escape(label)}</code>")
        cursor = match.end()
    parts.append(escape(value[cursor:]))
    return "".join(parts)


def render(rows, output):
    output_dir = output.parent.resolve()
    row_html = []
    level_counts = {"unit": 0, "integration": 0, "system": 0, "hil": 0}
    for item in rows:
        evidence = item["verification"].lower()
        levels = [level for level in level_counts if f"tests/{level}" in evidence]
        if "tests/hil" in evidence:
            levels.append("hil")
        for level in set(levels):
            level_counts[level] += 1
        kind = "security" if item["id"].startswith("SEC-") else "software" if item["id"].startswith("SWR-") else "system"
        chips = "".join(f'<span class="chip {level}">{level.title()}</span>' for level in dict.fromkeys(levels))
        row_html.append(
            f'<tr data-kind="{kind}" data-id="{escape(item["id"].lower())}" '
            f'data-text="{escape((item["id"] + " " + item["parent"] + " " + item["requirement"] + " " + item["design"] + " " + item["implementation"] + " " + item["verification"] + " " + item["status"]).lower(), quote=True)}">'
            f'<td><strong class="req-id {kind}">{escape(item["id"])}</strong><small>Parent: {render_inline(item["parent"], output_dir)}</small></td>'
            f'<td>{render_inline(item["requirement"], output_dir)}</td>'
            f'<td>{render_inline(item["design"], output_dir)}</td>'
            f'<td>{render_inline(item["implementation"], output_dir)}</td>'
            f'<td>{render_inline(item["verification"], output_dir)}<div class="chips">{chips or "<span class=\"muted\">No test path linked</span>"}</div></td>'
            f'<td>{render_inline(item["status"], output_dir)}</td></tr>'
        )

    template = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Software Design & Traceability</title>
<style>
:root{font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:#17212b;background:#f2f5f8;--blue:#1769aa;--ink:#17212b;--muted:#5e6c78;--line:#dbe3ea;--panel:#fff}
*{box-sizing:border-box}body{margin:0}header{background:linear-gradient(120deg,#102b46,#1769aa);color:#fff;padding:30px max(24px,calc((100vw - 1480px)/2)) 28px}header h1{margin:0;font-size:2rem}header p{margin:5px 0 0;color:#e0efff}.wrap{max-width:1480px;margin:auto;padding:24px}.toplinks{display:flex;gap:12px;flex-wrap:wrap;margin-top:16px}.toplinks a{color:#fff;border:1px solid #ffffff70;border-radius:7px;padding:5px 10px;text-decoration:none}.notice{background:#fff7db;border:1px solid #f0d58a;padding:12px 16px;border-radius:9px;color:#624d13;margin-bottom:20px}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0 24px}.metric,.panel{background:var(--panel);border:1px solid var(--line);border-radius:11px;box-shadow:0 2px 6px #1223340a}.metric{padding:15px 17px}.metric strong{display:block;font-size:1.7rem}.metric span{color:var(--muted)}h2{margin:30px 0 12px;font-size:1.35rem}.panel{padding:18px 20px}.diagram{overflow-x:auto}.diagram svg{display:block;width:100%;min-width:760px;height:auto}.node{fill:#fff;stroke:#b8c9d9;stroke-width:2}.node-blue{fill:#eaf4fc;stroke:#6da6d0}.node-purple{fill:#f4efff;stroke:#a28bd3}.node-green{fill:#eaf7ef;stroke:#79b68c}.node-gray{fill:#f0f3f6;stroke:#aebbc7}.arrow{stroke:#58758c;stroke-width:2.4;fill:none;marker-end:url(#arrow)}.dash{stroke-dasharray:7 6}.svg-title{font-weight:700;fill:#182b3a;font-size:15px}.svg-sub{fill:#5a6d7d;font-size:12px}.section-head{display:flex;align-items:end;justify-content:space-between;gap:12px;flex-wrap:wrap}.section-head p{color:var(--muted);margin:0 0 12px}.controls{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.controls input,.controls select{font:inherit;border:1px solid #bdcbd6;border-radius:7px;padding:8px 10px;background:white}.controls input{min-width:min(360px,100%)}.tablebox{overflow:auto;background:white;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;table-layout:fixed;width:100%;min-width:1350px}th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #e7edf2;overflow-wrap:anywhere;word-break:break-word}th{background:#edf3f7;color:#405363;position:sticky;top:0;z-index:1;font-size:.85rem}tr:last-child td{border:0}td code,.file-link{overflow-wrap:anywhere;word-break:break-word}td:first-child{min-width:0}.req-id{font-size:1rem}.req-id.system{color:#15659e}.req-id.security{color:#7544a1}.req-id.software{color:#a45b13}td small{display:block;color:var(--muted);margin-top:5px}.chips{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}.chip{font-size:.72rem;border-radius:99px;padding:2px 8px;background:#e8eef4;color:#405263}.chip.unit{background:#e4f2fb;color:#155c8b}.chip.integration{background:#e6f4ec;color:#206741}.chip.system{background:#f0eafa;color:#684395}.chip.hil{background:#fff0d7;color:#875500}.file-link{color:#155d91;text-decoration:none}.file-link:hover{text-decoration:underline}.muted{color:#81909c}.empty{display:none;text-align:center;padding:30px;color:var(--muted)}footer{color:#657481;margin:24px 0 8px;font-size:.9rem}
@media(max-width:700px){.wrap{padding:16px}header{padding:24px 16px}header h1{font-size:1.6rem}}
</style></head><body>
<header><div class="wrap"><h1>Software Design & Traceability</h1><p>Architecture, detailed design, and V-model links from requirement to implementation and test evidence.</p>
<nav class="toplinks"><a href="system-architecture.md">System architecture</a><a href="software-detailed-design.md">Software detailed design</a><a href="v-model-traceability.md">Traceability source</a></nav></div></header>
<main class="wrap"><div class="notice"><strong>Baseline status:</strong> Requirements are derived from the current repository implementation and need stakeholder review. Test links identify mapped evidence; this page does not report whether tests passed or establish product acceptance.</div>
<section class="metrics" aria-label="Traceability totals"><div class="metric"><strong>__TOTAL__</strong><span>requirement records</span></div><div class="metric"><strong>__UNIT__</strong><span>records linked to unit tests</span></div><div class="metric"><strong>__INTEGRATION__</strong><span>records linked to integration tests</span></div><div class="metric"><strong>__SYSTEM__</strong><span>records linked to system tests</span></div><div class="metric"><strong>__HIL__</strong><span>records linked to HIL tests</span></div></section>
<h2>System architecture view</h2><section class="panel diagram"><svg viewBox="0 0 1180 300" role="img" aria-label="System architecture showing sensors flowing through STM32 firmware, USB serial, Raspberry Pi gateway and system journal; build host builds the Yocto image."><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#58758c"/></marker></defs>
<rect class="node node-gray" x="25" y="85" width="190" height="106" rx="12"/><text class="svg-title" x="120" y="121" text-anchor="middle">Sensors &amp; controls</text><text class="svg-sub" x="120" y="146" text-anchor="middle">ADC · RTC · DHT11 · button</text><text class="svg-sub" x="120" y="165" text-anchor="middle">LCD feedback</text>
<rect class="node node-blue" x="275" y="85" width="205" height="106" rx="12"/><text class="svg-title" x="377" y="121" text-anchor="middle">STM32F446RE</text><text class="svg-sub" x="377" y="146" text-anchor="middle">FreeRTOS telemetry task</text><text class="svg-sub" x="377" y="165" text-anchor="middle">COBS + CRC-16 frame</text>
<rect class="node node-gray" x="540" y="85" width="175" height="106" rx="12"/><text class="svg-title" x="627" y="121" text-anchor="middle">USB CDC / UART</text><text class="svg-sub" x="627" y="146" text-anchor="middle">115200 baud · /dev/ttyACM0</text><text class="svg-sub" x="627" y="165" text-anchor="middle">one-way telemetry</text>
<rect class="node node-green" x="775" y="85" width="190" height="106" rx="12"/><text class="svg-title" x="870" y="121" text-anchor="middle">Raspberry Pi / Yocto</text><text class="svg-sub" x="870" y="146" text-anchor="middle">gatewayd + systemd</text><text class="svg-sub" x="870" y="165" text-anchor="middle">decode · validate · print</text>
<rect class="node node-purple" x="1025" y="85" width="130" height="106" rx="12"/><text class="svg-title" x="1090" y="121" text-anchor="middle">Journal</text><text class="svg-sub" x="1090" y="146" text-anchor="middle">service output</text>
<path class="arrow" d="M215 138 H268"/><path class="arrow" d="M480 138 H533"/><path class="arrow" d="M715 138 H768"/><path class="arrow" d="M965 138 H1018"/>
<rect class="node node-gray" x="335" y="225" width="350" height="54" rx="10"/><text class="svg-title" x="510" y="248" text-anchor="middle">Development host · BitBake · Yocto layer</text><text class="svg-sub" x="510" y="267" text-anchor="middle">builds/packages the image and gateway; not in telemetry path</text><path class="arrow dash" d="M685 250 C790 250 850 225 870 198"/>
</svg></section>
<h2>Software component design</h2><section class="panel diagram"><svg viewBox="0 0 1160 340" role="img" aria-label="Software component view connecting STM32 startup, telemetry task, sensor/display/protocol modules, UART, gateway serial loop, frame decoder, telemetry output, and secure boot verification."><defs><marker id="arrow3" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#58758c"/></marker></defs>
<text class="svg-title" x="250" y="28" text-anchor="middle">STM32 application</text><text class="svg-title" x="870" y="28" text-anchor="middle">Yocto Linux gateway</text>
<rect class="node node-blue" x="35" y="55" width="175" height="62" rx="9"/><text class="svg-title" x="122" y="81" text-anchor="middle">main.c</text><text class="svg-sub" x="122" y="101" text-anchor="middle">HAL + RTOS startup</text>
<rect class="node node-blue" x="260" y="55" width="190" height="62" rx="9"/><text class="svg-title" x="355" y="81" text-anchor="middle">telemetry_task.c</text><text class="svg-sub" x="355" y="101" text-anchor="middle">periodic sample / transmit</text><path class="arrow" d="M210 86 H253"/>
<rect class="node node-gray" x="260" y="145" width="190" height="58" rx="9"/><text class="svg-title" x="355" y="170" text-anchor="middle">sensors_driver.c</text><text class="svg-sub" x="355" y="189" text-anchor="middle">DS3231 · DHT11</text><path class="arrow" d="M355 117 V138"/>
<rect class="node node-gray" x="35" y="145" width="175" height="58" rx="9"/><text class="svg-title" x="122" y="170" text-anchor="middle">ADC / button</text><text class="svg-sub" x="122" y="189" text-anchor="middle">HAL + DMA + GPIO</text><path class="arrow" d="M210 174 H253"/>
<rect class="node node-gray" x="35" y="225" width="175" height="58" rx="9"/><text class="svg-title" x="122" y="250" text-anchor="middle">lcd1602.c</text><text class="svg-sub" x="122" y="269" text-anchor="middle">local status output</text><path class="arrow" d="M260 185 C230 185 220 240 218 250"/>
<rect class="node node-blue" x="260" y="225" width="190" height="58" rx="9"/><text class="svg-title" x="355" y="250" text-anchor="middle">telemetry_protocol.c</text><text class="svg-sub" x="355" y="269" text-anchor="middle">CRC16 + COBS</text><path class="arrow" d="M355 117 V218"/>
<rect class="node node-gray" x="500" y="225" width="125" height="58" rx="9"/><text class="svg-title" x="562" y="250" text-anchor="middle">USART2</text><text class="svg-sub" x="562" y="269" text-anchor="middle">115200 8N1</text><path class="arrow" d="M450 254 H493"/>
<rect class="node node-green" x="675" y="55" width="175" height="62" rx="9"/><text class="svg-title" x="762" y="81" text-anchor="middle">main.cpp</text><text class="svg-sub" x="762" y="101" text-anchor="middle">TTY read / framing loop</text>
<rect class="node node-green" x="675" y="145" width="175" height="58" rx="9"/><text class="svg-title" x="762" y="170" text-anchor="middle">frame_protocol.cpp</text><text class="svg-sub" x="762" y="189" text-anchor="middle">COBS · length · CRC</text><path class="arrow" d="M762 117 V138"/>
<rect class="node node-green" x="900" y="145" width="215" height="58" rx="9"/><text class="svg-title" x="1007" y="170" text-anchor="middle">telemetry.h + print</text><text class="svg-sub" x="1007" y="189" text-anchor="middle">payload decode · stdout</text><path class="arrow" d="M850 174 H893"/>
<rect class="node node-purple" x="900" y="55" width="215" height="62" rx="9"/><text class="svg-title" x="1007" y="81" text-anchor="middle">systemd journal</text><text class="svg-sub" x="1007" y="101" text-anchor="middle">captured service output</text><path class="arrow" d="M1007 145 V124"/>
<path class="arrow" d="M625 254 C650 254 652 86 668 86"/>
<rect class="node node-purple" x="35" y="300" width="175" height="30" rx="8"/><text class="svg-sub" x="122" y="320" text-anchor="middle">bootloader/main.c</text><rect class="node node-purple" x="260" y="300" width="190" height="30" rx="8"/><text class="svg-sub" x="355" y="320" text-anchor="middle">firmware_package.c verifier</text><path class="arrow" d="M210 315 H253"/>
</svg></section>
<h2>V-model verification view</h2><section class="panel diagram"><svg viewBox="0 0 1080 410" role="img" aria-label="V-model links stakeholder needs to requirements, architecture, detailed design and implementation, then unit, integration, system and hardware verification."><defs><marker id="arrow2" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#58758c"/></marker></defs>
<path d="M110 65 L270 135 L420 205 L520 275 L560 345 L730 275 L780 205 L920 135 L1000 65" stroke="#7590a4" stroke-width="4" fill="none"/>
<g text-anchor="middle"><rect class="node node-blue" x="30" y="34" width="160" height="62" rx="9"/><text class="svg-title" x="110" y="60">Stakeholder needs</text><text class="svg-sub" x="110" y="80">NEED-01 / NEED-02</text>
<rect class="node node-blue" x="190" y="104" width="160" height="62" rx="9"/><text class="svg-title" x="270" y="130">System requirements</text><text class="svg-sub" x="270" y="150">SYS / SEC</text>
<rect class="node node-blue" x="340" y="174" width="160" height="62" rx="9"/><text class="svg-title" x="420" y="200">Software requirement</text><text class="svg-sub" x="420" y="220">SWR-01</text>
<rect class="node node-blue" x="440" y="244" width="160" height="62" rx="9"/><text class="svg-title" x="520" y="270">Architecture</text><text class="svg-sub" x="520" y="290">system components</text>
<rect class="node node-blue" x="480" y="314" width="160" height="62" rx="9"/><text class="svg-title" x="560" y="340">Detailed design</text><text class="svg-sub" x="560" y="360">module interfaces</text>
<rect class="node node-green" x="650" y="244" width="160" height="62" rx="9"/><text class="svg-title" x="730" y="270">Implementation</text><text class="svg-sub" x="730" y="290">source modules</text>
<rect class="node node-green" x="700" y="174" width="160" height="62" rx="9"/><text class="svg-title" x="780" y="200">Unit verification</text><text class="svg-sub" x="780" y="220">pytest / native CTest</text>
<rect class="node node-green" x="840" y="104" width="160" height="62" rx="9"/><text class="svg-title" x="920" y="130">Integration</text><text class="svg-sub" x="920" y="150">gateway + PTY</text>
<rect class="node node-green" x="920" y="34" width="160" height="62" rx="9"/><text class="svg-title" x="1000" y="60">System / HIL</text><text class="svg-sub" x="1000" y="80">Yocto target / bench</text></g>
<text class="svg-sub" x="540" y="398" text-anchor="middle">Left: decomposition and design                          Right: implementation verification and validation</text>
</svg></section>
<section class="section-head"><div><h2>Requirement traceability matrix</h2><p>Filter the matrix, then follow linked source and test files back into the repository.</p></div></section>
<div class="controls"><input id="search" type="search" placeholder="Search ID, requirement, source, test…" aria-label="Search traceability"><select id="kind" aria-label="Filter requirement kind"><option value="all">All requirement kinds</option><option value="system">System</option><option value="security">Security</option><option value="software">Software</option></select><span id="shown" class="muted"></span></div>
<div class="tablebox"><table><colgroup><col style="width:9%"><col style="width:20%"><col style="width:14%"><col style="width:15%"><col style="width:22%"><col style="width:20%"></colgroup><thead><tr><th>ID / parent</th><th>Requirement</th><th>Design allocation</th><th>Implementation</th><th>Verification evidence</th><th>Remaining evidence / status</th></tr></thead><tbody>__ROWS__</tbody></table><div id="empty" class="empty">No matching requirement records.</div></div>
<footer>Generated from <code>docs/design/v-model-traceability.md</code> by <code>tools/generate_design_report.py</code>. Rebuild with <code>python3 tools/generate_design_report.py</code>. Architecture and design content remains maintained in the linked Markdown documents.</footer></main>
<script>
const search=document.getElementById('search'),kind=document.getElementById('kind'),rows=[...document.querySelectorAll('tbody tr')],shown=document.getElementById('shown'),empty=document.getElementById('empty');
function filter(){const q=search.value.toLowerCase().trim(),k=kind.value;let n=0;for(const r of rows){const ok=(!q||r.dataset.text.includes(q))&&(k==='all'||r.dataset.kind===k);r.hidden=!ok;if(ok)n++}shown.textContent=`Showing ${n} of ${rows.length} requirements`;empty.style.display=n?'none':'block'}search.addEventListener('input',filter);kind.addEventListener('change',filter);filter();
</script></body></html>'''
    html = (template.replace("__TOTAL__", str(len(rows)))
            .replace("__UNIT__", str(level_counts["unit"]))
            .replace("__INTEGRATION__", str(level_counts["integration"]))
            .replace("__SYSTEM__", str(level_counts["system"]))
            .replace("__HIL__", str(level_counts["hil"]))
            .replace("__ROWS__", "\n".join(row_html)))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traceability", type=Path, default=ROOT / "docs/design/v-model-traceability.md")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/design/index.html")
    args = parser.parse_args()
    render(read_traceability(args.traceability), args.output)
    print(f"Graphical design report: {args.output}")


if __name__ == "__main__":
    main()
