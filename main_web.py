#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main_web.py – iperf-manager web dashboard entry point.

Usage:
    python main_web.py [--host 0.0.0.0] [--port 5000] [--debug]
"""
from __future__ import annotations

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="iperf-manager web dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5000, help="Listen port (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    from web.app import app, socketio

    print(f"[iperf-manager] Starting web dashboard on http://{args.host}:{args.port}")
    socketio.run(app, host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
