#!/usr/bin/env python3
"""Generate build-free HTML and BibTeX from the reviewed publication dataset."""
from pathlib import Path
from html import escape
import json
import re

ROOT = Path(__file__).resolve().parent.parent
PUBLICATIONS = json.loads((ROOT / 'data/publications.json').read_text())
SCHOLAR = 'https://scholar.google.com/citations?user=tP-VfEAAAAAJ&hl=en'
LINKEDIN = 'https://www.linkedin.com/in/jiajunli/'
GITHUB = 'https://github.com/LiJ21'
NAV = [('index.html', 'Overview'), ('about.html', 'Background'), ('publications.html', 'Publications'), ('projects.html', 'Projects'), ('contact.html', 'Contact')]
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

def shell(filename, title, description, body, script=False):
    nav=''.join(link(f,t,extra='aria-current="page"' if f==filename else '') for f,t in NAV)
    footer=f'<footer><p>© 2026 Jiajun Li</p><p>AI · Computation · Trading</p><div>{link(SCHOLAR,"Scholar ↗")}{link(GITHUB,"GitHub ↗")}{link(LINKEDIN,"LinkedIn ↗")}</div></footer>'
    html=f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{escape(description,quote=True)}">
  <meta name="theme-color" content="#003b71">
  <meta property="og:title" content="{escape(title,quote=True)} · Jiajun Li">
  <meta property="og:description" content="{escape(description,quote=True)}">
  <meta property="og:type" content="website">
  <title>{escape(title)} · Jiajun Li</title>
  <link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="assets/style.css">
  {'<script src="assets/publications.js" defer></script>' if script else ''}
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
    (ROOT/filename).write_text("\n".join(line.rstrip() for line in html.splitlines()) + "\n")

def hero(label, title, intro):
    return f'<section class="page-hero"><p class="eyebrow">{label}</p><h1>{title}</h1><p class="intro">{intro}</p></section>'

PROJECTS=[
 dict(name='QLeaf',subtitle='Low-latency tree inference',category='01 / SYSTEMS & MACHINE LEARNING',tags=['C++','CUDA','CPU / GPU'],text='Single-row inference for large ensembles of shallow decision trees. QLeaf investigates how memory layout, CPU affinity, persistent GPU kernels, and host–device coordination affect end-to-end latency.',detail='A focused benchmark and implementation toolkit for latency-sensitive inference. The current interface returns a scalar raw margin; benchmark results depend on the model, hardware, and execution policy.',href='QLeaf',extra=link(GITHUB+'/QLeaf/blob/main/BENCHMARK.md','Benchmark methodology ↗')),
 dict(name='QuDrip',subtitle='Exact quantum many-body simulation',category='02 / COMPUTATIONAL PHYSICS',tags=['C++','Eigen','Krylov methods'],text='A toolbox for constructing constrained Hilbert spaces, quantum operators, and Hamiltonians. Sparse-matrix and Krylov methods support ground-state calculations, real-time evolution, and Lindblad dynamics.',detail='Designed for flexible small-to-medium quantum systems, including fermionic and bosonic degrees of freedom. Used in research on quantum-light control and photodoped superconductivity.',href='QuDrip',extra=link('publications.html#paper-03','Related publication →')),
 dict(name='OptIndex',subtitle='Safe intrusive object store',category='03 / DATA STRUCTURES',tags=['C++','Boost.Intrusive','Memory management'],text='A safe intrusive object store with stable addresses and compile-time index definitions. Centralized storage and object lifetime management keep optional or partitioned views consistent without duplicating objects.',detail='Built for bounded working sets and repeated queries, with explicit indexing control and an optional fixed-size pool. The design addresses consistency across indices without duplicating the stored objects.',href='OptIndex',extra=''),
 dict(name='RL Tools',subtitle='Composable reinforcement learning',category='04 / LEARNING ALGORITHMS',tags=['C++','Templates','LibTorch'],text='A lightweight reinforcement learning framework that separates agents from their value models. SARSA and Q-learning agents work with tabular storage or Torch-based function approximators.',detail='Template-based interfaces keep the interaction loop small: observe a state, select an action, and collect a reward. Core components are header-only; neural models use LibTorch.',href='rl_tools',extra='')
]

PROJECTS.append(dict(name='NESSi 2.0',subtitle='Nonequilibrium systems simulation',category='05 / COLLABORATIVE RESEARCH SOFTWARE',tags=['C++','Green’s functions','DMFT'],text='A shared research library for nonequilibrium Green’s functions and interacting quantum systems. Version 2.0 adds memory-truncated time propagation and steady-state calculations.',detail='I contributed to the development of NESSi 2.0 through my research on nonequilibrium many-body methods. The package supports accurate numerical integration and distributed-memory calculations for quantum dynamics.',href='https://github.com/nessi-cntr/nessi',extra=link('publications.html#paper-33','NESSi 2.0 paper →')))

def project_card(p,compact=False):
    repo_url = p['href'] if p['href'].startswith('https://') else GITHUB+'/'+p['href']
    details='' if compact else f'<p class="project-detail">{p["detail"]}</p>'
    return f'<article class="project-card"><p class="eyebrow">{p["category"]}</p><h3>{link(repo_url,p["name"]+" ↗")}</h3><p class="project-subtitle">{p["subtitle"]}</p><p>{p["text"]}</p>{details}<ul class="tags" aria-label="Technologies">'+''.join(f'<li>{t}</li>' for t in p['tags'])+f'</ul><div class="project-links">{link(repo_url,"Repository ↗")}{p["extra"]}</div></article>'

# Selection lives in the reviewed dataset; newest year first, citations break ties.
selected = sorted(
    (p for p in PUBLICATIONS if p.get('selected')),
    key=lambda p: (-p['year'], -p.get('citation_count', 0), p['title']),
)
body=f'''<section class="home-intro">
  <div class="home-heading"><h1>Jiajun Li</h1>
  <p class="home-tagline">AI, computation, and trading.</p></div>
  <div class="home-details">
  <p class="home-bio">Quantitative researcher at Qube Research &amp; Technologies in Zürich.</p>
  <div class="home-description"><p class="home-bio">I develop algorithms and computational methods across quantitative finance, AI, and quantum physics. My current work applies machine learning and high-performance computing to high-frequency trading, market microstructure research, and short-term forecasting. Previously, I studied strongly correlated quantum systems and nonequilibrium light–matter dynamics.</p>
  <p class="home-bio">For more than a decade, I’ve built high-performance software in C++, Python, Fortran, and CUDA. My open-source work includes quantum simulation tools, low-latency AI inference, and efficient C++ data structures.</p>
  <div class="home-links">{link(SCHOLAR,'Google Scholar')}{link(GITHUB,'GitHub')}{link(LINKEDIN,'LinkedIn')}</div></div></div>
</section>
<section class="home-experience" aria-labelledby="experience-heading">
  <div class="home-section-heading"><h2 id="experience-heading">Experience</h2>{link('about.html','Full background →')}</div>
  <ul class="experience-list">
    <li><span class="experience-date">2025 — present</span><span><strong>Qube Research &amp; Technologies</strong><span class="experience-role">Quantitative Researcher · Zürich</span></span></li>
    <li><span class="experience-date">2022 — 2025</span><span><strong>IMC Trading</strong><span class="experience-role">Quantitative Developer, 2022–2024; garden leave, 2024–2025 · Zug</span></span></li>
    <li><span class="experience-date">2021 — 2022</span><span><strong>Paul Scherrer Institut</strong><span class="experience-role">PSI Fellow · Villigen</span></span></li>
    <li><span class="experience-date">2017 — 2021</span><span><strong>FAU Erlangen–Nürnberg</strong><span class="experience-role">Postdoctoral Research Associate · Erlangen</span></span></li>
  </ul>
  <p class="home-education"><strong>PhD in Physics</strong> · University at Buffalo, State University of New York</p>
</section>
<section class="home-projects" aria-labelledby="projects-heading">
  <div class="home-section-heading"><h2 id="projects-heading">Selected projects</h2>{link('projects.html','All projects →')}</div>
  <div class="selected-project-list">
    <article><h3>Low latency tools</h3><p>{link(GITHUB+'/OptIndex','OptIndex')} — A safe intrusive C++ object store with stable addresses, managed object lifetimes, and optional indices.</p></article>
    <article><h3>AI inference optimization</h3><p>{link(GITHUB+'/QLeaf','QLeaf')} — Low-latency decision-tree ensemble inference on CPUs and GPUs.</p></article>
    <article><h3>Quantum physics</h3><p>{link('https://github.com/nessi-cntr/nessi','NESSi 2.0')} — Collaborative software for nonequilibrium Green’s-function simulations; {link(GITHUB+'/QuDrip','QuDrip')} — Exact quantum many-body simulation and dynamics.</p></article>
  </div>
</section>
<section class="home-publications" aria-labelledby="selected-heading">
  <div class="home-section-heading"><h2 id="selected-heading">Selected publications</h2>{link('publications.html','All publications →')}</div>
  <div class="publication-list">{''.join(publication(p,True) for p in selected)}</div>
</section>'''
shell('index.html','Overview','Jiajun Li — AI, computation, and trading. Quantitative researcher and physicist building high-performance software.',body)

body=hero('PROFILE / BACKGROUND','Research meets engineering.','I’m a quantitative researcher based in Zürich. My work concerns machine learning, market microstructure, and real-time computation.')+f'''
<div class="two-column section"><aside class="side-heading"><span class="eyebrow">01 / PROFILE</span><h2>From machine learning<br>to real-time decisions.</h2></aside><div class="prose"><p>Since 2022, I have worked at IMC Trading and Qube Research &amp; Technologies on high-frequency trading and short-term forecasting. My work includes machine-learning models for market-making strategies, market microstructure research, and the implementation of trading systems and low-latency inference in C++.</p><p>I have spent more than a decade developing computational methods and scientific software, mainly in C++, Python, Fortran, and CUDA. Much of this work involves numerical algorithms and performance-critical code.</p><p>Trained as a theoretical physicist, I combine mathematical insight with a hands-on, empirical approach to time series research, trading strategy design, and performance engineering. My work at QRT and IMC has deepened my understanding of statistics and market microstructure.</p><ul class="tags" aria-label="Programming languages"><li>C++</li><li>Python</li><li>Fortran</li><li>CUDA</li></ul><div class="inline-links">{link(LINKEDIN,'LinkedIn profile ↗')}{link(SCHOLAR,'Google Scholar ↗')}</div></div></div>
<section class="section">{section_heading('02 / EXPERIENCE','Industry &amp; research')}<div class="timeline">
<article><span class="timeline-label">MAR 2025 — PRESENT</span><div><h3>Quantitative Researcher</h3><p class="venue">Qube Research &amp; Technologies · Zürich, Switzerland</p><p>High-frequency trading and short-term alpha research.</p></div></article>
<article><span class="timeline-label">NOV 2022 — MAR 2025</span><div><h3>Quantitative Developer</h3><p class="venue">IMC Trading · Zug, Switzerland</p><p><strong>Nov 2022 – Apr 2024</strong><br>Machine-learning signals for market-making strategies, delta-one market-access engineering, and market microstructure research.</p><p class="career-note">Garden leave · Apr 2024 – Mar 2025</p></div></article>
<article><span class="timeline-label">AUG 2021 — OCT 2022</span><div><h3>PSI Fellow</h3><p class="venue">Paul Scherrer Institut · Villigen, Switzerland</p><p>Quantum Monte Carlo algorithms and Green’s-function approximations; light-induced superconductivity and photodoping; optimal control of laser-induced quantum states in solids.</p></div></article>
<article><span class="timeline-label">AUG 2017 — AUG 2021</span><div><h3>Postdoctoral Research Associate</h3><p class="venue">FAU Erlangen–Nürnberg · Erlangen, Germany</p><p>Foundations of strongly coupled lattice quantum electrodynamics, hidden phases in photodoped Mott insulators, and steady-state photodoping theory. Developed time-truncation and steady-state methods for non-Markovian integro-differential equations.</p></div></article>
</div></section>
<section class="section">{section_heading('03 / EDUCATION','A foundation in physics')}<div class="timeline">
<article><span class="timeline-label">PHD / PHYSICS</span><div><h3>University at Buffalo</h3><p class="venue">State University of New York</p><p>Thesis: <em>Non-equilibrium Effects in Dissipative Strongly Correlated Systems</em> (2017).</p><p>President of the Physics Graduate Student Association; member of the UB Chinese Football Team.</p>{link('https://arxiv.org/pdf/2009.12865','Read the thesis · PDF ↓','text-link')}</div></article>
<article><span class="timeline-label">BSC / PHYSICS</span><div><h3>Beijing Normal University</h3><p>Thesis: <em>Mie scattering of electromagnetic waves over nanoheterostructures.</em></p><p>White Pigeon Volunteers, Singularity Drama, and University Debate Team.</p></div></article>
<article><span class="timeline-label">2016 / CERTIFICATE</span><div><h3>Computational Sciences</h3><p class="venue">Advanced Certificate · University at Buffalo</p></div></article>
</div></section>
<section class="section">{section_heading('04 / RESEARCH THEMES','Questions and methods')}<div class="theme-grid"><article><h3>Driven quantum matter</h3><p>Photodoping, resistive switching, hidden superconductivity, and the dynamics of correlated electrons away from equilibrium.</p></article><article><h3>Light–matter interaction</h3><p>Gauge-invariant descriptions of strongly coupled light and matter, collective behavior in cavities, and photon-mediated interactions.</p></article><article><h3>Numerical many-body methods</h3><p>Quantum Monte Carlo, impurity solvers, dynamical mean-field theory, and efficient treatment of non-Markovian dynamics.</p></article></div></section>'''
shell('about.html','Background','Jiajun Li’s experience at QRT, IMC Trading, PSI, and FAU; physics education at University at Buffalo and Beijing Normal University.',body)

body=hero('ENGINEERING / OPEN SOURCE','Projects &amp; software.','C++ tools for scientific computing and performance-sensitive systems. Each project explores a specific computational problem, with source code and implementation details on GitHub.')+f'<section class="section"><div class="project-grid">'+''.join(project_card(p) for p in PROJECTS)+f'</div></section><section class="closing"><div><p class="eyebrow">RESEARCH ↔ SOFTWARE</p><h2>Code behind the physics.</h2></div><div><p>QuDrip supports research on light-controlled quantum matter and photodoped superconductivity. The publication record also includes the collaborative NESSi 2.0 simulation package.</p><div class="inline-links">{link("publications.html#paper-33","NESSi 2.0 paper →")}{link(GITHUB,"All GitHub repositories ↗")}</div></div></section>'
shell('projects.html','Projects','QLeaf, QuDrip, OptIndex, RL Tools, and contributions to NESSi 2.0 — engineering and research software by Jiajun Li.',body)

counts={k:sum(p['kind']==k for p in PUBLICATIONS) for k in TYPES}
years=sorted({p['year'] for p in PUBLICATIONS},reverse=True)
body=hero('RESEARCH / PUBLICATION RECORD','Publications.','Journal articles, preprints, a doctoral thesis, and conference abstracts. Research in nonequilibrium quantum matter, light–matter coupling, and computational methods.')+f'''
<div class="publication-summary"><div><strong>{counts['article']}</strong><span>JOURNAL / PROCEEDINGS</span></div><div><strong>{counts['preprint']}</strong><span>PREPRINTS</span></div><div><strong>{counts['thesis']}</strong><span>THESIS</span></div><div><strong>{counts['abstract']}</strong><span>MEETING ABSTRACTS</span></div></div>
<div class="bibliography-tools"><div class="inline-links">{link(SCHOLAR,'Google Scholar ↗')}{link('assets/publications.bib','Download all BibTeX ↓',extra='download')}</div><p>PDF links use the journal copy for confirmed open-access articles and arXiv for other papers. Meeting abstracts link to their records; a separate paper PDF is not available.</p></div>
<form class="publication-filters" id="publication-filters" role="search" hidden><div class="search-field"><label for="publication-search">Search publications</label><input type="search" id="publication-search" placeholder="Title, author, topic, DOI…" autocomplete="off"></div><div><label for="publication-type">Publication type</label><select id="publication-type"><option value="all">All types</option>{''.join(f'<option value="{k}">{v}</option>' for k,v in TYPES.items())}</select></div><div><label for="publication-year">Year</label><select id="publication-year"><option value="all">All years</option>{''.join(f'<option value="{y}">{y}</option>' for y in years)}</select></div><button type="reset" class="reset-button">Reset</button></form>
<div class="results-heading"><h2>Complete record</h2><p id="result-count" role="status" aria-live="polite">{len(PUBLICATIONS)} publications</p></div>
<div class="publication-list" id="publication-list">{''.join(publication(p) for p in PUBLICATIONS)}</div><p id="no-results" class="no-results" hidden>No publications match these filters. Try a different search or reset the filters.</p>
<details class="record-notes"><summary>About this bibliography</summary><p>Compiled from the 46 records in my Google Scholar profile, with four duplicate preprint entries consolidated into their published papers. Earlier titles remain available under “Earlier titles / versions.” The 2024 paper on photon-mediated spin interactions is additionally verified through arXiv and the publisher’s metadata. This gives 43 distinct records.</p><p>Publication metadata and access links were checked on 19 October 2026. Preprints are identified separately from journal articles. Downloads are hosted by the publisher or arXiv.</p></details>'''
shell('publications.html','Publications','Complete publication record of Jiajun Li, with journal links, arXiv PDFs, and downloadable BibTeX.',body,True)

body=hero('CONTACT / PROFILES','Get in touch.','For professional connections, research, and open-source work, you can reach me by email or through the profiles below.')+f'''<p class="contact-email">Email: <a href="mailto:jiajunligg@gmail.com">jiajunligg@gmail.com</a></p><section class="contact-grid section"><a href="{LINKEDIN}" class="contact-card"><span class="eyebrow">01 / PROFESSIONAL</span><h2>LinkedIn <span aria-hidden="true">↗</span></h2><p>Experience, background, and professional connections.</p><span class="contact-handle">linkedin.com/in/jiajunli</span></a><a href="{escape(SCHOLAR,quote=True)}" class="contact-card"><span class="eyebrow">02 / RESEARCH</span><h2>Google Scholar <span aria-hidden="true">↗</span></h2><p>Publications, citations, and related research.</p><span class="contact-handle">Jiajun Li / Google Scholar</span></a><a href="{GITHUB}" class="contact-card"><span class="eyebrow">03 / CODE</span><h2>GitHub <span aria-hidden="true">↗</span></h2><p>Source code, documentation, and project discussions.</p><span class="contact-handle">github.com/LiJ21</span></a></section><div class="contact-location"><span class="eyebrow">BASED IN</span><p>Zürich area, Switzerland</p></div>'''
shell('contact.html','Contact','Contact Jiajun Li by email or connect on LinkedIn, Google Scholar, and GitHub.',body)
shell('404.html','Page not found','The requested page could not be found.',hero('404 / PAGE NOT FOUND','Outside the domain.','This page does not exist or has moved.')+'<div class="actions section">'+link('/','Return to overview →','button')+'</div>')
p=ROOT/'404.html';p.write_text(p.read_text().replace('href="assets/','href="/assets/').replace('href="index.html"','href="/index.html"').replace('href="about.html"','href="/about.html"').replace('href="publications.html"','href="/publications.html"').replace('href="projects.html"','href="/projects.html"').replace('href="contact.html"','href="/contact.html"'))
(ROOT/'assets/publications.bib').write_text('% Jiajun Li — publication record, checked 2026-10-19\n% UTF-8; compatible with biblatex/biber.\n\n'+'\n\n'.join(bibtex(p) for p in PUBLICATIONS)+'\n')
print(f'Generated six pages and {len(PUBLICATIONS)} BibTeX entries.')
