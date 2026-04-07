# 12 Curated v8 Tasks

This is the **definitive list** of the 12 tasks that make up the
browser-pilot v8 baseline. Phase 1 of caliper must port all 12 with
their bucket assignments preserved.

The tasks are pulled from the WebVoyager benchmark
(`browser-pilot/tests/agent/data/WebVoyager_data.jsonl`) but were
hand-curated to satisfy three constraints:

1. **Stable** — golden references where possible (5 of 12 are golden)
2. **Diverse** — span 4 task patterns (lookup / search / compare / navigate)
3. **Tractable** — solvable in ≤12 turns by a competent agent

Original curation rationale lives in
`browser-pilot/tests/agent/v7_baseline.py:18`. This document mirrors it
verbatim so caliper is self-contained.

---

## Bucket: lookup (3 tasks)

Single-fact retrieval. The agent navigates to one specific page and
extracts an answer that's stable across time.

### `Cambridge Dictionary--3` — zeitgeist

```yaml
id: "Cambridge Dictionary--3"
bucket: lookup
why_chosen: "Pronunciation/definition lookup; deterministic answer; non-time-sensitive"
goal: "Look up the definition, pronunciation, and examples of the word 'zeitgeist.'"
start_url: "https://dictionary.cambridge.org/"
reference_answer: "UK: /ˈtsaɪt.ɡaɪst/ or /ˈzaɪt.ɡaɪst/, US: /ˈtsaɪt.ɡaɪst/ or /ˈzaɪt.ɡaɪst/; the general set of ideas, beliefs, feelings, etc."
reference_type: possible
```

### `Wolfram Alpha--0` — derivative

```yaml
id: "Wolfram Alpha--0"
bucket: lookup
why_chosen: "Math task; golden reference; small numeric answer"
goal: "derivative of x^2 when x=5.6"
start_url: "https://www.wolframalpha.com/"
reference_answer: "11.2"
reference_type: golden
```

### `Wolfram Alpha--2` — large exponentiation

```yaml
id: "Wolfram Alpha--2"
bucket: lookup
why_chosen: "Math task; golden reference; tests scientific notation extraction"
goal: "Calculate 3^71 and retain 5 significant figures in scientific notation."
start_url: "https://www.wolframalpha.com/"
reference_answer: "7.5095 * 10^33"
reference_type: golden
```

---

## Bucket: search (3 tasks)

Find one specific item from a list of search results. The agent must
filter / rank results against criteria, not just look up a fact.

### `Allrecipes--3` — vegan cookies

```yaml
id: "Allrecipes--3"
bucket: search
why_chosen: "Search + filter (rating + review count); golden reference"
goal: "Locate a recipe for vegan chocolate chip cookies with over 60 reviews and a rating of at least 4.5 stars."
start_url: "https://www.allrecipes.com/"
reference_answer: "'Vegan Chocolate Chip, Oatmeal, and Nut Cookies', 4.9 star, 67 viewers (> 60)"
reference_type: golden
```

### `Coursera--0` — beginner 3D printing

```yaml
id: "Coursera--0"
bucket: search
why_chosen: "Multi-criterion search (level + topic + duration)"
goal: "Find a beginner-level online course about '3d printing' which lasts 1-3 months, and is provided by a top-ranking institution on Coursera."
start_url: "https://www.coursera.org/"
reference_answer: "Rapid Prototyping Using 3D Printing, Specialization"
reference_type: possible
```

### `Huggingface--3` — most-liked cc-by-sa-4.0 model

```yaml
id: "Huggingface--3"
bucket: search
why_chosen: "License-filtered search + ranking by likes"
goal: "Look up a model with a license of cc-by-sa-4.0 with the most likes on Hugging face."
start_url: "https://huggingface.co/"
reference_answer: "replit/replit-code-v1-3b"
reference_type: possible
```

---

## Bucket: compare (3 tasks)

Weigh 2+ candidates against attributes. Hardest bucket — both Sonnet
and gpt-5.4 fail more often here. Multi-page navigation amplifies
context cost.

### `Apple--0` — MacBook Air price comparison

```yaml
id: "Apple--0"
bucket: compare
why_chosen: "Multi-model comparison; reference is stale (2023 → M2 chip)"
goal: "Compare the prices of the latest models of MacBook Air available on Apple's website."
start_url: "https://www.apple.com/"
reference_answer: "MacBook Air 13-inch M1 chip: from $999; 13-inch M2 chip: from $1099; 15-inch M2 chip: from $1299"
reference_type: possible
notes: "Reference is from 2023. As of 2026 the current chip is M5 at the same prices. The v8 stale-ref-tolerant judge accepts the M5 answer; older judges did not."
```

### `Apple--3` — iPhone Pro vs Pro Max

```yaml
id: "Apple--3"
bucket: compare
why_chosen: "2-product comparison; reference is stale (2023 → iPhone 15)"
goal: "Find the latest model of the iPhone and compare the price and screen size between the pro and pro max."
start_url: "https://www.apple.com/"
reference_answer: "iPhone 15 pro starts from $999, 6.1-inch screen; iPhone 15 pro max starts from $1199, 6.7-inch screen"
reference_type: possible
notes: "As of 2026 the current model is iPhone 17 Pro/Pro Max. The v8 judge accepts answers about iPhone 17 with current pricing. This is the one task where Sonnet sometimes hits the 12-step limit with an empty answer."
```

### `Allrecipes--0` — vegetarian lasagna with criteria

```yaml
id: "Allrecipes--0"
bucket: compare
why_chosen: "Search + filter + servings comparison; sourced from original 7-task v6 set for continuity"
goal: "Provide a recipe for vegetarian lasagna with more than 100 reviews and a rating of at least 4.5 stars suitable for 6 people."
start_url: "https://www.allrecipes.com/"
reference_answer: "'Vegetarian Four Cheese Lasagna', 4.6-star, 181 reviews, Servings 8"
reference_type: possible
```

---

## Bucket: navigate (3 tasks)

Follow a chain of pages and extract specific structured info. Requires
both navigation and content extraction.

### `GitHub--3` — Enterprise vs Team storage

```yaml
id: "GitHub--3"
bucket: navigate
why_chosen: "Documentation lookup; golden reference; deterministic"
goal: "Find out how much more package storage the Enterprise version has over Team in GitHub Pricing."
start_url: "https://github.com/"
reference_answer: "48GB"
reference_type: golden
```

### `BBC News--5` — climate change guide

```yaml
id: "BBC News--5"
bucket: navigate
why_chosen: "Find specific article + extract specific quote; golden reference"
goal: "Find the article 'What is climate change? A really simple guide' and use it to answer what is causing recent climate change."
start_url: "https://www.bbc.com/news"
reference_answer: "This recent climate change has been caused by human activity, mainly the widespread use of fossil fuels - coal, oil and gas"
reference_type: golden
```

### `ArXiv--2` — most recent cs.CL paper abstract

```yaml
id: "ArXiv--2"
bucket: navigate
why_chosen: "Recent-paper navigation + abstract extraction; reference is structural not literal"
goal: "Look up the most recent papers related to 'cs.CL', select one and show its abstract."
start_url: "https://arxiv.org/"
reference_answer: "cs.CL paper, <abstract>"
reference_type: possible
notes: "Reference is intentionally structural (any cs.CL paper with its abstract counts). The judge accepts any plausibly real cs.CL abstract."
```

---

## Loading these in caliper

In M1.3 you'll convert this list to a JSONL file
(`examples/browser_pilot_v8/data.jsonl`) where each line is one task with
this schema:

```json
{
  "id": "Cambridge Dictionary--3",
  "input": "Look up the definition, pronunciation, and examples of the word 'zeitgeist.'",
  "target": "UK: /ˈtsaɪt.ɡaɪst/ or /ˈzaɪt.ɡaɪst/, US: /ˈtsaɪt.ɡaɪst/ or /ˈzaɪt.ɡaɪst/; the general set of ideas, beliefs, feelings, etc.",
  "metadata": {
    "bucket": "lookup",
    "start_url": "https://dictionary.cambridge.org/",
    "reference_type": "possible",
    "source": "WebVoyager"
  }
}
```

Inspect AI's `Sample` constructor maps these directly:
- `input` → the task goal (becomes the user's first message)
- `target` → reference answer (used by the judge scorer)
- `metadata` → arbitrary fields, accessed in scorers via `state.metadata`

A loader function in `src/caliper/datasets/webvoyager.py` should produce
a `Dataset` of `Sample` objects from the JSONL.

---

## Why these 12 and not others

Tasks NOT in this list that we considered but rejected:

| Task | Why rejected |
|---|---|
| `GitHub--1` (decision tree repo) | Verdict flipped across runs in v6 variance analysis — unstable |
| `GitHub--2` (trending Python) | Time-sensitive (trending changes daily) |
| `ESPN--0/--1/--2` (NBA standings) | Time-sensitive; ESPN shows season-to-date data |
| `Allrecipes--1` / `Allrecipes--2` | Less stable than --3 across runs |
| `Cambridge Dictionary--0/--1/--2` | --3 was chosen as the canonical dict task; others are redundant |
| Most `BBC News`, `Booking`, `Google Flights` | Heavily time-sensitive |

The rejected tasks are still useful for **stress testing** caliper
(intentionally noisy tasks help evaluate the variance machinery), but
they should not be in the **stable baseline**.

---

## Updating this list

When you add new curated tasks (Phase 3+), the rules are:

1. Each task must have a clear bucket assignment
2. Time-sensitive tasks need either golden refs or stale-ref-tolerant
   notes
3. The task list should grow only when adding a new bucket or new
   failure mode the existing 12 don't cover
4. Removed tasks should be archived in this doc with reason, not
   deleted
