(() => {
  const root = document.querySelector('.bw-site');
  if (!root) return;

  const samples = {
    curl: `# Hand the agent a task in plain English\ncurl https://api.browser-use.com/api/v4/runs \\\n+  -H "X-Browser-Use-API-Key: $BROWSER_USE_API_KEY" \\\n+  -H "Content-Type: application/json" \\\n+  -d '{ "task": "Find the top Hacker News story and return its title and points" }'\n\n# { "id":"9c2f...", "status":"queued", "sessionId":"5b81...",\n#   "eventsUrl":"https://api.browser-use.com/..." }`,
    python: `import os\nfrom browser_use import Agent\n\nagent = Agent(\n    task="Find the top Hacker News story and return its title and points",\n    api_key=os.environ["BROWSER_USE_API_KEY"],\n)\nresult = await agent.run()\nprint(result)`,
    node: `const response = await fetch("https://api.browser-use.com/api/v4/runs", {\n  method: "POST",\n  headers: {\n    "X-Browser-Use-API-Key": process.env.BROWSER_USE_API_KEY,\n    "Content-Type": "application/json",\n  },\n  body: JSON.stringify({\n    task: "Find the top Hacker News story and return its title and points",\n  }),\n});\n\nconsole.log(await response.json());`
  };
  samples.curl = samples.curl.replaceAll('\n+  ', '\n  ');
  const codeTarget = document.getElementById('code-sample');
  const codeStatus = root.querySelector('.bw-code-status');
  const tabButtons = [...root.querySelectorAll('[data-code-tab]')];
  let activeSample = 'curl';

  function setSample(name) {
    if (!samples[name] || !codeTarget) return;
    activeSample = name;
    codeTarget.textContent = samples[name];
    tabButtons.forEach((button) => {
      const selected = button.dataset.codeTab === name;
      button.classList.toggle('is-active', selected);
      button.setAttribute('aria-selected', String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
    if (codeStatus) codeStatus.textContent = '';
  }
  setSample(activeSample);

  tabButtons.forEach((button, index) => {
    button.addEventListener('click', () => setSample(button.dataset.codeTab));
    button.addEventListener('keydown', (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabButtons.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + tabButtons.length) % tabButtons.length;
      tabButtons[next].focus();
      setSample(tabButtons[next].dataset.codeTab);
    });
  });

  root.querySelector('.bw-copy-button')?.addEventListener('click', async (event) => {
    const button = event.currentTarget;
    try {
      await navigator.clipboard.writeText(samples[activeSample]);
      if (codeStatus) codeStatus.textContent = 'Copied to clipboard';
      button.classList.add('is-copied');
      button.querySelector('span').textContent = 'Copied';
      window.setTimeout(() => {
        button.classList.remove('is-copied');
        button.querySelector('span').textContent = 'Copy';
      }, 1800);
    } catch {
      if (codeStatus) codeStatus.textContent = 'Clipboard access is unavailable in this browser.';
    }
  });

  const menuToggle = root.querySelector('.bw-menu-toggle');
  const mobileMenu = root.querySelector('.bw-mobile-menu');
  menuToggle?.addEventListener('click', () => {
    const open = menuToggle.getAttribute('aria-expanded') !== 'true';
    menuToggle.setAttribute('aria-expanded', String(open));
    menuToggle.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
    mobileMenu.hidden = !open;
    root.classList.toggle('bw-menu-open', open);
  });
  root.querySelectorAll('.bw-nav__trigger').forEach((trigger) => {
    trigger.addEventListener('click', () => {
      const wasOpen = trigger.getAttribute('aria-expanded') === 'true';
      root.querySelectorAll('.bw-nav__trigger').forEach((other) => {
        other.setAttribute('aria-expanded', 'false');
        const panel = root.querySelector(`#${other.getAttribute('aria-controls')}`);
        if (panel) panel.hidden = true;
      });
      trigger.setAttribute('aria-expanded', String(!wasOpen));
      const panel = root.querySelector(`#${trigger.getAttribute('aria-controls')}`);
      if (panel) panel.hidden = wasOpen;
    });
  });
  document.addEventListener('click', (event) => {
    if (event.target.closest('.bw-nav__group')) return;
    root.querySelectorAll('.bw-nav__trigger').forEach((trigger) => {
      trigger.setAttribute('aria-expanded', 'false');
      const panel = root.querySelector(`#${trigger.getAttribute('aria-controls')}`);
      if (panel) panel.hidden = true;
    });
  });
  root.querySelectorAll('.bw-mobile-menu a').forEach((link) => link.addEventListener('click', () => {
    if (!link.href.includes('#')) return;
    mobileMenu.hidden = true;
    menuToggle?.setAttribute('aria-expanded', 'false');
    menuToggle?.setAttribute('aria-label', 'Open navigation menu');
    root.classList.remove('bw-menu-open');
  }));
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    root.querySelectorAll('.bw-nav__trigger').forEach((trigger) => {
      trigger.setAttribute('aria-expanded', 'false');
      const panel = root.querySelector(`#${trigger.getAttribute('aria-controls')}`);
      if (panel) panel.hidden = true;
    });
    if (menuToggle?.getAttribute('aria-expanded') === 'true') {
      menuToggle.setAttribute('aria-expanded', 'false');
      menuToggle.setAttribute('aria-label', 'Open navigation menu');
      mobileMenu.hidden = true;
      root.classList.remove('bw-menu-open');
      menuToggle.focus();
    }
  });

  root.querySelectorAll('.bw-faq-question').forEach((button) => {
    button.addEventListener('click', () => {
      const willOpen = button.getAttribute('aria-expanded') !== 'true';
      root.querySelectorAll('.bw-faq-question').forEach((other) => {
        other.setAttribute('aria-expanded', 'false');
        const answer = root.querySelector(`#${other.getAttribute('aria-controls')}`);
        if (answer) answer.hidden = true;
      });
      button.setAttribute('aria-expanded', String(willOpen));
      const answer = root.querySelector(`#${button.getAttribute('aria-controls')}`);
      if (answer) answer.hidden = !willOpen;
    });
  });

  const grid = root.querySelector('.bw-concurrency-grid');
  if (grid) {
    const fragment = document.createDocumentFragment();
    for (let i = 0; i < 192; i += 1) {
      const cell = document.createElement('i');
      cell.style.setProperty('--cell-delay', `${(i % 24) * 22 + Math.floor(i / 24) * 55}ms`);
      if (i % 13 === 0 || i % 17 === 0) cell.classList.add('is-hot');
      fragment.append(cell);
    }
    grid.append(fragment);
  }
  const ticks = root.querySelector('.bw-ticks');
  if (ticks) {
    const heights = [17,25,14,31,20,12,23,18,40,19,28,13,22,36,18,15,31,21,46,23,17,29,16,39,22,14,33,19,50,23,17,29,13,36,20,15,42,18,27,13,37,22];
    const fragment = document.createDocumentFragment();
    heights.forEach((height, index) => {
      const tick = document.createElement('i');
      tick.style.setProperty('--bw-tick-height', `${height}px`);
      tick.style.setProperty('--tick-delay', `${index * 18}ms`);
      if ([8, 18, 28, 36].includes(index)) tick.classList.add('is-change');
      fragment.append(tick);
    });
    ticks.append(fragment);
  }

  const revealTargets = root.querySelectorAll('.bw-reveal, .bw-benchmark__chart, .bw-progress__fill');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        if (entry.target.matches('.bw-progress__fill')) entry.target.style.width = `${entry.target.dataset.progress}%`;
        observer.unobserve(entry.target);
      });
    }, { threshold: .18, rootMargin: '0px 0px -4% 0px' });
    revealTargets.forEach((item) => observer.observe(item));
  } else {
    revealTargets.forEach((item) => {
      item.classList.add('is-visible');
      if (item.matches('.bw-progress__fill')) item.style.width = `${item.dataset.progress}%`;
    });
  }

  const cookieNotice = root.querySelector('.bw-cookie-notice');
  let cookieChoice = null;
  try { cookieChoice = window.localStorage.getItem('bw-cookie-choice'); } catch { /* storage can be disabled */ }
  if (!cookieChoice && cookieNotice) cookieNotice.hidden = false;
  cookieNotice?.querySelectorAll('[data-cookie-choice]').forEach((button) => {
    button.addEventListener('click', () => {
      try { window.localStorage.setItem('bw-cookie-choice', button.dataset.cookieChoice); } catch { /* dismissal still works without storage */ }
      cookieNotice.hidden = true;
    });
  });
  root.querySelector('[data-cookie-settings]')?.addEventListener('click', () => {
    if (cookieNotice) cookieNotice.hidden = false;
  });

  const markdownToggle = root.querySelector('.bw-markdown-toggle');
  const markdownPreview = root.querySelector('#markdown-preview');
  markdownToggle?.addEventListener('click', () => {
    const open = markdownToggle.getAttribute('aria-expanded') !== 'true';
    markdownToggle.setAttribute('aria-expanded', String(open));
    if (markdownPreview) markdownPreview.hidden = !open;
    markdownToggle.textContent = open ? 'Hide Markdown' : 'View as Markdown';
  });
})();
