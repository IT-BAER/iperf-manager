# -*- coding: utf-8 -*-
"""
controller_v5_18.py - Thin CLI wrapper around core.test_runner.

Usage:
    python controller_v5_18.py --config test_config.json --out results.csv
"""
import argparse
import json

from core.test_runner import run_test


def main():
    ap = argparse.ArgumentParser(description='iperf3 test controller')
    ap.add_argument('--config', required=True, help='Test configuration JSON file')
    ap.add_argument('--out', default='controller_result.csv', help='CSV output path')
    args = ap.parse_args()

    with open(args.config, 'r', encoding='utf-8') as fp:
        cfg = json.load(fp)

    run_test(cfg, csv_path=args.out, on_log=print)


if __name__ == '__main__':
    main()
