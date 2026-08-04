"""Compare pdfplumber vs pypdf extraction quality on a PDF file.

Usage:
  python rag_subsystem/scripts/compare_pdf_extractors.py "C:\\path\\file.pdf" --pages 20
"""
from __future__ import annotations

import argparse

from rag_subsystem.pdf_extract import extract_pdf_text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path")
    parser.add_argument("--pages", type=int, default=20)
    args = parser.parse_args()

    text_pdfplumber, engine_a, pages_a = extract_pdf_text(args.pdf_path, max_pages=args.pages, engine="pdfplumber", fallback=False)
    text_pypdf, engine_b, pages_b = extract_pdf_text(args.pdf_path, max_pages=args.pages, engine="pypdf", fallback=False)
    text_auto, engine_auto, pages_auto = extract_pdf_text(args.pdf_path, max_pages=args.pages, engine="auto", fallback=True)

    lines_a = len([ln for ln in text_pdfplumber.splitlines() if ln.strip()])
    lines_b = len([ln for ln in text_pypdf.splitlines() if ln.strip()])

    print(f"{engine_a}: pages={pages_a} chars={len(text_pdfplumber)} lines={lines_a}")
    print(f"{engine_b}: pages={pages_b} chars={len(text_pypdf)} lines={lines_b}")
    print(f"auto -> {engine_auto}: pages={pages_auto} chars={len(text_auto)} lines={len([ln for ln in text_auto.splitlines() if ln.strip()])}")
    print("--- sample(pdfplumber) ---")
    print(text_pdfplumber[:500].replace("\n", " "))
    print("--- sample(pypdf) ---")
    print(text_pypdf[:500].replace("\n", " "))


if __name__ == "__main__":
    main()
