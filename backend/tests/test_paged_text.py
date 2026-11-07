"""Tests for page-aware document text."""

import pytest

from utils.paged_text import PAGE_SEPARATOR, PagedText, split_pages, valid_page_starts


def test_pages_are_joined_with_a_blank_line_and_offsets_point_at_each_page():
    paged = PagedText.from_pages(["  Page one.  ", "Page two."])
    assert paged.text == "Page one." + PAGE_SEPARATOR + "Page two."
    assert paged.page_starts == (0, len("Page one.") + len(PAGE_SEPARATOR))
    assert paged.text[paged.page_starts[1]:] == "Page two."


def test_blank_pages_keep_their_page_number():
    paged = PagedText.from_pages(["", "Second page.", "   ", "Fourth page."])
    assert paged.text == "Second page." + PAGE_SEPARATOR + "Fourth page."
    assert len(paged.page_starts) == 4
    assert split_pages(paged.text, list(paged.page_starts)) == [(2, "Second page."), (4, "Fourth page.")]


def test_split_pages_round_trips():
    pages = ["Invoice INV-1001", "Line items", "Total due $10.00"]
    paged = PagedText.from_pages(pages)
    assert split_pages(paged.text, paged.page_starts) == [(1, pages[0]), (2, pages[1]), (3, pages[2])]


@pytest.mark.parametrize(
    "page_starts",
    [None, [], "0", [1], [0, 5, 3], [0, 999], [0, True], [0.0], {"a": 1}],
)
def test_unusable_offsets_fall_back_to_one_unnumbered_part(page_starts):
    assert not valid_page_starts("Some text here", page_starts)
    assert split_pages("  Some text here ", page_starts) == [(None, "Some text here")]


def test_empty_text_has_no_parts():
    assert split_pages("   ", None) == []
    assert split_pages("", [0]) == []
