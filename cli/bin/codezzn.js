#!/usr/bin/env node
'use strict';
if (Number(process.versions.node.split('.')[0]) < 20) {
  process.stderr.write('codezzn requires Node.js 20 or later.\n');
  process.exitCode = 1;
} else {
  require('../lib/main').main().then(code => { process.exitCode = code; }).catch(error => {
    const { Output, redact } = require('../lib/output');
    try {
      const options = require('../lib/args').parse(process.argv.slice(2));
      if (options.print && options.format !== 'text') new Output(options.format).result({ status: 'failed', error: error.message });
    } catch {}
    process.stderr.write(`codezzn: ${redact(error.message)}\n`);
    process.exitCode = 1;
  });
}
