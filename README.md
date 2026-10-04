# FitFindr

> ### 👋 Start here
>
> **New to this repo? Read [RUNNING.md](RUNNING.md) first** — setup, every
> command, and what to do when something breaks.
>
> Once `python test.py` passes:
>
> ```bash
> python app.py listings --full -n 6      # read the data (Milestone 1)
> python app.py fields                    # what you can filter on
> python app.py ask 'vintage graphic tee under $30'
> ```
>
> All three tools are stubs, so that last command will do nothing useful yet.
> That's the starting position.
>
> **The rest of this file is your submission.** Fill it in as you go.

---

<!-- ─────────────────────────────────────────────────────────────────────────
     HOW TO USE THIS FILE

     This is your submission. Fill each section in as you finish the milestone
     it belongs to — don't leave it all to the end.

     Unit 3 asks for the first five sections. Unit 4 adds the five below them.
     Leave the unit 4 sections alone until then; they're here so you know
     what's coming.

     Everything is pasted as TEXT. No screenshots, no images, no video links.
     A typed block of output gets full credit; a picture of the same output
     gets none.
     ───────────────────────────────────────────────────────────────────────── -->

<!-- ═══════════════════════ UNIT 3 — THE BUILD ═══════════════════════ -->

## What This Does

<!-- Three or four sentences: what a user asks for, and what they get back. -->

FitFindr takes a natural-language request for a secondhand clothing item, such
as a vintage graphic tee under a stated price. It parses the description, size,
and price ceiling, then searches and ranks matching listing records. For the
best match, it suggests outfits using the user's wardrobe and writes a short
fit-card caption; if nothing matches, it stops with advice about what to
change.

---

## Tool Inventory

<!-- Four lines per tool. This is worth 2 points and it's the single most
     common place students lose them.

     "Returns a list" earns NOTHING. The description has to say what is IN
     the list.

     The empty case isn't optional either — it's the thing your loop branches
     on, and if you don't decide it here you'll discover it as a crash in
     Milestone 5. -->

### `search_listings`

- **What it does:** Searches listings by description keywords, with optional size and maximum-price filters.
- **Inputs:** `description` (str), `size` (str | None), `max_price` (float | None)
- **Returns:** A list of matching listing dicts, each with `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`, ordered best match first.
- **When it has nothing:** An empty list (`[]`).

### `suggest_outfit`

- **What it does:** Suggests one or two outfits for a new listing using the user's wardrobe.
- **Inputs:** `new_item` (dict), `wardrobe` (dict with an `items` list)
- **Returns:** A non-empty string containing outfit suggestions that use wardrobe pieces, or general styling ideas for the new item when the wardrobe is empty.
- **When it has nothing:** A non-empty general styling-advice string when `wardrobe["items"]` is empty.

### `create_fit_card`

- **What it does:** Writes a short, post-ready caption for an outfit and its new thrifted item.
- **Inputs:** `outfit` (str), `new_item` (dict)
- **Returns:** A two-to-four sentence caption mentioning the item, its price, its platform, and the outfit's vibe.
- **When it has nothing:** A descriptive message when `outfit` is empty or contains only whitespace.

---

## Planning Loop

<!-- Your branch rule, stated as a rule — the condition AND both paths — plus
     the file and function that holds it.

     Like this:
       "If search_listings returns an empty list, put a message in the session
        and stop. Otherwise take the first result and go to suggest_outfit."
        — agent.py::run_agent

     The grader checks your code against what you claim here, so the file and
     function have to be real. -->

**Branch rule:** If `search_listings` returns an empty list, put a message in the session and stop. Otherwise, take the first result and go to `suggest_outfit`.

**Where it lives:** `agent.py::run_agent`

**How the query is parsed:** Regular expressions extract `size` and an inclusive `max_price`; the remaining text becomes the description.

**What moves through the session:** The parsed query goes to `search_listings`; its results become `search_results`, the first result becomes `selected_item`, and that item plus the wardrobe move through `suggest_outfit` and `create_fit_card`.

---

## Sample Run

<!-- Two things go here.

     1. One FULL query and its output, pasted as text.
     2. Your three per-tool terminal tests — the command and what it printed. -->

**One full query**

```
$ python app.py ask '...'

```

**The three tools, tested one at a time**

```
$ python -c "from tools import search_listings; print(search_listings('graphic tee', max_price=30))"
[('lst_002', 'Y2K Baby Tee — Butterfly Print', 18.0), ('lst_006', 'Graphic Tee — 2003 Tour Bootleg Style', 24.0), ('lst_017', 'Mesh Long-Sleeve Top — Black', 15.0), ('lst_033', 'Vintage Band Tee — Faded Grey', 19.0), ('lst_011', 'Low-Rise Cargo Pants — Khaki', 27.0), ('lst_015', 'Vintage Graphic Hoodie — Faded Black', 26.0)]
```

```
$ python -c "from tools import suggest_outfit; from utils.data_loader import get_example_wardrobe, load_listings; print(' '.join(suggest_outfit(load_listings()[0], get_example_wardrobe()).split()))"
Here are two complete outfits featuring your new Levi's 501 jeans: **Outfit 1: Casual Streetwear** * **New Item:** Levi's 501 Jeans * **Top:** White ribbed tank top (w_003) tucked in * **Outerwear:** Oversized grey crewneck sweatshirt (w_004) layered over * **Shoes:** Chunky white sneakers (w_007) * **Accessories:** Black crossbody bag (w_010) **Outfit 2: Edgy Denim-on-Denim** * **New Item:** Levi's 501 Jeans * **Top:** Black cropped zip hoodie (w_005) * **Outerwear:** Vintage black denim jacket (w_006) * **Shoes:** Black combat boots (w_008) * **Accessories:** Brown leather belt (w_009) and black crossbody bag (w_010)
```

```
$ python -c "from tools import create_fit_card; from utils.data_loader import load_listings; print(' '.join(create_fit_card('white ribbed tank top, oversized grey crewneck sweatshirt, chunky white sneakers, and black crossbody bag', load_listings()[0]).split()))"
Scored these classic Levi's 501s for just $38 on Depop and I'm honestly obsessed with the knee fading. Threw them on with a chunky white sneaker and an oversized grey crewneck for the ultimate effortless morning coffee run fit. Nothing beats finding broken-in vintage denim that actually fits right.
```

---

## How I Used AI

<!-- Two specific moments. What you asked, what came back, what you changed.

     "I used Claude to help me code" is not enough.

     "I gave Claude my search_listings spec. It returned None on no match
     instead of an empty list, so I changed it" is the level we want. -->

**Moment 1**

- *What I asked for:* I asked AI to inspect the listing fields, six complete
     records, and the wardrobe schema before implementing the tools.
- *What came back:* It identified the exact listing and wardrobe field names,
     including that an empty wardrobe is `{"items": []}`.
- *What I changed:* I used those facts to document typed inputs, concrete
     return values, and empty cases in the Tool Inventory before coding.

**Moment 2**

- *What I asked for:* I asked AI to test both the matching and impossible query
     paths and check that the selected item reached `suggest_outfit` unchanged.
- *What came back:* The happy path completed all three tools, while the empty
     path left `fit_card` as `None` and returned an actionable error.
- *What I changed:* I made each tool read its input back from the session and
     added the explicit early-stop branch for an empty search result.

<!-- ═══════════════════════ UNIT 4 — THE TEST ═══════════════════════

     Don't fill these in during unit 3.
     ═══════════════════════════════════════════════════════════════════ -->

---

## Run Log — Before

<!-- Five criteria, five tries each, in this exact format.

     Five, because your criteria are written out of five. Mark each try PASS
     or FAIL, count the passes, and read that count against your target — a
     row targeting 4 of 5 with three PASS cells is MISSED (3/5).

     `python run_eval.py --label before` runs everything and writes the table
     into results/. Paste it here and fill in the verdicts. -->

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| 1.  |  |  |  |  |  |  |  |
| 2.  |  |  |  |  |  |  |  |
| 3.  |  |  |  |  |  |  |  |
| 4.  |  |  |  |  |  |  |  |
| 5.  |  |  |  |  |  |  |  |

**Real output from one try**, pasted as text, naming the file and function
that produced it:

```

```

---

## Verdicts and Diagnoses

<!-- MET or MISSED per criterion against LAST UNIT's target, plus a sentence on
     how you decided.

     Then, for every miss: which of the four places it happened — a tool, the
     loop's branch, the session, or the model's output — AND the mechanism.

     Not a diagnosis:  "The fit card was bad."
     A diagnosis:      "The fit card criterion missed on 2 of 5 items. Both had
                        an empty brand field. My prompt puts the brand in the
                        first sentence, so the card opened with a blank and read
                        like a fragment. The tool worked; the prompt assumed a
                        field that isn't always there."

     Look for a pattern. Three misses on the same tool is one problem, not
     three. -->

| # | Criterion | Target | Verdict | How I decided |
|---|---|---|---|---|
| 1 |  |  |  |  |
| 2 |  |  |  |  |
| 3 |  |  |  |  |
| 4 |  |  |  |  |
| 5 |  |  |  |  |

**Diagnoses**



---

## Loop Trace

<!-- One full run, printed step by step, with the MCP call visible in it.

     `python app.py ask '...' --trace` once you've added the trace.step()
     calls in Milestone 2.

     Worth pasting BOTH the happy path and the empty-search path. The empty
     one should be visibly shorter, because it stops. If your two traces are
     the same length, your branch isn't working — and this is the fastest way
     anyone will ever find that out. -->

**Happy path**

```
[1] search_listings (via MCP)
     in:  dict with keys: description, size, max_price
     out: 10 items: Y2K Baby Tee — Butterfly Print, Graphic Tee — 2003 Tour Bootleg Style, Vintage Band Tee — Faded Grey … +7 more
[2] suggest_outfit
     in:  dict with keys: new_item, wardrobe
     out: Here are two complete outfits featuring your new Y2K baby tee:  **Outfit 1: Y2K Streetwear (Casual & Cool)** *…
[3] create_fit_card
     in:  dict with keys: outfit, new_item
     out: Scored this dreamy butterfly baby tee for just $18 on Depop and I am obsessed. I paired the cropped fit with b…
```

**Empty search**

```
[1] search_listings (via MCP)
     in:  dict with keys: description, size, max_price
     out: [] (empty)
     →    empty; stopping
```

**On the MCP move:** <!-- what changed in your code, and whether anything
behaved differently afterwards. If the rewire didn't work, say exactly where it
broke — the error text and the last thing that worked. That earns the point in
full. -->

`run_agent()` calls `search_listings` through `mcp_client.call_tool`. The MCP
call returned the same list of listing dicts as the direct implementation.

**Failure checks**

- Empty search (`qzxv blorptastic nebuloid quuxorium`): “No listings matched.
     Try a broader description, a different size, or a higher maximum price.” The
     agent stopped after the MCP search.
- Empty wardrobe (`python app.py ask 'vintage graphic tee under $30' --empty-wardrobe`): “Here are
     two wearable, Y2K-inspired outfit ideas for your butterfly baby tee.” It
     returned two general styling ideas and a non-empty fit card without crashing.
- Model unavailable (`corduroy wide leg pants rust`, with a one-character key
     change and cache disabled): “The model couldn't provide outfit advice. The
     model rejected your API key. Check `GEMINI_API_KEY` in your `.env` file, or create
     a fresh key at aistudio.google.com.” No stack trace was shown; `.env` was
     restored and verified after the test.


---

## The Improvement

<!-- What you changed, why your diagnosis pointed at it, and the after-run in
     the same table format. One change, measured properly.

     `python run_eval.py --label after` -->

**What I changed:**

**Which failure it was meant to fix:**

### Run Log — After

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| 1.  |  |  |  |  |  |  |  |
| 2.  |  |  |  |  |  |  |  |
| 3.  |  |  |  |  |  |  |  |
| 4.  |  |  |  |  |  |  |  |
| 5.  |  |  |  |  |  |  |  |

**Did it help, and how do I know:**

<!-- If it made things worse, say that. Honestly reported, that earns full
     credit and is more interesting than one that worked. -->



---

## What's Still Broken

<!-- For each criterion still missed: what you'd do, and why you stopped where
     you did. "I ran out of time" is fine if it's true. Pretending nothing is
     left is not. -->



<!-- ═════════════════════════════════════════════════════════════════════

     SUBMISSION CHECKLIST — unit 3

       [ ] criteria.md has five numbered criteria, each with a target
       [ ] Each criterion has a reason underneath it
       [ ] All five unit 3 sections above have real content
       [ ] Tool Inventory: all three tools, inputs WITH TYPES, a specific
           return value, and the empty case
       [ ] Planning Loop names the branch rule and agent.py::run_agent
       [ ] Sample Run: one full query plus the three per-tool tests, as text
       [ ] At least four new commits
       [ ] Repository URL submitted — WRITE IT DOWN, you submit the same one
           next unit

     SUBMISSION CHECKLIST — unit 4

       [ ] mcp_server.py exists with one tool registered
           (or a written record of exactly where the rewire broke)
       [ ] Run Log — Before, five criteria, five tries each
       [ ] Real output pasted underneath, naming file and function
       [ ] A verdict on every criterion
       [ ] A diagnosis for every miss, naming a place AND a mechanism
       [ ] Loop Trace, with the MCP call visible in it
       [ ] All three failure modes triggered and handled
       [ ] One improvement, with Run Log — After in the same format
       [ ] What's Still Broken
       [ ] At least four new commits
       [ ] The SAME repository URL as last unit

     Do not delete and recreate this repository. Your commit history is what
     shows your criteria existed before your results did.
     ═════════════════════════════════════════════════════════════════════ -->

---

📖 **How to run this project: [RUNNING.md](RUNNING.md)**
