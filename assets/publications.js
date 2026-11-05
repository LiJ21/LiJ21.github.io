(() => {
  'use strict';
  const form = document.querySelector('#publication-filters');
  if (!form) return;
  const search = document.querySelector('#publication-search');
  const type = document.querySelector('#publication-type');
  const year = document.querySelector('#publication-year');
  const count = document.querySelector('#result-count');
  const empty = document.querySelector('#no-results');
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  const papers = [...document.querySelectorAll('#publication-list .publication')].map(element => ({
    element,
    text: normalize(element.dataset.search),
    type: element.dataset.kind,
    year: element.dataset.year,
  }));
  function filter() {
    const terms = normalize(search.value.trim()).split(/\s+/).filter(Boolean);
    let visible = 0;
    papers.forEach(paper => {
      const matches = terms.every(term => paper.text.includes(term)) &&
        (type.value === 'all' || paper.type === type.value) &&
        (year.value === 'all' || paper.year === year.value);
      paper.element.hidden = !matches;
      visible += Number(matches);
    });
    count.textContent = (count.dataset.countTemplate || '{visible} of {total} publications')
      .replace('{visible}', String(visible)).replace('{total}', String(papers.length));
    empty.hidden = visible !== 0;
  }
  form.hidden = false;
  form.addEventListener('submit', event => event.preventDefault());
  form.addEventListener('input', filter);
  form.addEventListener('change', filter);
  form.addEventListener('reset', () => {
    // Apply after the browser restores each control's default value.
    setTimeout(filter, 0);
  });
  filter();
})();
