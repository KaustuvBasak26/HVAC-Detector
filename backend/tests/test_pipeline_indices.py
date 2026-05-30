from __future__ import annotations

import fitz

from app.processing.pipeline import _page_indices


def test_page_indices_all_pages():
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.new_page()
    try:
        idx = _page_indices(doc, "all", [])
        assert idx == [0, 1, 2]
    finally:
        doc.close()


def test_page_indices_explicit_subset():
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    try:
        idx = _page_indices(doc, "all", [2])
        assert idx == [1]
    finally:
        doc.close()


def test_page_indices_invalid_falls_back_to_all():
    doc = fitz.open()
    doc.new_page()
    try:
        idx = _page_indices(doc, "all", [99])
        assert idx == [0]
    finally:
        doc.close()
