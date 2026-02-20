"""Gemini API integration for table normalization and notes extraction."""

from __future__ import annotations

import os
import re
import sys

from google import genai
from google.genai import types

from .prompts import (
    COVER_PAGE_PROMPT,
    NOTES_EXTRACTION_PROMPT,
    PROSE_SECTION_PROMPT,
    TABLE_NORMALIZATION_PROMPT,
)

DEFAULT_MODEL = "gemini-2.5-flash"
CHUNK_CHAR_LIMIT = 150_000


def _get_client() -> genai.Client:
    return genai.Client()  # reads GEMINI_API_KEY or GOOGLE_API_KEY from env


def _get_model() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def _format_tables_for_prompt(tables: list[list[list[str]]]) -> str:
    """Convert raw pdfplumber table data into a readable text block."""
    if not tables:
        return ""
    parts: list[str] = []
    for i, table in enumerate(tables, 1):
        parts.append(f"\n### Raw table {i}")
        for row in table:
            parts.append(" | ".join(row))
    return "\n".join(parts)


def normalize_table(section_text: str, tables: list[list[list[str]]], verbose: bool = False) -> str:
    """Send section text + raw tables to Gemini for normalization into a clean markdown table."""
    client = _get_client()
    model = _get_model()

    content = section_text
    table_text = _format_tables_for_prompt(tables)
    if table_text:
        content += "\n\n" + table_text

    prompt = TABLE_NORMALIZATION_PROMPT.format(content=content)

    if verbose:
        print(f"  [Gemini] Normalizing table ({len(prompt)} chars) with {model}...", file=sys.stderr)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction="You are a financial document processor.",
            max_output_tokens=8192,
        ),
    )

    return response.text


def _chunk_notes(text: str, limit: int = CHUNK_CHAR_LIMIT) -> list[str]:
    """Split notes text at note boundaries if it exceeds the character limit."""
    if len(text) <= limit:
        return [text]

    # Split at "Note <number>" boundaries
    pattern = re.compile(r"(?=\bNote\s+\d+)", re.IGNORECASE)
    parts = pattern.split(text)

    # Re-assemble into chunks that stay under the limit
    chunks: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > limit:
            chunks.append(current)
            current = part
        else:
            current += part
    if current:
        chunks.append(current)

    return chunks


def extract_notes(notes_text: str, verbose: bool = False) -> str:
    """Send notes text to Gemini for structured extraction. Uses chunking for large notes."""
    client = _get_client()
    model = _get_model()
    chunks = _chunk_notes(notes_text)

    if verbose and len(chunks) > 1:
        print(f"  [Gemini] Notes split into {len(chunks)} chunks", file=sys.stderr)

    results: list[str] = []
    for i, chunk in enumerate(chunks):
        prompt = NOTES_EXTRACTION_PROMPT.format(content=chunk)

        if verbose:
            print(
                f"  [Gemini] Extracting notes chunk {i + 1}/{len(chunks)} "
                f"({len(prompt)} chars) with {model}...",
                file=sys.stderr,
            )

        # Use streaming for large output
        response = client.models.generate_content_stream(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a financial document processor.",
                max_output_tokens=16000,
            ),
        )
        parts = []
        for chunk_resp in response:
            parts.append(chunk_resp.text)
        results.append("".join(parts))

    return "\n\n".join(results)


def _chunk_prose(text: str, limit: int = CHUNK_CHAR_LIMIT) -> list[str]:
    """Split prose text at heading/paragraph boundaries if it exceeds the character limit."""
    if len(text) <= limit:
        return [text]

    # Split at Item headings, markdown headings, or double newlines
    pattern = re.compile(r"(?=\n(?:Item\s+\d|#{1,3}\s|\n\n))", re.IGNORECASE)
    parts = pattern.split(text)

    chunks: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > limit:
            chunks.append(current)
            current = part
        else:
            current += part
    if current:
        chunks.append(current)

    return chunks


def extract_prose_section(section_text: str, verbose: bool = False) -> str:
    """Send a prose-heavy section to Gemini for cleanup and structuring."""
    client = _get_client()
    model = _get_model()
    chunks = _chunk_prose(section_text)

    if verbose and len(chunks) > 1:
        print(f"  [Gemini] Prose section split into {len(chunks)} chunks", file=sys.stderr)

    results: list[str] = []
    for i, chunk in enumerate(chunks):
        prompt = PROSE_SECTION_PROMPT.format(content=chunk)

        if verbose:
            print(
                f"  [Gemini] Extracting prose chunk {i + 1}/{len(chunks)} "
                f"({len(prompt)} chars) with {model}...",
                file=sys.stderr,
            )

        response = client.models.generate_content_stream(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a financial document processor.",
                max_output_tokens=16000,
            ),
        )
        parts = []
        for chunk_resp in response:
            parts.append(chunk_resp.text)
        results.append("".join(parts))

    return "\n\n".join(results)


def extract_cover_page(section_text: str, verbose: bool = False) -> str:
    """Send cover page text to Gemini for metadata extraction."""
    client = _get_client()
    model = _get_model()

    prompt = COVER_PAGE_PROMPT.format(content=section_text)

    if verbose:
        print(f"  [Gemini] Extracting cover page ({len(prompt)} chars) with {model}...", file=sys.stderr)

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction="You are a financial document processor.",
            max_output_tokens=4096,
        ),
    )

    return response.text
