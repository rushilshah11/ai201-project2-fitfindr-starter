"""
tests/test_tools.py

Pytest tests for search_listings, suggest_outfit, and create_fit_card in tools.py.
External dependencies (load_listings, Groq client) are mocked so tests are
deterministic and make no network calls.
"""

from unittest.mock import MagicMock, patch

import pytest

from tools import search_listings, suggest_outfit, create_fit_card

# ── shared mock data ──────────────────────────────────────────────────────────

MOCK_LISTINGS = [
    {
        "id": "lst_001",
        "title": "Vintage Graphic Tee",
        "description": "A classic faded band tee with a great vintage feel.",
        "category": "tops",
        "style_tags": ["vintage", "graphic tee", "streetwear"],
        "size": "M",
        "condition": "good",
        "price": 25.00,
        "colors": ["black"],
        "brand": None,
        "platform": "depop",
    },
    {
        "id": "lst_002",
        "title": "90s Track Jacket",
        "description": "Authentic 90s track jacket with stripe detail.",
        "category": "outerwear",
        "style_tags": ["90s", "vintage", "athletic", "streetwear"],
        "size": "L",
        "condition": "excellent",
        "price": 45.00,
        "colors": ["navy", "white"],
        "brand": "Champion",
        "platform": "poshmark",
    },
    {
        "id": "lst_003",
        "title": "Flowy Midi Skirt",
        "description": "Lightweight cottagecore midi skirt with floral pattern.",
        "category": "bottoms",
        "style_tags": ["cottagecore", "vintage", "feminine"],
        "size": "S",
        "condition": "excellent",
        "price": 30.00,
        "colors": ["white", "pink"],
        "brand": None,
        "platform": "thredUp",
    },
]


# ── happy path ────────────────────────────────────────────────────────────────

def test_returns_matching_listings():
    """A matching description returns relevant results."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        results = search_listings("vintage graphic tee")
    assert len(results) > 0
    ids = [r["id"] for r in results]
    assert "lst_001" in ids  # best match for "vintage graphic tee"


def test_returns_list_of_dicts():
    """Each result is a dict with expected keys."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        results = search_listings("vintage")
    assert isinstance(results, list)
    for item in results:
        assert isinstance(item, dict)
        assert "title" in item and "price" in item and "platform" in item


# ── failure mode: no results ──────────────────────────────────────────────────

def test_no_match_returns_empty_list():
    """A description with no keyword overlap returns [] without raising."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        results = search_listings("ballgown sequin designer")
    assert results == []


def test_returns_empty_list_not_exception():
    """An impossible query returns [] rather than raising an exception."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        results = search_listings("xyzzy impossible query zork")
    assert results == []


# ── failure mode: price filter eliminates all results ─────────────────────────

def test_max_price_excludes_expensive_items():
    """Items above max_price are excluded."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        results = search_listings("vintage", max_price=20.00)
    # All mock items cost $25, $45, $30 — none are ≤ $20
    assert results == []


def test_max_price_includes_items_at_ceiling():
    """Items exactly at max_price are included (inclusive ceiling)."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        results = search_listings("skirt", max_price=30.00)
    ids = [r["id"] for r in results]
    assert "lst_003" in ids  # $30 == max_price, should be included


def test_max_price_filters_partial_results():
    """max_price removes some results but keeps others."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        results = search_listings("vintage", max_price=30.00)
    ids = [r["id"] for r in results]
    assert "lst_001" in ids   # $25 — under limit
    assert "lst_003" in ids   # $30 — at limit
    assert "lst_002" not in ids  # $45 — over limit


# ── failure mode: size filter eliminates all results ──────────────────────────

def test_size_filter_excludes_non_matching():
    """Items whose size field does not contain the requested size are excluded."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        # Only lst_001 is size "M"; lst_002 is "L", lst_003 is "S"
        results = search_listings("vintage", size="M")
    ids = [r["id"] for r in results]
    assert "lst_001" in ids
    assert "lst_002" not in ids
    assert "lst_003" not in ids


def test_size_filter_no_match_returns_empty():
    """Returns [] when no listing matches the requested size."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        results = search_listings("vintage", size="XXS")
    assert results == []


def test_size_filter_case_insensitive():
    """Size matching is case-insensitive ('m' finds size 'M')."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        lower = search_listings("vintage", size="m")
        upper = search_listings("vintage", size="M")
    assert [r["id"] for r in lower] == [r["id"] for r in upper]


# ── relevance ordering ────────────────────────────────────────────────────────

def test_results_sorted_by_relevance():
    """The listing with more keyword matches ranks first."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        # "vintage graphic tee" → lst_001 scores 3 (vintage, graphic, tee)
        #                          lst_002 scores 1 (vintage)
        #                          lst_003 scores 1 (vintage)
        results = search_listings("vintage graphic tee")
    assert results[0]["id"] == "lst_001"


def test_zero_score_items_excluded():
    """Listings with no keyword overlap are not returned."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        # "skirt" matches lst_003; lst_001 and lst_002 have no "skirt" tokens
        results = search_listings("skirt")
    ids = [r["id"] for r in results]
    assert "lst_003" in ids
    assert "lst_001" not in ids
    assert "lst_002" not in ids


# ── combined filters ──────────────────────────────────────────────────────────

def test_combined_price_and_size_filter_returns_empty():
    """Both filters active; no listing satisfies both → []."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        # lst_001 is M/$25 — price OK but size must match "L"
        # lst_002 is L/$45 — size OK but $45 > max_price $30
        results = search_listings("vintage", size="L", max_price=30.00)
    assert results == []


def test_combined_filters_returns_correct_item():
    """Both filters applied; one item satisfies both."""
    with patch("tools.load_listings", return_value=MOCK_LISTINGS):
        # lst_001: size M, price $25 — passes both filters
        results = search_listings("vintage tee", size="M", max_price=30.00)
    assert len(results) == 1
    assert results[0]["id"] == "lst_001"


# ═════════════════════════════════════════════════════════════════════════════
# suggest_outfit tests
# ═════════════════════════════════════════════════════════════════════════════

# ── shared fixtures ───────────────────────────────────────────────────────────

MOCK_NEW_ITEM = {
    "id": "lst_001",
    "title": "Vintage Graphic Tee",
    "category": "tops",
    "colors": ["black"],
    "style_tags": ["vintage", "graphic tee", "streetwear"],
    "price": 25.00,
    "platform": "depop",
}

MOCK_WARDROBE = {
    "items": [
        {
            "id": "w_001",
            "name": "Baggy straight-leg jeans",
            "category": "bottoms",
            "colors": ["dark blue"],
            "style_tags": ["denim", "streetwear", "baggy"],
            "notes": "High-waisted",
        },
        {
            "id": "w_002",
            "name": "White ribbed tank top",
            "category": "tops",
            "colors": ["white"],
            "style_tags": ["basics", "minimal"],
            "notes": None,
        },
    ]
}

EMPTY_WARDROBE = {"items": []}


def _make_mock_client(content: str) -> MagicMock:
    """Return a mock Groq client whose completion returns `content`."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = content
    return mock_client


# ── failure mode: empty wardrobe ──────────────────────────────────────────────

def test_empty_wardrobe_returns_error_message():
    """Empty wardrobe returns the planning.md error string without calling the LLM."""
    with patch("tools._get_groq_client") as mock_groq:
        result = suggest_outfit(MOCK_NEW_ITEM, EMPTY_WARDROBE)
    assert result == "Please add items to your wardrobe before requesting an outfit suggestion."
    mock_groq.assert_not_called()


def test_missing_items_key_treated_as_empty():
    """A wardrobe dict with no 'items' key is treated as empty."""
    with patch("tools._get_groq_client") as mock_groq:
        result = suggest_outfit(MOCK_NEW_ITEM, {})
    assert result == "Please add items to your wardrobe before requesting an outfit suggestion."
    mock_groq.assert_not_called()


# ── failure mode: LLM returns empty response ──────────────────────────────────

def test_llm_empty_response_returns_fallback():
    """If the LLM returns an empty string, the fallback error message is returned."""
    with patch("tools._get_groq_client", return_value=_make_mock_client("")):
        result = suggest_outfit(MOCK_NEW_ITEM, MOCK_WARDROBE)
    assert result == "We couldn't generate an outfit suggestion right now. Please try again."


def test_llm_whitespace_response_returns_fallback():
    """A response that is only whitespace is treated as empty."""
    with patch("tools._get_groq_client", return_value=_make_mock_client("   \n  ")):
        result = suggest_outfit(MOCK_NEW_ITEM, MOCK_WARDROBE)
    assert result == "We couldn't generate an outfit suggestion right now. Please try again."


# ── happy path ────────────────────────────────────────────────────────────────

def test_happy_path_returns_llm_response():
    """A non-empty LLM response is returned as the outfit suggestion."""
    expected = "Pair the tee with your baggy jeans for a 90s streetwear look."
    with patch("tools._get_groq_client", return_value=_make_mock_client(expected)):
        result = suggest_outfit(MOCK_NEW_ITEM, MOCK_WARDROBE)
    assert result == expected


def test_returns_string():
    """Return value is always a string."""
    with patch("tools._get_groq_client", return_value=_make_mock_client("Some suggestion")):
        result = suggest_outfit(MOCK_NEW_ITEM, MOCK_WARDROBE)
    assert isinstance(result, str)


# ── prompt content ────────────────────────────────────────────────────────────

def test_new_item_title_in_prompt():
    """The new item's title appears in the prompt sent to the LLM."""
    mock_client = _make_mock_client("Some suggestion")
    with patch("tools._get_groq_client", return_value=mock_client):
        suggest_outfit(MOCK_NEW_ITEM, MOCK_WARDROBE)
    call_args = mock_client.chat.completions.create.call_args
    prompt = call_args.kwargs["messages"][0]["content"]
    assert "Vintage Graphic Tee" in prompt


def test_wardrobe_items_in_prompt():
    """Each wardrobe item's name appears in the prompt sent to the LLM."""
    mock_client = _make_mock_client("Some suggestion")
    with patch("tools._get_groq_client", return_value=mock_client):
        suggest_outfit(MOCK_NEW_ITEM, MOCK_WARDROBE)
    call_args = mock_client.chat.completions.create.call_args
    prompt = call_args.kwargs["messages"][0]["content"]
    assert "Baggy straight-leg jeans" in prompt
    assert "White ribbed tank top" in prompt


# ═════════════════════════════════════════════════════════════════════════════
# create_fit_card tests
# ═════════════════════════════════════════════════════════════════════════════

MOCK_OUTFIT = "Pair this vintage tee with baggy jeans and chunky sneakers for a 90s streetwear look."


# ── failure mode: missing outfit input ────────────────────────────────────────

def test_none_outfit_returns_error():
    """None outfit returns the planning.md error string without calling the LLM."""
    with patch("tools._get_groq_client") as mock_groq:
        result = create_fit_card(None, MOCK_NEW_ITEM)
    assert result == "Can't create a fit card without an outfit suggestion. Please try your search again."
    mock_groq.assert_not_called()


def test_empty_outfit_returns_error():
    """Empty string outfit returns the error string without calling the LLM."""
    with patch("tools._get_groq_client") as mock_groq:
        result = create_fit_card("", MOCK_NEW_ITEM)
    assert result == "Can't create a fit card without an outfit suggestion. Please try your search again."
    mock_groq.assert_not_called()


def test_whitespace_outfit_returns_error():
    """Whitespace-only outfit is treated as empty."""
    with patch("tools._get_groq_client") as mock_groq:
        result = create_fit_card("   \n  ", MOCK_NEW_ITEM)
    assert result == "Can't create a fit card without an outfit suggestion. Please try your search again."
    mock_groq.assert_not_called()


# ── failure mode: LLM returns empty response ──────────────────────────────────

def test_llm_empty_response_returns_fitcard_fallback():
    """If the LLM returns an empty string, the fallback error message is returned."""
    with patch("tools._get_groq_client", return_value=_make_mock_client("")):
        result = create_fit_card(MOCK_OUTFIT, MOCK_NEW_ITEM)
    assert result == "Couldn't generate a fit card right now. Please try again."


# ── happy path ────────────────────────────────────────────────────────────────

def test_fitcard_happy_path_returns_llm_response():
    """A non-empty LLM response is returned as the fit card."""
    expected = "thrifted this vintage graphic tee off depop for $25 and it was made for my baggy jeans! 🖤"
    with patch("tools._get_groq_client", return_value=_make_mock_client(expected)):
        result = create_fit_card(MOCK_OUTFIT, MOCK_NEW_ITEM)
    assert result == expected


def test_fitcard_returns_string():
    """Return value is always a string."""
    with patch("tools._get_groq_client", return_value=_make_mock_client("Some caption")):
        result = create_fit_card(MOCK_OUTFIT, MOCK_NEW_ITEM)
    assert isinstance(result, str)


# ── prompt content ────────────────────────────────────────────────────────────

def test_item_title_in_fitcard_prompt():
    """The item title appears in the prompt sent to the LLM."""
    mock_client = _make_mock_client("Some caption")
    with patch("tools._get_groq_client", return_value=mock_client):
        create_fit_card(MOCK_OUTFIT, MOCK_NEW_ITEM)
    prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "Vintage Graphic Tee" in prompt


def test_item_platform_in_fitcard_prompt():
    """The item platform appears in the prompt sent to the LLM."""
    mock_client = _make_mock_client("Some caption")
    with patch("tools._get_groq_client", return_value=mock_client):
        create_fit_card(MOCK_OUTFIT, MOCK_NEW_ITEM)
    prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "depop" in prompt


def test_outfit_text_in_fitcard_prompt():
    """The outfit suggestion appears in the prompt sent to the LLM."""
    mock_client = _make_mock_client("Some caption")
    with patch("tools._get_groq_client", return_value=mock_client):
        create_fit_card(MOCK_OUTFIT, MOCK_NEW_ITEM)
    prompt = mock_client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert MOCK_OUTFIT in prompt
