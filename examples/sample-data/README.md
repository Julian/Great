# Sample data repo

Minimal Great data repo demonstrating every entity. Build it with:

```sh
cd examples/sample-data
uv --project ../.. run great build
open dist/index.html
```

Layout:

- `great.toml` — list config
- `items/{kinds}.toml` — items by pluralized kind (`movies.toml`, `tv.toml`, …); each id unique within its file
- `comparisons/{list}.jsonl` — append-only ranking judgments
- `log/{year}.jsonl` — append-only consumption diary
- `want/{list}.toml` — want-to-consume queue (mutable; pruned on consume)
