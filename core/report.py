# -*- coding: utf-8 -*-
"""
report.py - iperf3 HTML 리포트 생성 모듈
Dashboard에서 분리된 generate_report() 및 관련 헬퍼 함수.
"""
import csv as _csv
import datetime as _dt
import os
from pathlib import Path as _Path

from matplotlib.backends.backend_agg import FigureCanvasAgg as _FCA
from matplotlib.figure import Figure as _Figure
import matplotlib.dates as _mdates


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fmt_hms(sec: int) -> str:
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _new_fig(figsize):
    fig = _Figure(figsize=figsize, dpi=100)
    _FCA(fig)
    return fig


def generate_report(csv_path: str,
                    agent_map=None,
                    target_map=None,
                    style_map=None, dpi: int = 140,
                    size_tot=(16, 6.0), size_agents=(16, 5.8),
                    size_jit=(16, 4.8), size_loss=(16, 4.2),
                    test_opts: dict | list | None = None,
                    server_url: str = None) -> str:
    # --- load CSV (wide format) ---
    cols, rows = [], []
    with open(csv_path, 'r', encoding='utf-8', newline='') as fp:
        rd = _csv.reader(fp)
        header = None
        for r in rd:
            if not r:
                continue
            if r[0].startswith('#'):
                continue
            if header is None:
                header = r
                cols = header
                continue
            rows.append(r)
    if not cols or not rows:
        raise RuntimeError('CSV empty for report')
    idx = {c: i for i, c in enumerate(cols)}

    def col(c):
        return [rows[k][idx[c]] if c in idx else '0' for k in range(len(rows))]

    agents = sorted({c[:-3] for c in cols if c.endswith('_up')})
    ts_list = [int(float(x)) for x in col('ts')]
    wall_py = [_dt.datetime.fromtimestamp(x) for x in ts_list]

    def series(a, suf):
        c = f'{a}_{suf}'
        return [_to_float(x) for x in (col(c) if c in idx else [0] * len(rows))]

    total_up = [_to_float(x) for x in (col('total_up') if 'total_up' in idx else [0] * len(rows))]
    total_dn = [_to_float(x) for x in (col('total_dn') if 'total_dn' in idx else [0] * len(rows))]

    out_dir = _Path(csv_path).parent
    stem = _Path(csv_path).stem.replace('_ui', '')

    # --- plot: total ---
    img_tot = out_dir / f'{stem}_total.png'
    fig = _Figure(figsize=size_tot, dpi=100)
    _FCA(fig)
    ax = fig.add_subplot(111)
    ax.plot(wall_py, total_up, label='TOTAL UP')
    ax.plot(wall_py, total_dn, label='TOTAL DOWN')
    ax.set_title('Total Up/Down (Mbps)')
    ax.set_xlabel('time (HH:MM:SS)')
    ax.set_ylabel('Mbps')
    ax.xaxis.set_major_formatter(_mdates.DateFormatter('%H:%M:%S'))
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(img_tot, dpi=dpi)

    # --- plot: per-agent up/down ---
    img_agents = out_dir / f'{stem}_agents.png'
    fig = _Figure(figsize=size_agents, dpi=100)
    _FCA(fig)
    ax = fig.add_subplot(111)

    def _style_for(a, i):
        mkrs = ['o', 'x', '^', '*', 's', 'D', 'P', 'X', 'v', '>', '<']
        if style_map and a in style_map:
            mk = style_map[a].get('marker') or mkrs[i % len(mkrs)]
            ls = style_map[a].get('linestyle') or '-'
        else:
            mk = mkrs[i % len(mkrs)]
            ls = '-'
        return mk, ls

    for i, a in enumerate(agents):
        mk, ls = _style_for(a, i)
        up, dn = series(a, 'up'), series(a, 'dn')
        if any(up):
            ax.plot(wall_py, up, label=f'{a} up', linestyle=ls, marker=mk,
                    markevery=max(1, len(wall_py) // 30), markersize=3, alpha=0.9)
        if any(dn):
            ax.plot(wall_py, dn, label=f'{a} down', linestyle='--', marker=mk,
                    markevery=max(1, len(wall_py) // 30), markersize=3, alpha=0.9)
    ax.set_title('Per-agent Up/Down (HH:MM:SS)')
    ax.set_xlabel('time (HH:MM:SS)')
    ax.set_ylabel('Mbps')
    ax.xaxis.set_major_formatter(_mdates.DateFormatter('%H:%M:%S'))
    if agents:
        ax.legend(ncol=3, fontsize=8, loc='upper right')
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(img_agents, dpi=dpi)

    # --- UDP jitter/loss plots (if any) ---
    img_jit = None
    img_loss = None
    if any((f'{a}_jit_ms' in idx) for a in agents):
        img_jit = out_dir / f'{stem}_udp_jitter.png'
        fig = _Figure(figsize=size_jit, dpi=100)
        _FCA(fig)
        ax = fig.add_subplot(111)
        ax.set_title('Per-agent UDP Jitter (line)')
        ax.set_xlabel('time (HH:MM:SS)')
        ax.set_ylabel('jitter (ms)')
        ax.xaxis.set_major_formatter(_mdates.DateFormatter('%H:%M:%S'))
        for i, a in enumerate(agents):
            c = f'{a}_jit_ms'
            if c in idx:
                mk, ls = _style_for(a, i)
                y = [_to_float(v) for v in col(c)]
                ax.plot(wall_py, y, label=a, linestyle=ls, marker=mk,
                        markevery=max(1, len(wall_py) // 30), markersize=3, alpha=0.95)
        if agents:
            ax.legend(ncol=4, fontsize=8)
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(img_jit, dpi=dpi)

    if any((f'{a}_loss_pct' in idx) for a in agents):
        img_loss = out_dir / f'{stem}_udp_loss.png'
        fig = _Figure(figsize=size_loss, dpi=100)
        _FCA(fig)
        ax = fig.add_subplot(111)
        ax.set_title('Per-agent UDP Loss (dot)')
        ax.set_xlabel('time (HH:MM:SS)')
        ax.set_ylabel('loss (%)')
        ax.xaxis.set_major_formatter(_mdates.DateFormatter('%H:%M:%S'))
        for i, a in enumerate(agents):
            c = f'{a}_loss_pct'
            if c in idx:
                mk, _ls = _style_for(a, i)
                y = [_to_float(v) for v in col(c)]
                ax.plot(wall_py, y, linestyle='None', marker=mk, markersize=3.2, label=a, alpha=0.9)
        if agents:
            ax.legend(ncol=6, fontsize=8)
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(img_loss, dpi=dpi)

    # --- HTML compose ---
    tested_at = (_dt.datetime.fromtimestamp(ts_list[-1])).strftime('%Y-%m-%d %H:%M') if ts_list else ''
    logo_name = 'kaon_logo.png'
    logo_path = _Path(csv_path).parent / logo_name
    logo_tag = f'<img src="{logo_name}" alt="logo" style="height:36px">' if logo_path.exists() else ''

    css = """
    <style>
    body { font-family: Segoe UI, Arial, sans-serif; margin: 18px 24px; color:#222 }
    h1 { font-size: 22px; margin: 6px 0 12px 0; }
    h3 { font-size: 16px; margin: 16px 0 6px 0; }
    table { border-collapse: collapse; margin: 6px 0 12px 0; }
    th, td { border: 1px solid #d0d0d0; padding: 6px 9px; font-size: 12.5px; }
    th { background: #f5f6f7; }
    .kvs td{ padding: 4px 8px; }
    .muted { color:#666; }
    img { max-width: 100%; height: auto; border: 1px solid #ddd; margin: 8px 0; }
    .nowrap { white-space: nowrap; }
    </style>
    """

    def kv(v):
        return '' if v is None else str(v)

    # --- Test options block (dict or list[dict]) ---
    def _render_test_opts(opts):
        if not opts:
            return ''
        rows_o = opts if isinstance(opts, list) else [opts]
        pref_order = ['mode', 'proto', 'duration_sec', 'base_port', 'parallel', 'bitrate', 'length', 'tcp_window', 'omit']
        keys = []
        for r in rows_o:
            for k in pref_order:
                if k in r and k not in keys:
                    keys.append(k)
        for r in rows_o:
            for k in r.keys():
                if k not in keys and k not in ('server', 'clients'):
                    keys.append(k)
        html_o = ['<h3>Test options</h3><table class="kvs"><tr>']
        for k in keys:
            html_o += [f'<th class="nowrap">{k}</th>']
        html_o += ['</tr>']
        for r in rows_o:
            html_o += ['<tr>']
            for k in keys:
                html_o += [f'<td class="nowrap">{kv(r.get(k, ""))}</td>']
            html_o += ['</tr>']
        html_o += ['</table>']
        return '\n'.join(html_o)

    # --- per-agent stats ---
    stats_rows = []
    for a in agents:
        up = series(a, 'up')
        dn = series(a, 'dn')
        up_avg = sum(up) / len(up) if up else 0.0
        dn_avg = sum(dn) / len(dn) if dn else 0.0
        up_max = max(up) if up else 0.0
        dn_max = max(dn) if dn else 0.0
        up_pos = [v for v in up if v > 0]
        dn_pos = [v for v in dn if v > 0]
        up_min = min(up_pos) if up_pos else 0.0
        dn_min = min(dn_pos) if dn_pos else 0.0
        sent = series(a, 'sent_mb') if f'{a}_sent_mb' in idx else []
        recv = series(a, 'recv_mb') if f'{a}_recv_mb' in idx else []
        amt = (sent[-1] if sent else 0.0) + (recv[-1] if recv else 0.0)
        jit = sum(series(a, 'jit_ms')) / len(rows) if f'{a}_jit_ms' in idx else 0.0
        los = sum(series(a, 'loss_pct')) / len(rows) if f'{a}_loss_pct' in idx else 0.0
        src_ip = (agent_map.get(a, '') if agent_map else '')
        tgt_ip = (target_map.get(a, '') if target_map else '')
        stats_rows.append((a, src_ip, tgt_ip, up_avg, dn_avg, up_max, up_min, dn_max, dn_min, (up_avg + dn_avg), amt, jit, los))

    # --- HTML assemble ---
    html = []
    html += ['<!doctype html><html><head><meta charset="utf-8"><title>IPERF3 Throughput TEST Report</title>', css, '</head><body>']
    html += ['<table style="width:100%; border-collapse:collapse;"><tr>',
             '<td style="vertical-align:middle;"><h1>IPERF3 Throughput TEST Report</h1></td>',
             f'<td style="text-align:right; vertical-align:middle;">{logo_tag}</td>', '</tr></table>']
    html += [f'<p><b>Tested at :</b> {tested_at}</p>']

    # Test options (dict or list)
    html += [_render_test_opts(test_opts)]

    # Per agent table with Source/Target columns
    html += ['<h3>Per agent</h3><table>',
             '<tr><th>Agent</th><th>Source IP</th><th>Target IP</th>'
             '<th>UP Load (AVG)</th><th>Down (AVG)</th>'
             '<th>UP Max</th><th>UP Min</th><th>Down Max</th><th>Down Min</th>'
             '<th>Sum (Total avg)</th><th>Amount (MB)</th><th>Jitter</th><th>loss</th></tr>']
    for (a, src, tgt, upa, dna, umax, umin, dmax, dmin, sumavg, amt, jit, los) in stats_rows:
        html += [f'<tr><td>{a}</td><td>{src}</td><td>{tgt}</td>',
                 f'<td>{upa:.3f}</td><td>{dna:.3f}</td>',
                 f'<td>{umax:.3f}</td><td>{(umin if umin > 0 else 0.0):.3f}</td>',
                 f'<td>{dmax:.3f}</td><td>{(dmin if dmin > 0 else 0.0):.3f}</td>',
                 f'<td>{(upa + dna):.3f}</td><td>{amt:.3f}</td><td>{jit:.3f}</td><td>{los:.3f}</td></tr>']
    # total row (if available)
    if total_up and total_dn:
        upa = sum(total_up) / len(total_up)
        dna = sum(total_dn) / len(total_dn)
        html += [f'<tr><td>total</td><td></td><td></td><td>{upa:.3f}</td><td>{dna:.3f}</td>',
                 '<td></td><td></td><td></td><td></td>',
                 f'<td>{(upa + dna):.3f}</td><td></td><td></td><td></td></tr>']
    html += ['</table>']

    # graphs
    html += ['<h3>Graphs</h3>']
    if server_url:
        html += [f'<p class="muted">Server: {server_url}</p>']
    html += [f'<img src="{img_tot.name}" alt="total">', f'<img src="{img_agents.name}" alt="per_agent">']
    if img_jit:
        html += [f'<img src="{img_jit.name}" alt="udp_jitter">']
    if img_loss:
        html += [f'<img src="{img_loss.name}" alt="udp_loss">']

    html += ['</body></html>']

    rep = out_dir / f'{stem}_report.html'
    rep.write_text('\n'.join(html), encoding='utf-8')
    return str(rep)
