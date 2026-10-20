"""Static localization: authored overrides, source-versioned machine cache, English fallback."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from html import escape
from pathlib import Path
import json
import re
from urllib.parse import urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
import markdown
import yaml

SITE = 'https://jjli.info'
TOKEN = re.compile(r'⟦\d+⟧')
BLOCKS = {'p','h1','h2','h3','h4','h5','h6','li','ul','ol','table','tr','th','td','div','section','article','header','footer','nav','figure','figcaption','form','details','pre','blockquote'}
UNITS = {'p','h1','h2','h3','h4','h5','h6','li','th','td','figcaption','label','option','button','summary','a','span','strong','em'}
PROTECTED_TAGS = {'script','style','pre','code','math','svg'}
VOID = {'br','img','hr','input','wbr'}

def digest(text):
    return sha256(text.encode()).hexdigest()

def read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default

def dump_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)+'\n')

def load_mapping(path):
    value = yaml.safe_load(path.read_text()) if path.exists() else {}
    if value is None: return {}
    if not isinstance(value, dict): raise ValueError(f'{path}: expected a mapping')
    return value

def freeze(node, glossary):
    """Keep markup, code, names, glossary terms and numbers outside the translator."""
    slots, originals = {}, {}
    def protect(source, output=None):
        token=f'⟦{len(slots)}⟧'; slots[token]=source if output is None else output; originals[token]=source
        return token
    terms = sorted(glossary, key=len, reverse=True)
    term_pattern = '|'.join(re.escape(t) for t in terms)
    pattern = re.compile((rf'(?<![\w])(?:{term_pattern})(?![\w])|' if terms else '') + r'\{(?:visible|total)\}|\b\d[\d,]*(?:\.\d+)?\b')
    def text(value):
        return pattern.sub(lambda m: protect(escape(m[0]), escape(glossary.get(m[0],m[0]))), value)
    def walk(child):
        if isinstance(child, Comment): return protect(str(child.output_ready()))
        if isinstance(child, NavigableString): return text(str(child))
        if child.name in PROTECTED_TAGS or child.get('translate')=='no': return protect(str(child))
        opening='<'+child.name+''.join(' '+k+'="'+escape(' '.join(v) if isinstance(v,list) else str(v),quote=True)+'"' for k,v in child.attrs.items())+'>'
        result=protect(opening)
        if child.name not in VOID:
            result+=''.join(walk(c) for c in child.children)+protect('</'+child.name+'>')
        return result
    source=''.join(walk(c) for c in node.children) if isinstance(node,Tag) else text(str(node))
    return source, slots, originals

def valid_translation(source, target):
    return isinstance(target,str) and bool(target.strip()) and Counter(TOKEN.findall(source))==Counter(TOKEN.findall(target))

def thaw(text, slots):
    return TOKEN.sub(lambda m: slots[m[0]], escape(text))

class Catalog:
    def __init__(self, root, locale):
        self.root,self.locale=root,locale
        self.manual=load_mapping(root/f'translations/{locale}.yaml')
        self.cache=read_json(root/f'translations/automatic/{locale}.json',{})
        self.glossary=load_mapping(root/f'translations/glossary/{locale}.yaml')
        self.sources={}
        self.report={'missing':[], 'stale_manual':[], 'untracked_manual':[], 'invalid_cache':[], 'unused_manual':[]}
        self.used=set(); self.machine=0; self.missing=0

    def resolve(self, key, node, context):
        source,slots,originals=freeze(node,self.glossary)
        if not re.search(r'[A-Za-z\u4e00-\u9fff]',TOKEN.sub('',source)):
            return str(node.decode_contents()) if isinstance(node,Tag) else escape(str(node)), 'original'
        fingerprint=digest(json.dumps([source,originals,self.glossary],sort_keys=True,ensure_ascii=False))
        record={'source':source,'source_hash':fingerprint,'protected':originals,'replacements':slots,'context':context}
        if key in self.sources and self.sources[key]['source_hash']!=fingerprint:
            raise ValueError(f'Duplicate translation key with different text: {key}')
        self.sources[key]=record;self.used.add(key)
        manual=self.manual.get(key)
        if manual is not None:
            if isinstance(manual,str):
                result=escape(manual);baseline=None
            elif isinstance(manual,dict):
                result=manual.get('html') if 'html' in manual else escape(manual.get('text',''))
                baseline=manual.get('source_hash')
            else:raise ValueError(f'{self.locale}: invalid authored entry {key}')
            if not isinstance(result,str) or not result.strip():raise ValueError(f'{self.locale}: empty authored entry {key}')
            if baseline is None:self.report['untracked_manual'].append(key)
            elif baseline!=fingerprint:self.report['stale_manual'].append(key)
            # Authored blocks are literal content, so source edits never silently change their numbers or links.
            status='manual'
        else:
            cached=self.cache.get(key,{})
            if cached.get('source_hash')==fingerprint and valid_translation(source,cached.get('text')):
                result=thaw(cached['text'],slots);status='machine';self.machine+=1
            else:
                if cached.get('source_hash')==fingerprint:self.report['invalid_cache'].append(key)
                self.report['missing'].append(key);self.missing+=1
                return str(node.decode_contents()) if isinstance(node,Tag) else escape(str(node)), 'fallback'
        if isinstance(node,Tag) and status!='manual':
            original_tags=[(t.name,t.attrs) for t in node.find_all(True)]
            new_tags=[(t.name,t.attrs) for t in BeautifulSoup(result,'html.parser').find_all(True)]
            if original_tags!=new_tags:raise ValueError(f'{key}: translation changed inline markup or its order')
        return result,status

    def finish(self):
        self.report['unused_manual']=sorted(set(self.manual)-self.used)
        for key in self.report:self.report[key]=sorted(set(self.report[key]))
        dump_json(self.root/f'translations/source/{self.locale}.json',self.sources)
        dump_json(self.root/f'translations/reports/{self.locale}.json',self.report)


def annotate_note(html, slug):
    soup=BeautifulSoup(html,'html.parser')
    seen=set()
    for comment in list(soup.find_all(string=lambda s:isinstance(s,Comment))):
        match=re.fullmatch(r'\s*i18n:\s*([a-zA-Z0-9_.-]+)\s*',str(comment))
        if match:
            if match[1] in seen:raise ValueError(f'{slug}: duplicate note translation ID {match[1]}')
            seen.add(match[1])
            following=comment.find_next_sibling()
            if following:following['data-i18n']=f'note.{slug}.{match[1]}'
    return str(soup)


def translate_body(soup, catalog, context):
    # Preserve formal citations, author names, code, and download records verbatim.
    for tag in soup.select('.publication h3, .publication .authors, .publication .venue, .compact-meta span, .contact-handle, .bibtex pre, .versions li'):
        tag['translate']='no';tag['lang']='en'
    def key_for(tag, suffix=''):
        anchor=tag if tag.get('data-i18n') else tag.find_parent(attrs={'data-i18n':True})
        if anchor:
            key=anchor['data-i18n']
            if tag is not anchor:
                # Positions are only within a stable block (e.g. table cells), never across paragraphs.
                chain=[];cur=tag
                while cur is not anchor:
                    siblings=[c for c in cur.parent.children if isinstance(c,Tag)]
                    chain.append(f'{cur.name}{siblings.index(cur)}');cur=cur.parent
                key+='.'+'.'.join(reversed(chain))
        elif tag.get('id'):key=context+'.'+tag['id']
        else:key='shared.'+digest(tag.decode_contents())[:16]
        return key+suffix
    def walk(tag):
        if tag.name in PROTECTED_TAGS or tag.get('translate')=='no':return
        for attr in ['alt','aria-label','placeholder','title']:
            if tag.get(attr):
                original=tag[attr]
                if original.startswith('Read PDF: '):
                    tag[attr]='阅读 PDF：'+original.removeprefix('Read PDF: ') if catalog.locale=='zh-Hans' else original
                    continue
                key='attribute.'+digest(original)[:16]
                value,status=catalog.resolve(key,original,context)
                from html import unescape
                tag[attr]=unescape(value)
        if tag.name in UNITS and not tag.find(list(BLOCKS)) and tag.get_text(strip=True):
            result,status=catalog.resolve(key_for(tag),tag,context)
            tag.clear()
            fragment=BeautifulSoup(result,'html.parser')
            for child in list(fragment.contents):tag.append(child)
            if status=='fallback':tag['lang']='en';tag['data-translation']='fallback'
            return
        for child in list(tag.children):
            if isinstance(child,Tag):walk(child)
            elif isinstance(child,NavigableString) and not isinstance(child,Comment) and re.search('[A-Za-z]',str(child)):
                key='fragment.'+digest(str(child).strip())[:16]
                value,status=catalog.resolve(key,str(child).strip(),context)
                span=soup.new_tag('span')
                if status=='fallback':span['lang']='en';span['data-translation']='fallback'
                span.append(BeautifulSoup(value,'html.parser'))
                child.replace_with(span)
    walk(soup.body)


def route(filename):
    return '/' if filename=='index.html' else '/'+filename.removesuffix('index.html') if filename.endswith('/index.html') else '/'+filename


def build_languages(root, page_names, note_count):
    config=read_json(root/'translations/languages.json',[])
    assert config and config[0]['code']=='en'
    for item in config:
        if not re.fullmatch(r'[a-zA-Z0-9-]+',item['code']) or (item['prefix'] and not re.fullmatch(r'[a-zA-Z0-9-]+',item['prefix'])):
            raise ValueError('Unsafe locale code or path prefix')
    names=[n+'.html' for n in page_names]+['blog.html']+[str(p.relative_to(root)) for p in sorted((root/'blog').glob('*/index.html')) if '<!-- Generated from content/posts' in p.read_text()]
    sources={name:BeautifulSoup((root/name).read_text(),'html.parser') for name in names}
    paths={route(n):n for n in names}
    paths.update({'/'+n:n for n in names})
    results=[]
    for language in config:
        code,prefix=language['code'],language['prefix']
        catalog=Catalog(root,code) if code!='en' else None
        svg_map={}
        if catalog:
            for svg in sorted((root/'assets/posts').glob('**/*.svg')):
                tree=ET.parse(svg);stem='diagram.'+svg.stem
                for i,node in enumerate(tree.getroot().iter()):
                    if node.tag.split('}')[-1] in ['text','title'] and node.text:
                        value,_=catalog.resolve(f'{stem}.{i}',node.text,str(svg.relative_to(root)))
                        from html import unescape
                        node.text=unescape(value)
                destination=root/prefix/svg.relative_to(root);destination.parent.mkdir(parents=True,exist_ok=True)
                tree.write(destination,encoding='utf-8',xml_declaration=True)
                svg_map['/'+str(svg.relative_to(root))]='/'+str(destination.relative_to(root))
        expected=set()
        for name,original in sources.items():
            soup=deepcopy(original);is_error=name=='404.html';outname=(prefix+'/' if prefix else '')+name
            expected.add(root/outname)
            page_route=('/'+prefix if prefix else '')+route(name)
            if catalog:
                before_machine,before_missing=catalog.machine,catalog.missing
                manual_post=None
                if name=='blog.html':
                    for preview in soup.select('.note-preview'):
                        link=preview.select_one('h2 a')
                        slug=urlsplit(link['href']).path.strip('/').split('/')[1]
                        manual_path=root/f'content/translations/{code}/posts/{slug}.md'
                        if manual_path.exists():
                            parts=manual_path.read_text().split('---',2)
                            if len(parts)!=3 or parts[0].strip():raise ValueError(f'{manual_path}: YAML front matter required')
                            metadata=yaml.safe_load(parts[1])
                            if not isinstance(metadata,dict) or not all(isinstance(metadata.get(k),str) and metadata[k].strip() for k in ['title','summary','source_hash']):raise ValueError(f'{manual_path}: title, summary and source_hash required')
                            link.string=metadata['title'];link.parent['translate']='no'
                            preview.select_one('p').string=metadata['summary'];preview.select_one('p')['translate']='no'
                if name.startswith('blog/'):
                    slug=name.split('/')[1];manual_path=root/f'content/translations/{code}/posts/{slug}.md'
                    if manual_path.exists():
                        parts=manual_path.read_text().split('---',2)
                        if len(parts)!=3 or parts[0].strip():raise ValueError(f'{manual_path}: YAML front matter required')
                        metadata=yaml.safe_load(parts[1]);manual_post=metadata
                        if not isinstance(metadata,dict) or not all(isinstance(metadata.get(k),str) and metadata[k].strip() for k in ['title','summary','source_hash']):raise ValueError(f'{manual_path}: title, summary and source_hash required')
                        from build_notes import load_posts
                        source_post=next(p for p in load_posts(root) if p['slug']==slug)
                        if metadata['source_hash']!=source_post['source_hash']:catalog.report['stale_manual'].append('post.'+slug)
                        content=markdown.markdown(parts[2],extensions=['extra','sane_lists'])
                        if BeautifulSoup(content,'html.parser').find('h1'):raise ValueError(f'{manual_path}: use level-two headings')
                        section=soup.select_one('.note-content');section.clear();section.append(BeautifulSoup(content,'html.parser'));section['translate']='no'
                        for selector,key in [('.note-article h1','title'),('.note-deck','summary')]:
                            node=soup.select_one(selector);node.string=metadata[key];node['translate']='no'
                        soup.title.string=metadata['title']+' · Jiajun Li'
                        for tag in soup.select('meta[name="description"],meta[property="og:description"]'):tag['content']=metadata['summary']
                        soup.select_one('meta[property="og:title"]')['content']=soup.title.string
                translate_body(soup,catalog,name)
                if not manual_post:
                    from html import unescape
                    value,_=catalog.resolve(name+'.title',original.title.get_text(),name);soup.title.string=unescape(value)
                    for meta in soup.select('meta[name="description"],meta[property="og:description"]'):
                        value,_=catalog.resolve(name+'.description',meta['content'],name);meta['content']=unescape(value)
                    soup.select_one('meta[property="og:title"]')['content']=soup.title.string
                if catalog.machine>before_machine or catalog.missing>before_missing:
                    notice=soup.new_tag('aside',attrs={'class':'translation-notice'})
                    notice.string=language['notice']+(' '+language['fallback_notice'] if catalog.missing>before_missing else '')+' '
                    a=soup.new_tag('a',href=SITE+route(name),attrs={'data-original-link':'true'});a.string=language['original_label'];notice.append(a)
                    soup.main.insert(0,notice)
            soup.html['lang']=code
            canonical=soup.find('link',rel='canonical')
            if canonical:canonical['href']=SITE+page_route
            og=soup.find('meta',property='og:url')
            if og:og['content']=SITE+page_route
            if not is_error:
                for target in config:
                    target_route=('/'+target['prefix'] if target['prefix'] else '')+route(name)
                    soup.head.append(soup.new_tag('link',rel='alternate',hreflang=target['code'],href=SITE+target_route))
                soup.head.append(soup.new_tag('link',rel='alternate',hreflang='x-default',href=SITE+route(name)))
            switch=soup.new_tag('div',attrs={'class':'language-switch','aria-label':'Language','translate':'no'})
            for target in config:
                target_route=('/'+target['prefix'] if target['prefix'] else '')+route(name)
                a=soup.new_tag('a',href=target_route,hreflang=target['code'],lang=target['code']);a.string=target['label']
                if target['code']==code:a['aria-current']='true'
                switch.append(a)
            soup.select_one('.site-header').append(switch)
            # Resolve links against the English source before adding locale prefixes.
            for tag in soup.find_all(True):
                for attr in ['href','src']:
                    value=tag.get(attr)
                    if not value or value.startswith('#'):continue
                    parsed=urlsplit(urljoin(SITE+'/'+name,value))
                    if parsed.netloc!=urlsplit(SITE).netloc or parsed.scheme not in ['http','https']:continue
                    if tag.name=='link' and (tag.get('hreflang') or 'canonical' in tag.get('rel',[])):continue
                    if tag.get('hreflang') or tag.get('data-original-link'):continue
                    path=parsed.path
                    if prefix and path in paths:path='/'+prefix+route(paths[path])
                    elif prefix and path=='/feed.xml':path='/'+prefix+'/feed.xml'
                    elif path in svg_map:path=svg_map[path]
                    tag[attr]=urlunsplit(('', '',path,parsed.query,parsed.fragment))
            counter=soup.select_one('#result-count')
            if counter:counter['data-count-template']=language['count_template']
            destination=root/outname;destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_text(str(soup).rstrip()+'\n')
            if prefix and not is_error:results.append(SITE+page_route)
        if catalog:
            # Clean only generated translations when an original note is removed/drafted.
            for old in (root/prefix/'blog').glob('*/index.html'):
                if old not in expected and '<!-- Generated from content/posts' in old.read_text():old.unlink()
            feed=ET.parse(root/'feed.xml');channel=feed.getroot().find('channel')
            channel.find('language').text=code;channel.find('link').text=SITE+'/'+prefix+'/blog.html';channel.find('title').text=language['feed_title'];channel.find('description').text=language['feed_description']
            for item in channel.findall('item'):
                english=urlsplit(item.find('link').text).path
                page=BeautifulSoup((root/prefix/english.lstrip('/')/'index.html').read_text(),'html.parser')
                item.find('title').text=page.select_one('.note-article h1').get_text()
                item.find('description').text=page.select_one('.note-deck').get_text()
                for key in ['link','guid']:item.find(key).text=SITE+'/'+prefix+english
                for node,value in zip(item.findall('category'),page.select('.note-meta span')):node.text=value.get_text()
            feed.write(root/prefix/'feed.xml',encoding='utf-8',xml_declaration=True)
            catalog.finish()
            print(f'{code}: {len(catalog.sources)} translation units; {len(catalog.report["missing"])} missing, {len(catalog.report["stale_manual"])} authored translations need review.')
    return results
