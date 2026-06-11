# FitFindr

FitFindr is an AI-powered thrift shopping assistant. You describe what you're looking for, and it searches a secondhand listings dataset, suggests a complete outfit using your wardrobe, and generates an Instagram-style fit card.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root with your Groq API key (free at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

Run the app:

```bash
python app.py
```

Run the test suite:

```bash
.venv/bin/python -m pytest tests/test_tools.py -v
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Searches the mock listings dataset for items that match the user's query. Returns results ranked by keyword relevance so the agent always works with the best match.

**Inputs:**

| Parameter | Type | Description |
|---|---|---|
| `description` | `str` | Free-text description of what the user wants (e.g. `"vintage graphic tee"`) |
| `size` | `str \| None` | Size to filter by; case-insensitive substring match against the listing's size field. `None` skips size filtering. |
| `max_price` | `float \| None` | Inclusive price ceiling. `None` skips price filtering. |

**Output:** `list[dict]` — matching listing dicts sorted by relevance (most keyword overlap first). Each dict contains `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`. Returns an empty list if nothing matches — never raises.

---

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Uses an LLM to suggest 1–2 complete outfit combinations featuring the thrifted item and specific named pieces from the user's wardrobe.

**Inputs:**

| Parameter | Type | Description |
|---|---|---|
| `new_item` | `dict` | A listing dict returned by `search_listings` |
| `wardrobe` | `dict` | A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each item has `name`, `category`, `colors`, `style_tags`, and `notes`. |

**Output:** `str` — a non-empty outfit suggestion string from the LLM, or one of two error strings if the tool cannot produce a suggestion (see Error Handling).

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Uses an LLM to generate a short, casual Instagram-style OOTD caption that highlights the thrifted item and the full outfit.

**Inputs:**

| Parameter | Type | Description |
|---|---|---|
| `outfit` | `str` | The outfit suggestion string returned by `suggest_outfit` |
| `new_item` | `dict` | The listing dict for the thrifted item |

**Output:** `str` — a 2–3 sentence caption in an authentic OOTD voice mentioning the item name, price, and platform once each. Returns an error string if the input is invalid or the LLM fails (see Error Handling).

---

## Planning Loop

The agent runs a linear, guarded pipeline. Each step only executes if the previous one succeeded.

```
User query
    │
    ▼
Parse description, size, max_price from query text (regex)
    │
    ▼
search_listings(description, size, max_price)
    │
    ├─ empty → set session["error"], return early
    │
    ▼
session["selected_item"] = results[0]
    │
    ▼
suggest_outfit(selected_item, wardrobe)
    │
    ├─ empty/None → set session["error"], return early
    │
    ▼
session["outfit_suggestion"] = result
    │
    ▼
create_fit_card(outfit_suggestion, selected_item)
    │
    ▼
session["fit_card"] = result → return session
```

**Query parsing** uses regex to extract `max_price` (patterns like `"under $30"`, `"$40"`) and `size` (pattern `"size M"`, `"size XS"`). The full query string is passed as `description` — the keyword scoring in `search_listings` handles relevance without needing the description stripped down.

**Early returns** mean `suggest_outfit` is never called with a missing item, and `create_fit_card` is never called with a missing outfit. The agent does not call all three tools unconditionally.

---

## State Management

All state lives in a single `session` dict initialized at the start of each interaction and threaded through the planning loop:

```python
session = {
    "query":             str,        # original user query
    "parsed":            dict,       # extracted description, size, max_price
    "search_results":    list[dict], # all matching listings from search_listings
    "selected_item":     dict,       # results[0], passed into suggest_outfit
    "wardrobe":          dict,       # user's wardrobe, passed into suggest_outfit
    "outfit_suggestion": str,        # returned by suggest_outfit, passed into create_fit_card
    "fit_card":          str,        # returned by create_fit_card, shown to user
    "error":             str | None, # set on failure, triggers early return
}
```

Each tool writes its output to a specific key; the next tool reads from that key. No tool re-prompts the user or reconstructs data from the original query; it only reads what the previous step wrote. This was verified by running a full interaction with spy wrappers on `suggest_outfit` and `create_fit_card` that confirmed the objects passed in were the same Python objects stored in the session (`is` check returned `True` for both).

---

## Error Handling

### `search_listings`

**Failure mode:** No listings match the description, size, or price constraints.

**Agent response:** Sets `session["error"]` to:
> "No listings found for your query. Try broadening your description, adjusting your size, or increasing your max price."

Returns the session immediately. `suggest_outfit` and `create_fit_card` are never called.

**Concrete example from testing:** `test_combined_price_and_size_filter_returns_empty` — queried `"vintage"` with `size="L"` and `max_price=30.00`. The only size-L item in the mock data (`lst_002`) costs $45, so it was eliminated by the price filter. The function returned `[]`, which the agent surfaced as the error message above.

---

### `suggest_outfit`

**Failure mode 1 — empty wardrobe:** `wardrobe["items"]` is empty or the key is missing.

**Agent response:** Returns the string:
> "Please add items to your wardrobe before requesting an outfit suggestion."

No LLM call is made. Verified by `test_empty_wardrobe_returns_error_message`, which also asserted `_get_groq_client` was never called.

**Failure mode 2 — LLM returns empty response:** The Groq API returns a blank completion.

**Agent response:** Returns:
> "We couldn't generate an outfit suggestion right now. Please try again."

**Concrete example from testing:** `test_llm_whitespace_response_returns_fallback` — the mock client was configured to return `"   \n  "`. After `.strip()`, this is falsy, so the fallback string was returned instead of the whitespace.

---

### `create_fit_card`

**Failure mode 1 — outfit input is missing:** `outfit` is `None`, an empty string, or whitespace-only.

**Agent response:** Returns:
> "Can't create a fit card without an outfit suggestion. Please try your search again."

No LLM call is made. Verified by `test_none_outfit_returns_error`, `test_empty_outfit_returns_error`, and `test_whitespace_outfit_returns_error`, all of which asserted `_get_groq_client` was never called.

**Failure mode 2 — LLM returns empty response:**

**Agent response:** Returns:
> "Couldn't generate a fit card right now. Please try again."

**Concrete example from testing:** `test_llm_empty_response_returns_fitcard_fallback` — mock client returned `""`, which after `.strip()` is falsy, triggering the fallback.

---

## Spec Reflection

**What matched the spec exactly:**
The three-tool pipeline, the session dict keys, the early-return logic on empty results, and all error strings were implemented exactly as written in `planning.md`. The state diagram proved accurate — each arrow in the Mermaid diagram maps one-to-one to a line in `run_agent()`.

**What diverged from the spec:**

*`suggest_outfit` empty-wardrobe behavior:* The `tools.py` docstring said to call the LLM for general styling advice when the wardrobe is empty. The planning.md error table said to return an error string instead. I followed `planning.md` since it was the authoritative spec, and the docstring was guidance for a stretch behavior.

*`search_listings` return type:* The planning.md originally described the return as a "dict of all listings." The actual implementation returns a `list[dict]` (a list where index 0 is the best match), which is what the agent needs to do `results[0]`. The planning.md was updated to reflect this correction before implementation was finalized.

*Query parsing scope:* The planning.md did not specify how to parse the query (regex vs. LLM). Regex was chosen because it is deterministic, adds no latency, and requires no API call for a straightforward extraction task. The full query string is passed as `description` rather than a stripped-down version, since `search_listings` scoring handles noise gracefully.

---

## AI Usage

### Instance 1 — Implementing `search_listings`

**What I gave Claude:** The full `planning.md` file (Tool 1 spec block: inputs with types, return value description, failure mode), the `tools.py` stub with its docstring TODO list, and the `data_loader.py` helper so it knew not to re-implement file loading.

**What it produced:** A working `search_listings` implementation using `_tokenize()` (regex word-set extraction) for keyword scoring, case-insensitive substring matching for size, and an inclusive price filter. It also produced 14 pytest tests using `unittest.mock.patch` to mock `load_listings`, covering all three failure modes.

**What I changed:** The planning.md described the return value as a "dict of all listings." Claude correctly implemented it as a `list[dict]` since that's what `results[0]` requires in the planning loop — and flagged the mismatch. I updated the planning.md to say `list[dict]` before moving on. I also reviewed the tokenization approach: Claude used regex word tokens (`re.findall(r"[a-z0-9]+"`) rather than a simple `.split()`, which I kept because it avoids false substring matches like `"tee"` hitting `"streetwear"`.

---

### Instance 2 — Implementing `run_agent()` (planning loop)

**What I gave Claude:** The Planning Loop section from `planning.md` (the four numbered steps with exact branching conditions), the State Management section (the session dict with all key names), and the Architecture Mermaid diagram showing every branch and early-return path.

**What it produced:** A `run_agent()` implementation with regex-based query parsing, the two guarded early returns (`if not session["search_results"]` and `if not session["outfit_suggestion"]`), and correct session key writes at each step. It also proposed an explanation of the logic before writing any code, which I reviewed and approved before implementation.

**What I changed:** I reviewed the branching logic against my planning.md diagram before accepting the code, and confirmed the early return conditions and session key names matched the spec exactly.
