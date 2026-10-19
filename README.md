# Jiajun Li — personal website

A static academic and engineering portfolio for GitHub Pages. Pages are served directly from the repository root, with no runtime dependencies or third-party scripts.

The visual design takes cues from [PSI](https://www.psi.ch/en): black-and-white sans-serif typography, deep blue accents inspired by Citadel Securities, subtle gray-blue color fields, and simple editorial rows. The homepage retains a concise introduction and selected publications. All fonts use a local system stack.

## Local preview

```sh
python3 -m http.server 8000
```

Open http://localhost:8000. Stop with Ctrl+C.

## Content and maintenance

- `index.html`: minimal introduction, profile links, a compact experience timeline, and five compact selected publications.
- `about.html`: professional background, education, and research themes.
- `publications.html`: searchable full bibliography, paper links, and individual BibTeX citations.
- `projects.html`: QLeaf, QuDrip, OptIndex, RL Tools, and the collaborative NESSi 2.0 contribution.
- `contact.html`: LinkedIn, Google Scholar, and GitHub profiles.
- `data/publications.json`: reviewed bibliographic metadata and access links.
- `scripts/build_site.py`: page templates, profile copy, project descriptions, and static generation.
- `assets/style.css`: responsive layout and print styling.
- `assets/publications.js`: progressive search, type/year filters, and reset behavior.
- `assets/publications.bib`: downloadable UTF-8 bibliography (biblatex/biber recommended).

Edit the publication dataset or the page content in `scripts/build_site.py`, then regenerate:

```sh
python3 scripts/build_site.py
```

Commit both the source edits and the generated HTML/BibTeX. GitHub Pages does not need to run the generator. All publication records and links remain available without JavaScript. Search matches title, authors, venue, year, DOI, arXiv ID, and earlier titles, ignoring case and diacritics.

## Homepage selection

The `selected` flags in `data/publications.json` control the homepage. The selection includes NESSi 2.0, both first-author Physical Review Letters papers, Aaram Kim’s Physical Review Letters paper on vertex-based treatment of light–matter systems, and the Nature Communications paper. The complete bibliography remains unchanged.

Selections display newest year first, with citation count as the same-year tiebreaker. Citation counts use the Scholar snapshot retrieved on 19 October 2026; a subsequent refresh was rate-limited. Counts are recorded as editorial metadata and are not displayed on the site.

## Sources and editorial decisions

Checked on 19 October 2026:

- [Google Scholar](https://scholar.google.com/citations?user=tP-VfEAAAAAJ&hl=en): all 46 profile entries and individual citation metadata were retrieved. Four duplicate entries are consolidated into their journal articles; their earlier titles and source links are retained in `aliases`.
- [LinkedIn](https://www.linkedin.com/in/jiajunli/): direct access was blocked. The publicly indexed [Swiss profile](https://ch.linkedin.com/in/jiajunli) confirms the quantitative research background and computational sciences certificate. The owner supplied the complete profile text in this session, including QRT and IMC roles, garden leave, PSI fellowship, FAU research role, and degrees at Buffalo and Beijing Normal University. Employment dates come from that text. Degree dates were not supplied; only the separately verified 2017 doctoral thesis date is shown. Private analytics and social activity from the pasted profile are not included.
- [GitHub](https://github.com/LiJ21): project descriptions were checked against the four personal repositories' current READMEs and the [NESSi repository](https://github.com/nessi-cntr/nessi). Performance figures are deliberately left in the repositories, where hardware and methodology are documented.
- [Eckstein group publication list](https://www.physik.uni-hamburg.de/th1/ag-eckstein/publikationen.html): identifies the additional photon-mediated spin interaction paper, subsequently published as Physical Review B 109, 085149 (2024). The arXiv record and Crossref metadata confirm its publication and authors.
- arXiv records: verified titles, author lists, journal references, and identifiers. Scholar omissions of η, Sr₂IrO₄, and 1T-TaS₂ were repaired from publication metadata.
- Crossref publisher metadata: checked journal metadata and version-of-record open licenses. Confirmed open-access papers use journal PDFs; other papers use arXiv PDFs. The open-access IOP proceedings paper uses its Scholar-listed publisher PDF. Publisher bot restrictions can prevent automated PDF checks even when a link is valid.

The bibliography contains 28 journal/proceedings articles, 4 standalone preprints, 1 thesis, and 10 meeting abstracts, totaling 43 distinct records. Meeting abstracts have record links, not invented paper downloads. Preprints and published versions are not double-counted. No citation counts are displayed because they change frequently.

## Validation

Local HTML landmarks, navigation, fragment links, bibliography coverage, JavaScript syntax, and publication filter behavior passed checks. All six pages and their assets served successfully over local HTTP. Thirty PDF links returned PDF content; two APS PDF endpoints returned HTTP 403 and the IOP PDF endpoint returned a bot challenge. Those three publisher-provided links remain in place. Browser-based visual QA was unavailable because no browser surface was connected.

## Publish

Push the files to `main` in `LiJ21/LiJ21.github.io`. Configure the repository's **Settings → Pages** to deploy from the `main` branch and `/ (root)` directory. The intended site address is https://lij21.github.io/.

`.nojekyll` keeps the deployment a plain static site. This edit does not commit, push, or alter hosting settings.
