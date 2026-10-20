"""Render repository-authored Markdown notes and their RSS feed."""
from datetime import date, datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import markdown
import yaml
from hashlib import sha256
from i18n import annotate_note

SITE = 'https://jjli.info'
MARKER = '<!-- Generated from content/posts by build_notes.py -->'


def load_posts(root):
    posts, slugs = [], set()
    for path in sorted((root / 'content/posts').glob('*.md')):
        parts = path.read_text().split('---', 2)
        if len(parts) != 3 or parts[0].strip():
            raise ValueError(f'{path}: YAML front matter is required')
        meta = yaml.safe_load(parts[1])
        if not isinstance(meta, dict):
            raise ValueError(f'{path}: metadata must be a mapping')
        for key in ('title', 'slug', 'summary'):
            if not isinstance(meta.get(key), str) or not meta[key].strip():
                raise ValueError(f'{path}: {key} must be a nonempty string')
        slug = meta['slug']
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug) or slug in slugs:
            raise ValueError(f'{path}: invalid or duplicate slug {slug}')
        slugs.add(slug)
        if type(meta.get('draft', False)) is not bool:
            raise ValueError(f'{path}: draft must be true or false')
        published = date.fromisoformat(str(meta.get('date')))
        tags = meta.get('tags', [])
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
            raise ValueError(f'{path}: tags must be a list of strings')
        if meta.get('draft', False):
            continue
        html = annotate_note(markdown.markdown(parts[2], extensions=['extra', 'sane_lists'], output_format='html'), slug)
        # The page template owns its one top-level heading.
        if re.search(r'<h1(?:\s|>)', html):
            raise ValueError(f'{path}: use level-two headings in the article body')
        posts.append(dict(meta, source_hash=sha256(path.read_bytes()).hexdigest(), date=published, tags=tags, html=html, url=f'/blog/{slug}/'))
    return sorted(posts, key=lambda p: (p['date'], p['slug']), reverse=True)


def build_notes(root, shell, hero):
    posts = load_posts(root)
    expected = {root / 'blog' / p['slug'] / 'index.html' for p in posts}
    # Remove only our generated output when a post is deleted or becomes a draft.
    for path in (root / 'blog').glob('*/index.html'):
        if path not in expected and MARKER in path.read_text():
            path.unlink()
    cards = []
    for p in posts:
        title, summary = escape(p['title']), escape(p['summary'])
        metadata = f'<time datetime="{p["date"]}">{p["date"].strftime("%d %B %Y")}</time>'
        metadata += ''.join(f'<span>{escape(t)}</span>' for t in p['tags'])
        cards.append(f'<article class="note-preview"><div class="note-meta">{metadata}</div><h2><a href="{p["url"]}">{title}</a></h2><p>{summary}</p></article>')
        body = f'''{MARKER}<article class="note-article">
<p><a href="/blog.html">← All notes</a></p>
<header><div class="note-meta">{metadata}</div><h1>{title}</h1><p class="note-deck">{summary}</p></header>
<div class="note-content">{p['html']}</div>
</article>'''
        shell(f'blog/{p["slug"]}/index.html', p['title'], p['summary'], body)
    body = hero('WRITING / NOTES', 'Notes.', 'Experiments and observations on machine learning, systems, markets, and physics.')
    body += '<div class="notes-list"><p><a href="/feed.xml">Subscribe via RSS ↗</a></p>' + (''.join(cards) or '<p>No notes published yet.</p>') + '</div>'
    shell('blog.html', 'Notes', 'Technical notes by Jiajun Li on machine learning, systems, markets, and physics.', body)
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for tag, value in [('title', 'Jiajun Li — Notes'), ('link', SITE+'/blog.html'), ('description', 'Notes on machine learning, systems, markets, and physics.'), ('language', 'en')]:
        ET.SubElement(channel, tag).text = value
    for p in posts:
        item = ET.SubElement(channel, 'item')
        for tag, value in [('title', p['title']), ('link', SITE+p['url']), ('guid', SITE+p['url']), ('description', p['summary']), ('pubDate', format_datetime(datetime.combine(p['date'], datetime.min.time(), tzinfo=timezone.utc)))]:
            ET.SubElement(item, tag).text = value
        for tag in p['tags']:
            ET.SubElement(item, 'category').text = tag
    ET.indent(rss)
    ET.ElementTree(rss).write(root/'feed.xml', encoding='utf-8', xml_declaration=True)
    return len(posts)
