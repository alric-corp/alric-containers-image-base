'use strict';
// A dependency-free preparation step executed through the dev image's npm.
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('server.cjs', 'utf8');
new vm.Script(source, { filename: 'server.cjs' });
fs.mkdirSync('dist', { recursive: true });
fs.writeFileSync('dist/server.cjs', '// Prepared by the consumer npm build.\n' + source);
