# Website (`danieltroberts.github.io`) — Agent Guide

Public academic website for Daniel T. Roberts (`https://www.danieltroberts.com`), built with a zero-dependency Python 3.13 static site generator (`build.py`) and deployed via GitHub Actions to GitHub Pages.

## 1. Repository Layout

- `content/site.toml` — Site title, role, affiliation, contact, nav, headshot path, external profile links.
- `content/about.md` — Home page bio paragraphs.
- `content/research.toml` — Working papers, peer-reviewed publications, works in progress, and other writing.
- `content/teaching.toml` — Courses grouped by institution.
- `templates/base.html` — Shared HTML5 page shell.
- `assets/` — Stylesheet (`css/style.css`), progressive JS (`js/main.js`), headshot & favicon (`img/`).
- `files/` — Future self-hosted syllabi or paper PDFs (referenced as `/files/<filename>.pdf`).
- `Daniel_Roberts_CV.pdf` — **Managed externally** by `C:\Work\Career\scripts\publish-cv.ps1`. Do not edit or overwrite manually.
- `build.py` — Static generator, validator (`--check`), and local preview server (`--serve`).

## 2. Hard Rules

1. **Strict Privacy Boundary:** Never read private directories in `C:\Work\Career\` (`applications/`, `letters/`, `statements/`, `archive/`) or copy files manually from `Career\` into `Website\`. Only `Career\scripts\publish-cv.ps1` updates `Daniel_Roberts_CV.pdf`.
2. **Do Not Auto-Import Unrequested CV Items:** `Daniel_Roberts_CV.tex` intentionally includes items (e.g., advising, references, upcoming appointments, draft links) that may not belong on the public website yet. Only add or change website content when the user asks or explicitly confirms after a comparison.
3. **Reserved GitHub Pages Paths:** Never create top-level directories or routes named `working_papers`, `market_supplemental`, `paper_archive`, or `CV_Git` — those paths serve sibling GitHub Pages project repositories under `danieltroberts.github.io` / `www.danieltroberts.com`.
4. **No UTF-8 BOM:** Never write UTF-8 BOMs to `.py`, `.toml`, `.md`, `.html`, `.css`, `.js`, or `.yml` files (avoid PowerShell `Set-Content -Encoding UTF8` in Windows PowerShell 5.1).
5. **Always Validate:** Run `python build.py --check` before committing or reporting work complete.

## 3. Content Schemas (Copy-Paste Examples)

### Add a Working Paper (`content/research.toml`)

```toml
[[working_papers]]
title = "Paper Title"
featured = false
topics = ["Political Economy"]
primary_url = "https://danieltroberts.github.io/working_papers/filename.pdf"
abstract = """
Full abstract text here.
"""

[[working_papers.links]]
label = "Latest Version"
url = "https://danieltroberts.github.io/working_papers/filename.pdf"
```

### Add a Publication (`content/research.toml`)

```toml
[[publications]]
title = "Article Title"
authors = "Daniel T. Roberts and Coauthor"
year = "2026"
venue = "Journal Name"
details = "12(3): 45–67"
featured = true
topics = ["Topic"]
primary_url = "https://doi.org/..."
abstract = """
Abstract text here.
"""
bibtex = """
@article{roberts2026key,
  title   = {Article Title},
  author  = {Roberts, Daniel T. and Coauthor},
  journal = {Journal Name},
  year    = {2026}
}
"""

[[publications.links]]
label = "Journal"
url = "https://doi.org/..."
```

### Add a Course (`content/teaching.toml`)

```toml
[[institutions]]
name = "Taipei School of Economics and Political Science"
location = "National Tsing Hua University"
past = false  # Set past = true for collapsible entries under Past Teaching

[[institutions.courses]]
term = "Fall 2026"
badge = "Upcoming"  # Optional tag
title = "The Political Economy of AI"
subtitle = "Growth, Inequality, and Structural Change"
role = "Instructor, Graduate Seminar"
syllabus_url = "/files/Syllabus_PE_AI.pdf"
```

## 4. Build & Preview Commands

```powershell
python build.py --check   # Build into _site/ and validate schemas, assets, links, and BOMs
python build.py --serve   # Build, validate, and preview locally at http://127.0.0.1:8000
```

## 5. Scheduled & Future Updates

- **February 2027 role transition (monthly update checker):** Once the Assistant Professor appointment begins in February 2027, update:
  1. `content/site.toml`: set `role = "Assistant Professor of Political Science"` and update `description` accordingly.
  2. `content/about.md`: update the opening sentence to `"I am an Assistant Professor of Political Science at the Taipei School of Economics and Political Science (TSE) at National Tsing Hua University."`
  3. `content/teaching.toml`: remove `badge = "Upcoming"` from *The Political Economy of AI* (and optionally add `syllabus_url` once finalized).
  4. Run `python build.py --check`, commit, and push to `main`.
- **Optional future addition — Selected Research on Home:** `build.py` supports a compact Selected Research section on the Home page controlled by `show_selected_research = false` in `content/site.toml`. Keep it `false` unless the user asks to enable it.
