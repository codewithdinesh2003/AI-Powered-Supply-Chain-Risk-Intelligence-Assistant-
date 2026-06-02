#!/usr/bin/env python
"""CLI entry-point for the data ingestion pipeline.

Usage:
    python scripts/ingest_data.py --csv data/supply_chain_data.csv
    python scripts/ingest_data.py --csv data/supply_chain_data.csv --reset-chroma
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# ── Make sure the backend package root is on sys.path ────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.ingestion.pipeline import IngestionPipeline  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest supply-chain CSV data into ChromaDB + MySQL."
    )
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to supply_chain_data.csv",
    )
    parser.add_argument(
        "--reset-chroma",
        action="store_true",
        default=False,
        help="Drop and recreate the ChromaDB collection before ingesting.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv)

    if not csv_path.exists():
        print(f"[ERROR] CSV file not found: {csv_path}")
        sys.exit(1)

    pipeline = IngestionPipeline()
    summary = await pipeline.run(
        csv_path=str(csv_path),
        reset_chroma=args.reset_chroma,
    )

    print("\n" + "=" * 60)
    print("  INGESTION COMPLETE")
    print("=" * 60)
    for k, v in summary.items():
        print(f"  {k:<28} {v}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
