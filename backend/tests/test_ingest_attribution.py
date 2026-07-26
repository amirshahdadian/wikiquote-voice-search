from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.cli.ingest import ExtractedQuote, MWParserQuoteExtractor


CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "ingest_pages.json").read_text()
)
SEMANTIC_FIELDS = (
    "quote",
    "author",
    "work",
    "page_title",
    "page_type",
    "citation",
    "quote_type",
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["title"])
def test_golden_page_extraction(case):
    extractor = MWParserQuoteExtractor()

    rows = extractor.extract_page(
        case["title"],
        case["page_id"],
        case["revision_id"],
        case["wikitext"],
    )

    actual = [
        {field: row.to_dict().get(field) for field in SEMANTIC_FIELDS}
        for row in rows
    ]
    assert actual == case["expected"]


def test_quote_id_is_stable_across_pages():
    extractor = MWParserQuoteExtractor()
    first = extractor._finalize_quote(
        ExtractedQuote(
            quote="Stay hungry, stay foolish.",
            author="Steve Jobs",
            page_title="Steve Jobs",
            page_type="person",
            page_id=10,
            revision_id=20,
        )
    )
    second = extractor._finalize_quote(
        ExtractedQuote(
            quote="Stay hungry, stay foolish.",
            author="Steve Jobs",
            page_title="Stanford commencement address",
            page_type="theme",
            page_id=11,
            revision_id=21,
        )
    )

    assert first.quote_id == second.quote_id
    assert first.attribution_id != second.attribution_id
    assert len(first.quote_id) == 64


def test_page_and_revision_ids_are_preserved(tmp_path):
    xml_path = tmp_path / "wikiquote.xml"
    xml_path.write_text(
        """<mediawiki>
        <page><title>Test Person</title><id>42</id>
        <revision><id>84</id><text>
        [[Category:People]]
        == Quotes ==
        * A sufficiently long quotation for validation.
        </text></revision></page>
        </mediawiki>""",
        encoding="utf-8",
    )

    rows = MWParserQuoteExtractor().parse_wikiquote_xml(str(xml_path))

    assert rows[0]["page_id"] == 42
    assert rows[0]["revision_id"] == 84


def test_validation_is_deliberately_small():
    extractor = MWParserQuoteExtractor()

    assert extractor._is_valid_quote(
        "The only thing we have to fear is fear itself."
    )
    assert not extractor._is_valid_quote("Too short.")
    assert not extractor._is_valid_quote("1234567890 1234567890 1234567890")


@pytest.mark.parametrize(
    ("title", "wikitext", "page_type", "author", "work"),
    [
        (
            "Albert Einstein",
            """{{DEFAULTSORT:Einstein, Albert}}
            == Scientific work ==
            * Imagination is more important than knowledge, because knowledge is limited.
            ** ''[[Annus Mirabilis papers]]'' (1905).
            [[Category:Albert Einstein| ]]""",
            "person",
            "Albert Einstein",
            "Annus Mirabilis papers",
        ),
        (
            "Maya Angelou",
            """== Books ==
            * There is no greater agony than bearing an untold story inside you.
            ** ''[[Gather Together in My Name]]'' (1974).
            [[Category:1928 births]]
            [[Category:2014 deaths]]""",
            "person",
            "Maya Angelou",
            "Gather Together in My Name",
        ),
        (
            "William Shakespeare",
            """== Quotes ==
            * All the world's a stage, and all the men and women merely players.
            ** ''[[As You Like It]]'', Act II, scene vii.
            [[Category:1564 births]]
            [[Category:1616 deaths]]
            [[Category:Playwrights from England]]""",
            "person",
            "William Shakespeare",
            "As You Like It",
        ),
        (
            "Hamlet",
            """{{italic title}}
            == Hamlet ==
            * There are more things in heaven and earth than are dreamt of in our philosophy.
            ** [[First Folio]] (1623).
            [[Category:Shakespearean tragedies]]""",
            "literary_work",
            None,
            "Hamlet",
        ),
    ],
)
def test_real_page_structure_keeps_page_identity(
    title, wikitext, page_type, author, work
):
    rows = MWParserQuoteExtractor().extract_page(title, 1, 2, wikitext)

    assert rows
    assert rows[0].page_type == page_type
    assert rows[0].author == author
    assert rows[0].work == work
