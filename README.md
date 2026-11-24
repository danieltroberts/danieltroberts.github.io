# Daniel T. Roberts — Academic Website

Source repository for [danieltroberts.com](https://www.danieltroberts.com) (`danieltroberts.github.io`), built with a zero-dependency Python 3.13 static site generator (`build.py`) and deployed to GitHub Pages via GitHub Actions.

## Local Build & Preview

Requires Python 3.13+ (standard library only; no `pip` or Node packages).

```powershell
python build.py --check   # Build _site/ and validate schemas, links, assets, and UTF-8 encoding
python build.py --serve   # Build, validate, and serve locally at http://127.0.0.1:8000
```

## Updating Content

Edit the structured content files in `content/`:
- `content/site.toml` — affiliation, metadata, navigation, profile links
- `content/about.md` — home page biography
- `content/research.toml` — working papers, publications, works in progress, other writing
- `content/teaching.toml` — courses and syllabi

`Daniel_Roberts_CV.pdf` at the repository root is built and pushed automatically from the private `C:\Work\Career` repo via `Career\scripts\publish-cv.ps1`.

## Deployment & Custom Domain Cutover (`www.danieltroberts.com`)

1. Merge `redesign` into `main` and push to GitHub.
2. In GitHub repo **Settings → Pages**, set **Source** to **GitHub Actions**.
3. Verify the staging build at `https://danieltroberts.github.io` (including `/Daniel_Roberts_CV.pdf`, `/working_papers/...`, and `/market_supplemental/...`).
4. Add a `CNAME` file containing `www.danieltroberts.com` at the repo root (automatically copied into `_site/` by `build.py`).
5. At your DNS registrar:
   - Point `www` `CNAME` to `danieltroberts.github.io.`
   - Point apex `@` `A` records to GitHub Pages (`185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`)
6. Enable **Enforce HTTPS** in GitHub Pages settings once DNS propagates.
