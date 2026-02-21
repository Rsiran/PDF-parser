"""CLI entry point for sec-parse."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .pipeline import process_pdf

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sec-parse",
        description="Batch-process financial report PDFs (SEC 10-K/10-Q and IFRS) into structured markdown.",
    )
    parser.add_argument(
        "input_folder",
        type=Path,
        help="Folder containing financial report PDFs",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output folder for markdown files (default: <input_folder>/output)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed progress",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Gemini model to use (overrides GEMINI_MODEL env var)",
    )

    args = parser.parse_args()

    # Validate input folder
    if not args.input_folder.is_dir():
        print(f"Error: {args.input_folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Set model via env var if provided as CLI arg
    if args.model:
        os.environ["GEMINI_MODEL"] = args.model

    output_dir = args.output or args.input_folder / "output"

    # Collect PDFs
    pdfs = sorted(args.input_folder.glob("*.pdf"))
    if not pdfs:
        print(f"No PDF files found in {args.input_folder}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(pdfs)} PDF(s) in {args.input_folder}", file=sys.stderr)

    successes: list[Path] = []
    failures: list[tuple[Path, str]] = []

    for i, pdf_path in enumerate(pdfs, 1):
        print(f"\n[{i}/{len(pdfs)}] {pdf_path.name}", file=sys.stderr)
        try:
            out = process_pdf(pdf_path, output_dir, verbose=args.verbose)
            successes.append(out)
            print(f"  -> {out}", file=sys.stderr)
        except Exception as e:
            failures.append((pdf_path, str(e)))
            print(f"  FAILED: {e}", file=sys.stderr)

    # Summary
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Done. {len(successes)} succeeded, {len(failures)} failed.", file=sys.stderr)

    if failures:
        print("\nFailures:", file=sys.stderr)
        for path, error in failures:
            print(f"  {path.name}: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
