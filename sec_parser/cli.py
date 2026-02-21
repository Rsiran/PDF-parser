"""CLI entry point for sec-parse."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from .pipeline import ProcessingResult, process_pdf

load_dotenv()


def _update_filing_sequence(path: Path, seq: int) -> None:
    """Insert or update ``filing_sequence`` in the YAML front-matter of *path*."""
    text = path.read_text(encoding="utf-8")

    # Check if filing_sequence already exists in front-matter
    if re.search(r"^filing_sequence:", text, re.MULTILINE):
        text = re.sub(
            r"^filing_sequence:.*$",
            f"filing_sequence: {seq}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        # Insert before the closing --- of front-matter
        text = re.sub(
            r"^(---\n(?:.*\n)*?)(---\n)",
            rf"\g<1>filing_sequence: {seq}\n\2",
            text,
            count=1,
        )

    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sec-parse",
        description="Batch-process SEC 10-K and 10-Q financial PDFs into structured markdown.",
    )
    parser.add_argument(
        "input_folder",
        type=Path,
        help="Folder containing SEC filing PDFs",
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

    successes: list[ProcessingResult] = []
    failures: list[tuple[Path, str]] = []

    for i, pdf_path in enumerate(pdfs, 1):
        print(f"\n[{i}/{len(pdfs)}] {pdf_path.name}", file=sys.stderr)
        try:
            result = process_pdf(pdf_path, output_dir, verbose=args.verbose)
            successes.append(result)
            print(f"  -> {result.output_path}", file=sys.stderr)
        except Exception as e:
            failures.append((pdf_path, str(e)))
            print(f"  FAILED: {e}", file=sys.stderr)

    # Assign filing_sequence based on period_end (oldest = 1)
    if len(successes) > 1:
        successes.sort(key=lambda r: r.metadata.get("period_end", ""))
        for i, result in enumerate(successes, 1):
            _update_filing_sequence(result.output_path, i)

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
