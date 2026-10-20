# Translation workflow

English is the source language. Simplified Chinese is published at `/zh/`.
Everything is stored in Git; visitors need no translation service or API key.

## Files

- `zh-Hans.yaml`: your authored paragraph and UI translations.
- `automatic/zh-Hans.json`: generated drafts, initially translated with AI assistance.
- `source/zh-Hans.json`: generated catalog containing English text, keys, and hashes.
- `reports/zh-Hans.json`: missing, invalid, and outdated translations.
- `glossary/zh-Hans.yaml`: consistent terminology and names to preserve.
- `languages.json`: enabled languages, URL prefixes, and language-switch labels.
- `../content/translations/zh-Hans/posts/<slug>.md`: optional complete authored note.

Edit source files, not generated `/zh/` HTML. Commit sources, translation data,
and generated output together. Publication citations, code, numbers, and links
are preserved; surrounding prose and SVG diagram labels are translated.

## Edit a paragraph

Copy a current draft into the authored file:

```sh
python3 scripts/update_translations.py --promote home.introduction
```

Then edit its `html` in `translations/zh-Hans.yaml`. This contains ordinary HTML,
not translation placeholders. Alternatively add plain text directly:

```yaml
home.introduction:
  text: "这里写你自己的中文简介。"
```

Use `html` to retain inline links or emphasis, or `text` for plain text. A whole
block is replaced, so include all of its intended content. After reviewing:

```sh
python3 scripts/update_translations.py --accept home.introduction
```

This records the current English hash. Later English edits flag the authored
translation for review but never overwrite it, including its numbers and links.
Run the command without options to inspect the report.

Stable keys appear in `data-i18n` attributes in English page templates. For new
note paragraphs, put a unique marker immediately before the block:

```markdown
<!-- i18n: my-note.introduction -->

The English paragraph.
```

Keep the marker when moving or editing the paragraph; do not renumber existing
markers. Tables and lists use keys within their parent block. New unmarked text
still translates using a content-based key, but edits produce a new key.

## Supply a complete Chinese note

Create `content/translations/zh-Hans/posts/qleaf-inference-latency.md`:

```markdown
---
title: "你的中文标题"
summary: "用于文章列表和 RSS 的摘要。"
source_hash: "当前英文 Markdown 文件的 SHA-256"
---

## 第一节

你的完整中文正文。
```

Get the hash with:

```sh
sha256sum content/posts/2026-10-19-qleaf-inference-latency.md
```

The authored note replaces the translated body, title, and summary, including
the article list and RSS. It may use its own images or shared `/assets/` images.
It stays intact after English edits; the report flags it for review. Update
`source_hash` after reviewing. Use level-two headings, since the title supplies H1.
Other UI text continues to use the paragraph translation system.

## Refresh automatic drafts

An ordinary build uses the cache and makes **no network requests**:

```sh
python3 scripts/build_site.py
```

Missing or outdated automatic translations fall back to English and are reported.
To generate replacements, enable Google Cloud Translation Basic in a project
with billing, and set `GOOGLE_TRANSLATE_API_KEY` in your shell environment.
Do not put the key in this repository or browser code.

```sh
python3 scripts/update_translations.py --translate --limit 20
# Omit --limit to update all missing/outdated units.
```

Only missing or outdated units without an authored override are submitted.
The service can incur charges. Successful batches are cached for subsequent
offline builds; protected placeholders are checked before saving. The key is
used by the local Python command only. No API key is configured in this repo,
and the live API has not been exercised as part of the initial setup.

See [Google's authentication documentation](https://docs.cloud.google.com/translate/docs/authentication)
for API-key setup. This command is deliberately separate from the offline build;
it can also be run in a CI job with a secret, if desired.

## Additional languages

Add a language entry to `languages.json` with a unique code and URL prefix,
localized notice/feed/count strings, and a corresponding glossary and authored
YAML file. Run the updater with `--language <code> --translate`. The build
generates locale pages, RSS, sitemap entries, and reciprocal `hreflang` links.
The initial configuration enables English and Simplified Chinese only.
