# Offline file syntax highlighting

- Dependency: **PrismJS 1.30.0**, MIT, copyright Lea Verou; original license retained in `LICENSE`.
- Official npm archive: https://registry.npmjs.org/prismjs/-/prismjs-1.30.0.tgz
- Archive SHA256: `ac16a9106a28c53b6a6313993c816a3a02525fdfefd7614fc1703df915a9fc11`.
- `prism.js` is an unmodified concatenation of the official minified core and selected grammar modules (with a manual-mode preamble); no CDN, dynamic grammar loader, or runtime network request.
- Reproduce with `node scripts/build-file-code-viewer.cjs /path/to/unpacked/prismjs/package`.
- Includes markup, CSS, C-like dependency, JavaScript, Python, TypeScript, JSX, TSX, JSON, YAML, Bash, PowerShell, SQL, Markdown, TOML, C, C++, Java, Go, and Rust.
- `python.png` is the exact 32 px public Python language icon observed in Browser Use, downloaded from https://cloud.browser-use.com/_next/image?url=%2Ficons%2Flanguages%2Fpython.png&w=32&q=75 and displayed at 14 px. Python logo remains the property of the Python Software Foundation; it is not covered by Prism's MIT license.

Load `/assets/vendor/prism/prism.js` before `/assets/file-code-viewer.js`. The helper tokenizes locally, safely escapes source text, and does not use Prism's DOM-scanning APIs. Unknown languages and source files over 200 KiB (UTF-8) are escaped plaintext. Grammar-based highlighting is lexical, not a semantic language server.
