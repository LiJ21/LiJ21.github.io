# Jiajun Li — personal website

A static academic and engineering portfolio for GitHub Pages. Pages are served directly from the repository root, with no runtime dependencies or third-party scripts.

The visual design takes cues from [PSI](https://www.psi.ch/en): black-and-white sans-serif typography, black accents, neutral gray color fields, and simple editorial rows. The homepage retains a concise introduction and selected publications. All fonts use a local system stack.

## Local preview

```sh
python3 -m http.server 8000
```

Open http://localhost:8000. Stop with Ctrl+C.

## Content and maintenance

- `index.html`: minimal introduction, profile links, a compact experience timeline, a PhD summary, three selected-project categories, and five compact selected publications.
- `about.html`: professional background, education, and research themes.
- `publications.html`: searchable full bibliography, paper links, and individual BibTeX citations.
- `projects.html`: QLeaf, QuDrip, OptIndex, RL Tools, and the collaborative NESSi 2.0 contribution.
- `contact.html`: LinkedIn, Google Scholar, and GitHub profiles.
- `data/publications.json`: reviewed bibliographic metadata and access links.
- `content/pages/*.html`: editable English page content, including the profile.
- `content/pages.yaml`: page titles and descriptions.
- `content/projects.yaml`: project descriptions.
- `scripts/build_site.py`: shared page layout and static generation.
- `assets/style.css`: responsive layout and print styling.
- `assets/publications.js`: progressive search, type/year filters, and reset behavior.
- `assets/publications.bib`: downloadable UTF-8 bibliography (biblatex/biber recommended).

Edit the publication dataset or files under `content/`, then regenerate:

```sh
python3 scripts/build_site.py
```

Commit both the source edits and the generated HTML/BibTeX. GitHub Pages does not need to run the generator. All publication records and links remain available without JavaScript. Search matches title, authors, venue, year, DOI, arXiv ID, and earlier titles, ignoring case and diacritics.

## Languages

English pages remain at their existing URLs; Simplified Chinese pages are under
`/zh/`. The language switch keeps the current page. The homepage uses the supplied
portrait in `assets/me.jpeg`.

Translations use authored overrides first, then a current automatic draft, then
English. Initial Chinese drafts are included, so ordinary builds work offline.
See [the translation guide](translations/README.md) for paragraph overrides,
complete Chinese notes, review reports, and API updates. Generated pages use
relative links so they also work when opened directly as HTML files. Preview
the generated root `index.html`, not the source fragments in `content/pages/`.

```sh
python3 scripts/update_translations.py
.venv/bin/python -m unittest discover -s tests -v
```

## Homepage selection

The `selected` flags in `data/publications.json` control the homepage. The selection includes NESSi 2.0, both first-author Physical Review Letters papers, Aaram Kim’s Physical Review Letters paper on vertex-based treatment of light–matter systems, and the Nature Communications paper. The complete bibliography remains unchanged.

Selections display newest year first, with citation count as the same-year tiebreaker. Citation counts use the Scholar snapshot retrieved on 19 October 2026; a subsequent refresh was rate-limited. Counts are recorded as editorial metadata and are not displayed on the site.

## Sources and editorial decisions

Checked on 19 October 2026:

- [Google Scholar](https://scholar.google.com/citations?user=tP-VfEAAAAAJ&hl=en): all 46 profile entries and individual citation metadata were retrieved. Four duplicate entries are consolidated into their journal articles; their earlier titles and source links are retained in `aliases`.
- [LinkedIn](https://www.linkedin.com/in/jiajunli/): direct access was blocked. The publicly indexed [Swiss profile](https://ch.linkedin.com/in/jiajunli) confirms the quantitative research background and computational sciences certificate. The owner supplied the complete profile text in this session, including QRT and IMC roles, garden leave, PSI fellowship, FAU research role, and degrees at Buffalo and Beijing Normal University. Employment dates come from that text. Degree dates were not supplied; only the separately verified 2017 doctoral thesis date is shown. Private analytics and social activity from the pasted profile are not included.
- [GitHub](https://github.com/LiJ21): project descriptions were checked against the four personal repositories' current READMEs and the [NESSi repository](https://github.com/nessi-cntr/nessi). QLeaf’s latency summary refers to measured benchmark configurations; hardware, methodology, and detailed results are linked from its project entry.
- [Eckstein group publication list](https://www.physik.uni-hamburg.de/th1/ag-eckstein/publikationen.html): identifies the additional photon-mediated spin interaction paper, subsequently published as Physical Review B 109, 085149 (2024). The arXiv record and Crossref metadata confirm its publication and authors.
- arXiv records: verified titles, author lists, journal references, and identifiers. Scholar omissions of η, Sr₂IrO₄, and 1T-TaS₂ were repaired from publication metadata.
- Crossref publisher metadata: checked journal metadata and version-of-record open licenses. Confirmed open-access papers use journal PDFs; other papers use arXiv PDFs. The open-access IOP proceedings paper uses its Scholar-listed publisher PDF. Publisher bot restrictions can prevent automated PDF checks even when a link is valid.

The bibliography contains 28 journal/proceedings articles, 4 standalone preprints, 1 thesis, and 10 meeting abstracts, totaling 43 distinct records. Meeting abstracts have record links, not invented paper downloads. Preprints and published versions are not double-counted. No citation counts are displayed because they change frequently.

## Validation

The bilingual build has automated checks for translation precedence, stale-source
behavior, complete authored notes, protected benchmark numbers/code, local links,
assets, and language metadata. Browser checks cover the portrait, Chinese layout,
language switch, translated diagram, and publication search. The Google API
request is tested with a mock; no live API credentials are configured.

During the original bibliography check, thirty PDF links returned PDF content;
two APS PDF endpoints returned HTTP 403 and the IOP PDF endpoint returned a bot
challenge. Those three publisher-provided links remain in place.

## Publish

Push the files to `main` in `LiJ21/LiJ21.github.io`. Configure the repository's **Settings → Pages** to deploy from the `main` branch and `/ (root)` directory. The canonical site address is https://jjli.info/.

`.nojekyll` keeps the deployment a plain static site. This edit does not commit, push, or alter hosting settings.

## Notes

Notes are authored in `content/posts/*.md` and rendered to `blog/<slug>/index.html`.
`blog.html` lists published notes newest first, and `feed.xml` provides an RSS feed.
The explicit slug keeps the URL stable when the date or title changes.

Install the build dependencies once in a virtual environment:

```sh
python3 -m venv .venv
python3 -m pip --python .venv/bin/python install -r requirements.txt
```

If the system lacks `ensurepip`, create the environment with `python3 -m venv --without-pip .venv` instead, then use the same pip command above. The existing `python3 scripts/build_site.py` command automatically uses `.venv` when its dependencies are not available in the current interpreter.

Create an article with YAML metadata followed by Markdown:

```markdown
---
title: "A new note"
slug: a-new-note
date: 2026-10-19
summary: "A short description for the notes list and RSS feed."
tags: [Systems, Machine learning]
draft: true
---

Start the article here. Use level-two headings for sections.
```

Markdown supports tables, fenced code blocks, links, images, and footnotes.
Place figures in `assets/posts/<slug>/` and reference them with root-relative
paths such as `/assets/posts/a-new-note/figure.svg`. Article slugs must be unique,
lowercase words separated by hyphens. Dates use `YYYY-MM-DD`.

Set `draft: false` to include a note in the site and feed, then run:

```sh
.venv/bin/python scripts/build_site.py
python3 -m http.server 8000
```

Visit `/blog.html` to preview. Commit the Markdown source, generated pages,
updated navigation, and feed together. No server-side database or JavaScript is
required for notes. Generation removes previously generated article pages when
notes are deleted or returned to draft. Drafts are omitted from rendered pages
and RSS, but their Markdown remains visible if the repository is public.

The first note follows QLeaf’s latency ablation, framework structure, CPU workers,
and GPU optimizations. It links to a fixed source revision and includes six SVG
diagrams under `assets/posts/qleaf-inference-latency/`. To edit the diagrams, change
`scripts/draw_qleaf_diagrams.py` and run `python3 scripts/draw_qleaf_diagrams.py`.
The generated SVG files are served directly, without a diagram-rendering runtime.

## Search engine sitemap

Every build regenerates `sitemap.xml` with the main pages and published notes,
using `https://jjli.info`. Drafts and the 404 page are excluded. `robots.txt`
allows crawling and points to the sitemap. After deploying, submit
`https://jjli.info/sitemap.xml` in Google Search Console → Sitemaps.

Each published page includes an absolute canonical URL and Open Graph URL
matching its sitemap entry. Page titles and descriptions are generated with the
content; the homepage title identifies Jiajun Li and the site's focus. The 404
page has no canonical URL and remains excluded from the sitemap.

## Hosted journal PDFs

Thirteen unmodified APS journal PDFs are stored in `assets/papers/`, with download
provenance and checksums in `data/hosted-pdfs.json`. Copyright or CC BY notices
appear with the corresponding citations. Eleven other APS journal copies remain
unavailable; their existing arXiv download links are retained. See
[the PDF inventory](assets/papers/README.md) for the remaining papers.
