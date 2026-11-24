"""Zero-dependency static site builder and validator for danieltroberts.com."""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import html
import http.server
import os
import pathlib
import re
import shutil
import socketserver
import sys
import tomllib
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
TEMPLATES_DIR = ROOT / "templates"
ASSETS_DIR = ROOT / "assets"
FILES_DIR = ROOT / "files"
OUT_DIR = ROOT / "_site"

RESERVED_TOP_LEVEL = {
    "working_papers",
    "market_supplemental",
    "paper_archive",
    "CV_Git",
}

BOM_CHECK_EXTS = {".py", ".toml", ".md", ".html", ".css", ".js", ".yml", ".yaml"}


def e(text: object) -> str:
    """HTML-escape string safely."""
    return html.escape(str(text), quote=True)


def render_inline_markdown(text: str) -> str:
    """Render safe inline Markdown (links, bold, italic, code) with HTML escaping."""
    tokens: list[str] = []

    def stash(html_fragment: str) -> str:
        idx = len(tokens)
        tokens.append(html_fragment)
        return f"\x00TOK{idx}\x00"

    def repl_code(match: re.Match[str]) -> str:
        return stash(f"<code>{e(match.group(1))}</code>")

    def repl_link(match: re.Match[str]) -> str:
        label = e(match.group(1))
        url = match.group(2).strip()
        if url.startswith(("http://", "https://", "/", "mailto:")):
            return stash(f'<a href="{e(url)}">{label}</a>')
        return f"[{label}]({e(url)})"

    s = re.sub(r"`([^`]+)`", repl_code, text)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl_link, s)
    s = e(s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", s)

    for idx, fragment in enumerate(tokens):
        s = s.replace(f"\x00TOK{idx}\x00", fragment)
    return s


def render_markdown(md_text: str) -> str:
    """Render minimal block Markdown (headings, lists, paragraphs) cleanly."""
    lines = md_text.replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    para_lines: list[str] = []
    list_items: list[str] = []

    def flush_para() -> None:
        if para_lines:
            joined = " ".join(line.strip() for line in para_lines)
            blocks.append(f"<p>{render_inline_markdown(joined)}</p>")
            para_lines.clear()

    def flush_list() -> None:
        if list_items:
            items_html = "".join(
                f"<li>{render_inline_markdown(item)}</li>" for item in list_items
            )
            blocks.append(f"<ul>{items_html}</ul>")
            list_items.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            flush_para()
            flush_list()
            continue
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            flush_para()
            flush_list()
            level = len(heading_match.group(1))
            blocks.append(
                f"<h{level}>{render_inline_markdown(heading_match.group(2))}</h{level}>"
            )
            continue
        list_match = re.match(r"^[-*]\s+(.+)$", line)
        if list_match:
            flush_para()
            list_items.append(list_match.group(1))
            continue
        flush_list()
        para_lines.append(line)

    flush_para()
    flush_list()
    return "\n".join(blocks)


def load_toml(path: pathlib.Path) -> dict:
    with path.open("rb") as f:
        return tomllib.load(f)


def render_link_pills(links: list[dict], extra_class: str = "pill-link") -> str:
    if not links:
        return ""
    parts = []
    for item in links:
        label = e(item["label"])
        url = item["url"].strip()
        if not url:
            continue
        is_ext = url.startswith(("http://", "https://"))
        attrs = ' target="_blank" rel="noopener noreferrer"' if is_ext else ""
        parts.append(f'<a class="{extra_class}" href="{e(url)}"{attrs}>{label}</a>')
    if not parts:
        return ""
    return '<div class="entry-links">' + "".join(parts) + "</div>"


def render_drawers(abstract: str | None, bibtex: str | None) -> str:
    drawers: list[str] = []
    if abstract and abstract.strip():
        paragraphs = [
            f"<p>{render_inline_markdown(p.strip())}</p>"
            for p in abstract.strip().split("\n\n")
            if p.strip()
        ]
        drawers.append(
            '<details class="drawer">'
            "<summary>Abstract</summary>"
            f'<div class="drawer-body">{"".join(paragraphs)}</div>'
            "</details>"
        )
    if bibtex and bibtex.strip():
        drawers.append(
            '<details class="drawer">'
            "<summary>BibTeX</summary>"
            '<div class="drawer-body bibtex-wrap">'
            f'<pre class="bibtex-code">{e(bibtex.strip())}</pre>'
            '<button type="button" class="copy-btn" data-copy-bibtex>Copy BibTeX</button>'
            "</div>"
            "</details>"
        )
    if not drawers:
        return ""
    return '<div class="entry-drawers">' + "".join(drawers) + "</div>"


def render_paper_title(title: str, url: str | None) -> str:
    if url and url.strip():
        is_ext = url.strip().startswith(("http://", "https://"))
        attrs = ' target="_blank" rel="noopener noreferrer"' if is_ext else ""
        return f'<h3 class="paper-title"><a href="{e(url.strip())}"{attrs}>{e(title)}</a></h3>'
    return f'<h3 class="paper-title">{e(title)}</h3>'


def build_home(site: dict, about_md: str, research: dict) -> str:
    role_line = f'<span class="role">{e(site["role"])}</span>'
    aff_parts = [p for p in (site.get("affiliation"), site.get("university")) if p]
    aff_line = "<br>".join([role_line] + [e(p) for p in aff_parts])

    bio_html = render_markdown(about_md)

    contact_html = ""
    email_user = site.get("email_user", "").strip()
    email_domain = site.get("email_domain", "").strip()
    if email_user and email_domain:
        obfuscated = f'{email_user} [at] {email_domain.replace(".", " [dot] ")}'
        contact_html = (
            '<div class="hero-contact">'
            '<span class="contact-label">Email</span>'
            f'<span class="contact-address" data-eu="{e(email_user)}" data-ed="{e(email_domain)}">{e(obfuscated)}</span>'
            '<button type="button" class="copy-email-btn" data-copy-email aria-label="Copy email address">Copy</button>'
            "</div>"
        )

    profile_links = []
    for prof in site.get("profiles", []):
        if prof.get("url", "").strip():
            profile_links.append(
                f'<a href="{e(prof["url"].strip())}" target="_blank" rel="noopener noreferrer">{e(prof["label"])}</a>'
            )

    headshot_rel = "/" + site["headshot"].lstrip("/")
    headshot_alt = e(site.get("headshot_alt", site["author"]))

    featured_items: list[str] = []
    if site.get("show_selected_research", False):
        for wp in research.get("working_papers", []):
            if wp.get("featured"):
                title_html = (
                    f'<a href="{e(wp["primary_url"])}" target="_blank" rel="noopener noreferrer">{e(wp["title"])}</a>'
                    if wp.get("primary_url", "").strip()
                    else e(wp["title"])
                )
                featured_items.append(
                    '<li class="featured-item">'
                    '<span class="kicker">Working Paper</span>'
                    f'<div class="featured-title">{title_html}</div>'
                    f'{render_link_pills(wp.get("links", []))}'
                    "</li>"
                )
        for pub in research.get("publications", []):
            if pub.get("featured"):
                title_html = (
                    f'<a href="{e(pub["primary_url"])}" target="_blank" rel="noopener noreferrer">{e(pub["title"])}</a>'
                    if pub.get("primary_url", "").strip()
                    else e(pub["title"])
                )
                meta = f'{e(pub["authors"])} ({e(pub["year"])}). <em>{e(pub["venue"])}</em>, {e(pub["details"])}.'
                featured_items.append(
                    '<li class="featured-item">'
                    '<span class="kicker">Publication</span>'
                    f'<div class="featured-title">{title_html}</div>'
                    f'<div class="featured-meta">{meta}</div>'
                    f'{render_link_pills(pub.get("links", []))}'
                    "</li>"
                )

    selected_block = ""
    if featured_items:
        selected_block = (
            '<section class="selected-research" aria-labelledby="selected-heading">'
            '<div class="section-heading-row">'
            '<h2 id="selected-heading">Selected Research</h2>'
            '<a class="section-more" href="/research/">All research &amp; writing &rarr;</a>'
            "</div>"
            f'<ul class="featured-list">{"".join(featured_items)}</ul>'
            "</section>"
        )

    return (
        '<section class="hero">'
        '<div class="hero-content">'
        f'<h1 class="hero-title">{e(site["author"])}</h1>'
        f'<p class="hero-affiliation">{aff_line}</p>'
        f'<div class="hero-bio">{bio_html}</div>'
        f"{contact_html}"
        '<div class="hero-actions">'
        '<a class="btn-primary" href="/research/">Explore Research &rarr;</a>'
        f'<div class="profile-links">{"".join(profile_links)}</div>'
        "</div>"
        "</div>"
        '<figure class="portrait-col">'
        '<div class="portrait-frame">'
        f'<img src="{e(headshot_rel)}" alt="{headshot_alt}" width="900" height="1125">'
        "</div>"
        "</figure>"
        "</section>"
        f"{selected_block}"
    )


def build_research(research: dict) -> str:
    all_topics: list[str] = []
    for group in ("working_papers", "publications", "works_in_progress"):
        for item in research.get(group, []):
            for t in item.get("topics", []):
                if t not in all_topics:
                    all_topics.append(t)

    filter_html = ""
    if all_topics:
        pills = ['<button type="button" class="filter-pill is-active" data-topic="all" aria-pressed="true">All</button>']
        for topic in all_topics:
            pills.append(
                f'<button type="button" class="filter-pill" data-topic="{e(topic)}" aria-pressed="false">{e(topic)}</button>'
            )
        filter_html = (
            '<div class="topic-filter" data-topic-filter role="group" aria-label="Filter by topic">'
            '<span class="filter-label">Topic:</span>'
            f'{"".join(pills)}'
            "</div>"
        )

    wp_cards = []
    for wp in research.get("working_papers", []):
        topics = wp.get("topics", [])
        topic_attr = e("|".join(topics))
        wp_cards.append(
            f'<article class="paper-entry" data-topics="{topic_attr}">'
            f'{render_paper_title(wp["title"], wp.get("primary_url"))}'
            f'{render_link_pills(wp.get("links", []))}'
            f'{render_drawers(wp.get("abstract"), wp.get("bibtex"))}'
            "</article>"
        )

    pub_cards = []
    for pub in research.get("publications", []):
        topics = pub.get("topics", [])
        topic_attr = e("|".join(topics))
        meta = f'{e(pub["authors"])} ({e(pub["year"])}). <em>{e(pub["venue"])}</em>, {e(pub["details"])}.'
        pub_cards.append(
            f'<article class="paper-entry" data-topics="{topic_attr}">'
            f'{render_paper_title(pub["title"], pub.get("primary_url"))}'
            f'<p class="paper-meta">{meta}</p>'
            f'{render_link_pills(pub.get("links", []))}'
            f'{render_drawers(pub.get("abstract"), pub.get("bibtex"))}'
            "</article>"
        )

    wip_cards = []
    for wip in research.get("works_in_progress", []):
        topics = wip.get("topics", [])
        topic_attr = e("|".join(topics))
        note = f'<p class="paper-meta">({e(wip["note"])})</p>' if wip.get("note") else ""
        wip_cards.append(
            f'<article class="paper-entry" data-topics="{topic_attr}">'
            f'{render_paper_title(wip["title"], wip.get("primary_url"))}'
            f"{note}"
            f'{render_link_pills(wip.get("links", []))}'
            "</article>"
        )

    other_cards = []
    for item in research.get("other_writing", []):
        meta_parts = []
        if item.get("coauthors"):
            meta_parts.append(e(item["coauthors"]))
        if item.get("venue"):
            meta_parts.append(f'<em>{e(item["venue"])}</em>')
        if item.get("details"):
            meta_parts.append(e(item["details"]))
        if item.get("year"):
            meta_parts.append(e(item["year"]))
        if item.get("date"):
            meta_parts.append(e(item["date"]))
        meta_html = f'<p class="paper-meta">{", ".join(meta_parts)}</p>' if meta_parts else ""
        other_cards.append(
            '<article class="paper-entry">'
            f'{render_paper_title(item["title"], item.get("primary_url"))}'
            f"{meta_html}"
            f'{render_link_pills(item.get("links", []))}'
            "</article>"
        )

    return (
        '<header class="page-header">'
        f'<h1>{e(research.get("page_title", "Research and Writing"))}</h1>'
        '<nav class="jump-nav" aria-label="Page sections">'
        '<a href="#working-papers">Working Papers</a>'
        '<a href="#publications">Peer-Reviewed Publications</a>'
        '<a href="#works-in-progress">Works in Progress</a>'
        '<a href="#other-writing">Other Writing</a>'
        "</nav>"
        f"{filter_html}"
        "</header>"
        '<section id="working-papers" class="content-section">'
        "<h2>Working Papers</h2>"
        f'<div class="entry-list">{"".join(wp_cards)}</div>'
        "</section>"
        '<section id="publications" class="content-section">'
        "<h2>Peer-Reviewed Publications</h2>"
        f'<div class="entry-list">{"".join(pub_cards)}</div>'
        "</section>"
        '<section id="works-in-progress" class="content-section">'
        "<h2>Works in Progress</h2>"
        f'<div class="entry-list">{"".join(wip_cards)}</div>'
        "</section>"
        '<section id="other-writing" class="content-section">'
        "<h2>Other Writing</h2>"
        f'<div class="entry-list">{"".join(other_cards)}</div>'
        "</section>"
    )


def render_course_rows(courses: list[dict]) -> str:
    rows = []
    for course in courses:
        badge_html = (
            f'<span class="kicker course-badge">{e(course["badge"])}</span>'
            if course.get("badge")
            else ""
        )
        subtitle = (
            f'<div class="course-subtitle">{e(course["subtitle"])}</div>'
            if course.get("subtitle")
            else ""
        )
        syllabus = ""
        if course.get("syllabus_url", "").strip():
            syllabus = (
                '<div class="entry-links">'
                f'<a class="pill-link" href="{e(course["syllabus_url"].strip())}" target="_blank" rel="noopener noreferrer">Syllabus (PDF)</a>'
                "</div>"
            )
        rows.append(
            '<article class="course-item">'
            f'<div class="course-term"><span>{e(course["term"])}</span>{badge_html}</div>'
            '<div class="course-details">'
            f'<h3 class="course-title">{e(course["title"])}</h3>'
            f"{subtitle}"
            f'<div class="course-role">{e(course["role"])}</div>'
            f"{syllabus}"
            "</div>"
            "</article>"
        )
    return "".join(rows)


def build_teaching(teaching: dict) -> str:
    institutions = teaching.get("institutions", [])
    current_insts = [inst for inst in institutions if not inst.get("past", False)]
    past_insts = [inst for inst in institutions if inst.get("past", False)]

    sections = []
    for inst in current_insts:
        loc_html = (
            f'<p class="institution-sub">{e(inst["location"])}</p>'
            if inst.get("location")
            else ""
        )
        sections.append(
            '<section class="content-section">'
            f'<h2>{e(inst["name"])}</h2>'
            f"{loc_html}"
            f'<div class="course-list">{render_course_rows(inst.get("courses", []))}</div>'
            "</section>"
        )

    if past_insts:
        past_blocks = []
        for inst in past_insts:
            courses = inst.get("courses", [])
            count = len(courses)
            count_label = "1 course" if count == 1 else f"{count} courses"
            past_blocks.append(
                '<details class="past-institution">'
                '<summary class="past-institution-summary">'
                f'<span class="past-institution-name">{e(inst["name"])}</span>'
                f'<span class="past-institution-meta">{e(count_label)}</span>'
                "</summary>"
                '<div class="past-institution-body">'
                f'<div class="course-list">{render_course_rows(courses)}</div>'
                "</div>"
                "</details>"
            )
        sections.append(
            '<section class="content-section past-teaching" aria-labelledby="past-teaching-heading">'
            '<h2 id="past-teaching-heading" class="past-heading">Past Teaching</h2>'
            f'<div class="past-list">{"".join(past_blocks)}</div>'
            "</section>"
        )

    return (
        '<header class="page-header">'
        f'<h1>{e(teaching.get("page_title", "Teaching"))}</h1>'
        "</header>"
        f'{"".join(sections)}'
    )


def build_cv(site: dict) -> str:
    pdf_url = "/" + site["cv_pdf"].lstrip("/")
    return (
        '<header class="page-header">'
        "<h1>Curriculum Vitae</h1>"
        "</header>"
        '<div class="cv-toolbar">'
        f'<a class="btn-primary" href="{e(pdf_url)}" download>Download C.V. (PDF)</a>'
        f'<a class="pill-link" href="{e(pdf_url)}" target="_blank" rel="noopener noreferrer">Open in new tab &nearr;</a>'
        "</div>"
        '<div class="pdf-frame-wrap">'
        f'<object class="pdf-viewer" data="{e(pdf_url)}" type="application/pdf" aria-label="Curriculum Vitae PDF">'
        '<div class="pdf-fallback">'
        "<p>Your browser does not display embedded PDFs inline.</p>"
        f'<p><a href="{e(pdf_url)}">Download Daniel_Roberts_CV.pdf</a></p>'
        "</div>"
        "</object>"
        "</div>"
    )


def build_404() -> str:
    return (
        '<section class="not-found">'
        "<h1>Page not found</h1>"
        "<p>The page you requested could not be found.</p>"
        '<p><a href="/">Return to home page</a></p>'
        "</section>"
    )


def render_page(
    template: str,
    site: dict,
    *,
    title: str,
    description: str,
    path_suffix: str,
    active_nav: str,
    content: str,
    og_type: str = "website",
) -> str:
    nav_html = []
    for item in site["nav"]:
        url = item["url"]
        current = ' aria-current="page"' if url == active_nav else ""
        nav_html.append(f'<a href="{e(url)}"{current}>{e(item["label"])}</a>')

    footer_links = []
    for prof in site.get("profiles", []):
        if prof.get("url", "").strip():
            footer_links.append(
                f'<a href="{e(prof["url"].strip())}" target="_blank" rel="noopener noreferrer">{e(prof["label"])}</a>'
            )
    footer_links.append(f'<a href="/{e(site["cv_pdf"].lstrip("/"))}">C.V. (PDF)</a>')

    base_url = site["base_url"].rstrip("/")
    canonical = f"{base_url}{path_suffix}"
    headshot_url = f'{base_url}/{site["headshot"].lstrip("/")}'
    og_image_meta = f'<meta property="og:image" content="{e(headshot_url)}">'

    replacements = {
        "{{page_title}}": e(title),
        "{{meta_description}}": e(description),
        "{{canonical_url}}": e(canonical),
        "{{og_type}}": e(og_type),
        "{{og_title}}": e(title),
        "{{og_description}}": e(description),
        "{{og_image_meta}}": og_image_meta,
        "{{site_title}}": e(site["title"]),
        "{{nav_links}}": "".join(nav_html),
        "{{content}}": content,
        "{{year}}": str(dt.date.today().year),
        "{{author}}": e(site["author"]),
        "{{affiliation}}": e(site["affiliation"]),
        "{{university}}": e(site["university"]),
        "{{footer_links}}": "".join(footer_links),
    }
    output = template
    for key, val in replacements.items():
        output = output.replace(key, val)
    return output


def write_redirect_shim(target_path: pathlib.Path, destination: str, title: str) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{e(title)}</title>\n"
        f'  <meta http-equiv="refresh" content="0; url={e(destination)}">\n'
        f'  <link rel="canonical" href="{e(destination)}">\n'
        f'  <script>location.replace({destination!r});</script>\n'
        "</head>\n"
        f'<body><p>Redirecting to <a href="{e(destination)}">{e(destination)}</a>.</p></body>\n'
        "</html>\n"
    )
    target_path.write_text(body, encoding="utf-8", newline="\n")


def build() -> None:
    site = load_toml(CONTENT_DIR / "site.toml")
    research = load_toml(CONTENT_DIR / "research.toml")
    teaching = load_toml(CONTENT_DIR / "teaching.toml")
    about_md = (CONTENT_DIR / "about.md").read_text(encoding="utf-8")
    template = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pages = [
        (
            OUT_DIR / "index.html",
            render_page(
                template,
                site,
                title=site["title"],
                description=site["description"],
                path_suffix="/",
                active_nav="/",
                content=build_home(site, about_md, research),
                og_type="profile",
            ),
        ),
        (
            OUT_DIR / "research" / "index.html",
            render_page(
                template,
                site,
                title=f'{research.get("page_title", "Research")} — {site["title"]}',
                description=f'Working papers, publications, and writing by {site["author"]}.',
                path_suffix="/research/",
                active_nav="/research/",
                content=build_research(research),
            ),
        ),
        (
            OUT_DIR / "teaching" / "index.html",
            render_page(
                template,
                site,
                title=f'{teaching.get("page_title", "Teaching")} — {site["title"]}',
                description=f'Courses taught by {site["author"]}.',
                path_suffix="/teaching/",
                active_nav="/teaching/",
                content=build_teaching(teaching),
            ),
        ),
        (
            OUT_DIR / "cv" / "index.html",
            render_page(
                template,
                site,
                title=f'C.V. — {site["title"]}',
                description=f'Curriculum Vitae of {site["author"]}.',
                path_suffix="/cv/",
                active_nav="/cv/",
                content=build_cv(site),
            ),
        ),
        (
            OUT_DIR / "404.html",
            render_page(
                template,
                site,
                title=f'Page Not Found — {site["title"]}',
                description=site["description"],
                path_suffix="/404.html",
                active_nav="",
                content=build_404(),
            ),
        ),
    ]

    for out_path, rendered in pages:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8", newline="\n")

    # Legacy Google Sites paths
    write_redirect_shim(OUT_DIR / "home" / "index.html", "/", site["title"])
    write_redirect_shim(OUT_DIR / "c-v" / "index.html", "/cv/", f'C.V. — {site["title"]}')

    shutil.copytree(ASSETS_DIR, OUT_DIR / "assets")

    if FILES_DIR.exists():
        real_files = [p for p in FILES_DIR.rglob("*") if p.is_file() and p.name != ".gitkeep"]
        if real_files:
            for src in real_files:
                rel = src.relative_to(FILES_DIR)
                dst = OUT_DIR / "files" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    cv_src = ROOT / site["cv_pdf"]
    if cv_src.is_file():
        shutil.copy2(cv_src, OUT_DIR / site["cv_pdf"])

    for root_file in (".nojekyll", "CNAME"):
        src = ROOT / root_file
        if src.is_file():
            shutil.copy2(src, OUT_DIR / root_file)


def check() -> list[str]:
    errors: list[str] = []

    # 1. Required TOML validation
    try:
        site = load_toml(CONTENT_DIR / "site.toml")
        research = load_toml(CONTENT_DIR / "research.toml")
        teaching = load_toml(CONTENT_DIR / "teaching.toml")
    except Exception as exc:
        return [f"TOML parse error: {exc}"]

    for key in ("title", "author", "role", "affiliation", "base_url", "headshot", "cv_pdf", "nav"):
        if not site.get(key):
            errors.append(f"site.toml missing required key: {key}")

    if "working_papers" not in research or "publications" not in research:
        errors.append("research.toml missing working_papers or publications")

    if not teaching.get("institutions"):
        errors.append("teaching.toml missing institutions")

    # 2. Reserved top-level paths
    for reserved in RESERVED_TOP_LEVEL:
        if (OUT_DIR / reserved).exists():
            errors.append(f"Reserved GitHub Pages path collision in _site/: {reserved}")

    # 3. Critical static assets
    cv_out = OUT_DIR / site.get("cv_pdf", "Daniel_Roberts_CV.pdf")
    if not cv_out.is_file() or cv_out.stat().st_size == 0:
        errors.append(f"Missing or empty CV PDF in _site/: {cv_out}")

    headshot_out = OUT_DIR / site.get("headshot", "assets/img/headshot.jpg")
    if not headshot_out.is_file() or headshot_out.stat().st_size == 0:
        errors.append(f"Missing or empty headshot in _site/: {headshot_out}")

    for expected in (
        OUT_DIR / "index.html",
        OUT_DIR / "research" / "index.html",
        OUT_DIR / "teaching" / "index.html",
        OUT_DIR / "cv" / "index.html",
        OUT_DIR / "404.html",
        OUT_DIR / "assets" / "css" / "style.css",
        OUT_DIR / "assets" / "js" / "main.js",
    ):
        if not expected.is_file():
            errors.append(f"Missing expected output file: {expected.relative_to(ROOT)}")

    # 4. Internal link & asset resolution across generated HTML
    attr_re = re.compile(r'\b(?:href|src|data)=["\']([^"\']+)["\']')
    for html_file in OUT_DIR.rglob("*.html"):
        text = html_file.read_text(encoding="utf-8")
        for match in attr_re.finditer(text):
            target = match.group(1).strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#", "javascript:", "data:")):
                continue
            parsed = urlparse(target)
            rel_path = parsed.path
            if rel_path.startswith("/"):
                candidate = OUT_DIR / rel_path.lstrip("/")
            else:
                candidate = html_file.parent / rel_path
            if rel_path.endswith("/") or candidate.is_dir():
                resolved = candidate / "index.html"
            else:
                resolved = candidate
            if not resolved.exists():
                errors.append(
                    f"Broken internal link in {html_file.relative_to(OUT_DIR)}: {target}"
                )

    # 5. No UTF-8 BOM in tracked source files
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {"_site", ".git", "__pycache__"} for part in path.parts):
            continue
        if path.suffix.lower() in BOM_CHECK_EXTS:
            raw = path.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                errors.append(f"UTF-8 BOM detected in {path.relative_to(ROOT)}")

    return errors


def serve(port: int) -> None:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(OUT_DIR)
    )

    class ReusableTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with ReusableTCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Serving _site at http://127.0.0.1:{port}/ (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped server.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build danieltroberts.com static site.")
    parser.add_argument("--check", action="store_true", help="Run validation checks after building.")
    parser.add_argument("--serve", action="store_true", help="Build, validate, and serve locally.")
    parser.add_argument("--port", type=int, default=8000, help="Local preview port (default: 8000).")
    args = parser.parse_args()

    build()
    print(f"Built static site in {OUT_DIR}")

    if args.check or args.serve:
        errors = check()
        if errors:
            for err in errors:
                print(f"ERROR: {err}", file=sys.stderr)
            return 1
        print("Validation passed: all schemas, assets, internal links, and BOM checks clean.")

    if args.serve:
        serve(args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
