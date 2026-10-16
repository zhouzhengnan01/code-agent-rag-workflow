/* Offline read-only file preview. PrismJS 1.30.0 is vendored under vendor/prism/. */
(function (root, factory) {
  'use strict';
  const api = factory(typeof module === 'object' && module.exports
    ? require('./vendor/prism/prism.js') : root.Prism);
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.CodezznFileCode = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function (Prism) {
  'use strict';
  const MAX_HIGHLIGHT_BYTES = 200 * 1024;
  const extensions = Object.freeze({
    py: 'python', pyw: 'python', pyi: 'python', js: 'javascript', mjs: 'javascript', cjs: 'javascript',
    ts: 'typescript', mts: 'typescript', cts: 'typescript', jsx: 'jsx', tsx: 'tsx',
    html: 'markup', htm: 'markup', xml: 'markup', svg: 'markup', vue: 'markup', svelte: 'markup',
    css: 'css', json: 'json', jsonc: 'javascript', ipynb: 'json', webmanifest: 'json',
    yaml: 'yaml', yml: 'yaml', sh: 'bash', bash: 'bash', zsh: 'bash', ps1: 'powershell', psm1: 'powershell', psd1: 'powershell',
    sql: 'sql', md: 'markdown', markdown: 'markdown', mdx: 'markdown', toml: 'toml',
    c: 'c', h: 'c', cpp: 'cpp', cxx: 'cpp', cc: 'cpp', hpp: 'cpp', hxx: 'cpp',
    java: 'java', go: 'go', rs: 'rust', txt: 'plain', log: 'plain', csv: 'plain', tsv: 'plain'
  });
  const escapeHtml = value => String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  function languageFor(filename) {
    const name = String(filename || '').replace(/\\/g, '/').split('/').pop().toLowerCase();
    if (['.bashrc', '.bash_profile', '.zshrc', '.profile'].includes(name)) return 'bash';
    return extensions[name.split('.').pop()] || 'plain';
  }
  function isOversized(source) {
    // Count UTF-8 bytes, stopping early. No DOM work or large encoder allocation.
    let size = 0;
    for (let i = 0; i < source.length; i++) {
      const c = source.charCodeAt(i);
      if (c < 128) size++;
      else if (c < 2048) size += 2;
      else if (c >= 0xd800 && c <= 0xdbff && i + 1 < source.length &&
        source.charCodeAt(i + 1) >= 0xdc00 && source.charCodeAt(i + 1) <= 0xdfff) { size += 4; i++; }
      else size += 3;
      if (size > MAX_HIGHLIGHT_BYTES) return true;
    }
    return false;
  }
  function renderTokens(value) {
    if (typeof value === 'string') return escapeHtml(value);
    if (Array.isArray(value)) return value.map(renderTokens).join('');
    if (!value || typeof value !== 'object') return '';
    // Only grammar-owned class names are emitted; source text is always escaped.
    const classes = ['token', value.type, ...[].concat(value.alias || [])]
      .filter(name => typeof name === 'string' && /^[\w-]+$/.test(name));
    return `<span class="${classes.join(' ')}">${renderTokens(value.content)}</span>`;
  }
  function highlight(source, filename) {
    const code = String(source == null ? '' : source);
    const language = languageFor(filename);
    const grammar = Prism && Prism.languages && Prism.languages[language];
    if (!grammar || language === 'plain' || isOversized(code)) return escapeHtml(code);
    try {
      const env = { code, language, grammar };
      Prism.hooks.run('before-tokenize', env);
      env.tokens = Prism.tokenize(env.code, env.grammar);
      Prism.hooks.run('after-tokenize', env);
      // Preserve every source character, including NBSP (Prism.util.encode normalizes it).
      return renderTokens(env.tokens);
    } catch (_) {
      return escapeHtml(code);
    }
  }
  function svg(paths, kind, size, color) {
    return `<svg class="code-file-icon code-file-icon--${kind}" xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
  }
  const fileOutline = '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>';
  const icons = Object.freeze({
    folder: svg('<path d="M20 20H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2Z"/>', 'folder', 16, '#f97316'),
    'folder-open': svg('<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>', 'folder-open', 16, '#f97316'),
    file: svg(fileOutline, 'file', 14, '#78716c'),
    text: svg(fileOutline + '<path d="M8 13h8M8 17h6"/>', 'text', 14, '#78716c'),
    markdown: svg(fileOutline + '<path d="M7 17v-5l2 3 2-3v5m3-5v5m-1.5-1.5L14 17l1.5-1.5"/>', 'markdown', 14, '#78716c'),
    chevron: svg('<path d="m9 18 6-6-6-6"/>', 'chevron', 16, '#78716c'),
    download: svg('<path d="M12 15V3"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/>', 'download', 14, '#78716c'),
    close: svg('<path d="m18 6-12 12M6 6l12 12"/>', 'close', 14, '#78716c'),
    python: '<img class="code-file-icon code-file-icon--python" src="/assets/vendor/prism/python.png" width="14" height="14" alt="" aria-hidden="true" loading="lazy">'
  });
  function icon(filenameOrKind) {
    const name = String(filenameOrKind || '');
    if (Object.prototype.hasOwnProperty.call(icons, name)) return icons[name];
    if (name === 'open-folder') return icons['folder-open'];
    if (name === 'file-text') return icons.text;
    const language = languageFor(name);
    if (language === 'python') return icons.python;
    if (language === 'markdown') return icons.markdown;
    if (/(?:^|\/)(?:requirements[^/]*\.txt|[^/]*\.(?:txt|log|csv|tsv))$/i.test(name.replace(/\\/g, '/'))) return icons.text;
    return icons.file;
  }
  return Object.freeze({ highlight, languageFor, icon });
});
