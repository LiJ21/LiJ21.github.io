#!/usr/bin/env python3
"""Generate build-free HTML and BibTeX from the reviewed publication dataset."""
from pathlib import Path
from html import escape
import json
import re
import os
import sys
import posixpath
import xml.etree.ElementTree as ET
from importlib.util import find_spec

ROOT = Path(__file__).resolve().parent.parent
if any(find_spec(module) is None for module in ('markdown', 'yaml', 'bs4')):
    local_python = ROOT / '.venv/bin/python'
    if local_python.exists() and Path(sys.prefix) != ROOT / '.venv':
        os.execv(str(local_python), [str(local_python), str(Path(__file__).resolve()), *sys.argv[1:]])
    raise SystemExit('Missing build dependencies. Install requirements.txt in .venv; see README.md → Notes.')
from build_notes import build_notes, SITE
PUBLICATIONS = json.loads((ROOT / 'data/publications.json').read_text())
SCHOLAR = 'https://scholar.google.com/citations?user=tP-VfEAAAAAJ&hl=en'
LINKEDIN = 'https://www.linkedin.com/in/jiajunli/'
GITHUB = 'https://github.com/LiJ21'
NAV = [('index.html', 'Overview'), ('about.html', 'Background'), ('publications.html', 'Publications'), ('projects.html', 'Projects'), ('blog.html', 'Notes'), ('contact.html', 'Contact')]
TYPES = {'article': 'Journal / proceedings', 'preprint': 'Preprint', 'thesis': 'Thesis', 'abstract': 'Meeting abstract'}

def link(url, text, cls='', extra=''):
    return f'<a href="{escape(url, quote=True)}"'+(f' class="{cls}"' if cls else '')+f' {extra}>{text}</a>'

def bibtex(p):
    kind = {'article': 'article', 'preprint': 'misc', 'thesis': 'phdthesis', 'abstract': 'misc'}[p['kind']]
    fields = {'title': '{'+p['title']+'}', 'author': ' and '.join(p['authors']), 'year': str(p['year'])}
    if p['kind'] == 'article':
        fields.update(journal=p['journal'], volume=p['volume'], number=p['issue'], pages=p['pages'])
    elif p['kind'] == 'thesis':
        fields['school'] = 'University at Buffalo, State University of New York'
    elif p['kind'] == 'abstract':
        fields['howpublished'] = f"APS March Meeting, {p['pages']}"
        fields['note'] = 'Meeting abstract'
    if p['doi']: fields['doi'] = p['doi']
    if p['arxiv']: fields.update(eprint=p['arxiv'], archivePrefix='arXiv')
    fields['url'] = p['url']
    return '@'+kind+'{Li'+str(p['year'])+'_'+p['id'].replace('-', '_')+',\n'+',\n'.join('  '+k+' = {'+v+'}' for k,v in fields.items() if v)+'\n}'

def citation(p):
    if p['kind'] == 'preprint': return f"arXiv:{p['arxiv']} · {p['year']}"
    if p['kind'] == 'thesis': return f"PhD thesis · University at Buffalo · {p['year']}"
    if p['kind'] == 'abstract': return f"APS March Meeting · {p['pages']} · {p['year']}"
    return f"{p['journal']} {p['volume']}, {p['pages']} ({p['year']})"

def publication(p, compact=False):
    if compact:
        pdf = link(p['pdf'], 'PDF', extra=f'aria-label="{escape("Read PDF: "+p["title"],quote=True)}"') if p['pdf'] else ''
        return f'''<article class="publication publication-compact" id="{p['id']}">
          <h3>{link(p['url'], escape(p['title']))}</h3>
          <div class="compact-meta"><span>{escape(citation(p))}</span>{pdf}</div>
        </article>'''
    authors = ', '.join('<strong>'+escape(a)+'</strong>' if a in ['Jiajun Li','J. Li','J Li'] else escape(a) for a in p['authors'])
    buttons = [link(p['url'], 'Journal ↗' if p['kind']=='article' else 'Abstract ↗' if p['kind']=='abstract' else 'arXiv ↗')]
    if p['pdf']:
        buttons.insert(0, link(p['pdf'], 'PDF · Journal ↓' if p['pdf_source']=='publisher' else 'PDF · arXiv ↓', 'pdf-link', f'aria-label="{escape("Read PDF: "+p["title"],quote=True)}"'))
    if p['arxiv'] and p['kind']=='article': buttons.append(link('https://arxiv.org/abs/'+p['arxiv'], 'arXiv ↗'))
    if p['id'] == 'paper-33': buttons.append(link('https://github.com/nessi-cntr/nessi', 'Code ↗'))
    if p['id'] in ['paper-03','paper-24']: buttons.append(link(GITHUB+'/QuDrip', 'Code ↗'))
    search = ' '.join([p['title'],*p['authors'],p['journal'],str(p['year']),p['doi'],p['arxiv'],*[a['title'] for a in p['aliases']]])
    extras = ''
    if not compact:
        extras = f'<details class="bibtex"><summary>BibTeX</summary><pre>{escape(bibtex(p))}</pre></details>'
        if p['aliases']:
            extras += '<details class="versions"><summary>Earlier titles / versions</summary><ul>'+''.join(f'<li>{escape(a["title"])} ({a["year"]})</li>' for a in p['aliases'])+'</ul></details>'
    return f'''<article class="publication" id="{p['id']}" data-year="{p['year']}" data-kind="{p['kind']}" data-search="{escape(search,quote=True)}">
      <div class="pub-year">{p['year']}<span>{'PREPRINT' if p['kind']=='preprint' else 'THESIS' if p['kind']=='thesis' else 'ABSTRACT' if p['kind']=='abstract' else 'PAPER'}</span></div>
      <div class="pub-body"><h3>{link(p['url'],escape(p['title']))}</h3><p class="authors">{authors}</p><p class="venue">{escape(citation(p))}</p><div class="paper-links">{''.join(buttons)}</div>{extras}</div>
    </article>'''

def section_heading(n, title, trailing=''):
    return f'<div class="section-heading"><div><span class="eyebrow">{n}</span><h2>{title}</h2></div>{trailing}</div>'

SITEMAP_URLS = []

def shell(filename, title, description, body, script=False):
    canonical_tags = ''
    if filename != '404.html':
        route = '/' if filename == 'index.html' else '/' + filename.removesuffix('index.html') if filename.endswith('/index.html') else '/' + filename
        canonical_url = SITE + route
        SITEMAP_URLS.append(canonical_url)
        canonical_tags = f'  <link rel="canonical" href="{escape(canonical_url,quote=True)}">\n  <meta property="og:url" content="{escape(canonical_url,quote=True)}">\n'
    page_title = f'Jiajun Li · {title}' if filename == 'index.html' else f'{title} · Jiajun Li'
    nav=''.join(link('/'+f,t,extra='aria-current="page"' if f==filename or (f=='blog.html' and filename.startswith('blog/')) else '') for f,t in NAV)
    footer=f'<footer><p>© 2026 Jiajun Li</p><p>AI · Computation · Trading</p><div>{link(SCHOLAR,"Scholar ↗")}{link(GITHUB,"GitHub ↗")}{link(LINKEDIN,"LinkedIn ↗")}</div></footer>'
    html=f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{escape(description,quote=True)}">
  <meta name="theme-color" content="#111111">
  <meta property="og:title" content="{escape(page_title,quote=True)}">
  <meta property="og:description" content="{escape(description,quote=True)}">
  <meta property="og:type" content="website">
  <title>{escape(page_title)}</title>
{canonical_tags}  <link rel="alternate" type="application/rss+xml" title="Jiajun Li — Notes" href="/feed.xml">
  <link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/assets/style.css">
  {'<script src="/assets/publications.js" defer></script>' if script else ''}
</head>
<body{' class="home-page"' if filename == 'index.html' else ''}>
  <a class="skip-link" href="#main">Skip to content</a>
  <div class="site-wrap">
    <header class="site-header"><nav aria-label="Main navigation">{nav}</nav></header>
    <main id="main">{body}</main>
    {footer}
  </div>
</body>
</html>
'''
    if filename != '404.html':
        # Relative paths also allow direct file previews and subdirectory hosting.
        def relative_url(match):
            target = match.group(2)
            if target.endswith('/'):
                target += 'index.html'
            target = posixpath.relpath(target, posixpath.dirname(filename) or '.')
            return match.group(1) + target + '"'
        html = re.sub(r'(\b(?:href|src)=")/(?!/)([^"]*)"', relative_url, html)
    (ROOT/filename).parent.mkdir(parents=True, exist_ok=True)
    (ROOT/filename).write_text("\n".join(line.rstrip() for line in html.splitlines()) + "\n")

def hero(label, title, intro):
    return f'<section class="page-hero"><p class="eyebrow">{label}</p><h1>{title}</h1><p class="intro">{intro}</p></section>'

def project_card(p,compact=False):
    repo_url = p['href'] if p['href'].startswith('https://') else GITHUB+'/'+p['href']
    details='' if compact or not p['detail'] else f'<p class="project-detail" data-i18n="project.{p["name"]}.detail">{p["detail"]}</p>'
    return f'<article class="project-card" data-i18n-scope="project-{p["name"]}"><p class="eyebrow" data-i18n="project.{p["name"]}.category">{p["category"]}</p><h3>{link(repo_url,p["name"]+" ↗")}</h3><p class="project-subtitle" data-i18n="project.{p["name"]}.subtitle">{p["subtitle"]}</p><p data-i18n="project.{p["name"]}.description">{p["text"]}</p>{details}<ul class="tags" aria-label="Technologies">'+''.join(f'<li>{t}</li>' for t in p['tags'])+f'</ul><div class="project-links">{link(repo_url,"Repository ↗")}{p["extra"]}</div></article>'

# Page prose lives in editable templates; generated lists share the reviewed data.
import yaml
from i18n import build_languages
PROJECTS = yaml.safe_load((ROOT/'content/projects.yaml').read_text())
PAGES = yaml.safe_load((ROOT/'content/pages.yaml').read_text())
selected = sorted((p for p in PUBLICATIONS if p.get('selected')), key=lambda p: (-p['year'], -p.get('citation_count', 0), p['title']))
counts = {k: sum(p['kind'] == k for p in PUBLICATIONS) for k in TYPES}
slots = {
    'selected_publications': ''.join(publication(p, True) for p in selected),
    'projects': ''.join(project_card(p) for p in PROJECTS),
    'publications': ''.join(publication(p) for p in PUBLICATIONS),
    'publication_types': '<option value="all">All types</option>' + ''.join(f'<option value="{k}">{v}</option>' for k, v in TYPES.items()),
    'publication_years': '<option value="all">All years</option>' + ''.join(f'<option value="{y}">{y}</option>' for y in sorted({p['year'] for p in PUBLICATIONS}, reverse=True)),
    'count_all': str(len(PUBLICATIONS)),
    **{'count_'+k: str(v) for k,v in counts.items()},
}
for name, metadata in PAGES.items():
    body = (ROOT/f'content/pages/{name}.html').read_text()
    body = re.sub(r'{{\s*(\w+)\s*}}', lambda m: slots[m[1]], body)
    shell(name+'.html', metadata['title'], metadata['description'], body, name=='publications')
(ROOT/'assets/publications.bib').write_text('% Jiajun Li — publication record, checked 2026-10-19\n% UTF-8; compatible with biblatex/biber.\n\n'+'\n\n'.join(bibtex(p) for p in PUBLICATIONS)+'\n')
note_count = build_notes(ROOT, shell, hero)
translated_urls = build_languages(ROOT, list(PAGES), note_count)
SITEMAP_URLS.extend(translated_urls)
namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
ET.register_namespace('', namespace)
sitemap = ET.Element(f'{{{namespace}}}urlset')
for url in sorted(set(SITEMAP_URLS)):
    entry = ET.SubElement(sitemap, f'{{{namespace}}}url')
    ET.SubElement(entry, f'{{{namespace}}}loc').text = url
ET.indent(sitemap)
ET.ElementTree(sitemap).write(ROOT/'sitemap.xml', encoding='utf-8', xml_declaration=True)
(ROOT/'robots.txt').write_text(f'User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n')
print(f'Generated English/Chinese pages, {note_count} notes, feeds, and {len(PUBLICATIONS)} BibTeX entries.')
