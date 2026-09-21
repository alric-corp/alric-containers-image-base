'use strict';
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

function writable(directory) {
  const file = path.join(directory, `consumer-write-${process.pid}`);
  try {
    fs.writeFileSync(file, 'consumer-app');
    const valid = fs.readFileSync(file, 'utf8') === 'consumer-app';
    fs.unlinkSync(file);
    return valid;
  } catch (_) {
    return false;
  }
}

function security() {
  const fields = Object.fromEntries(fs.readFileSync('/proc/self/status', 'utf8')
    .trim().split('\n').map(line => {
      const colon = line.indexOf(':');
      return [line.slice(0, colon), line.slice(colon + 1).trim()];
    }));
  let readOnly = false;
  let rootError = 'write unexpectedly succeeded';
  const probe = '/app/certification-root-probe';
  try {
    fs.writeFileSync(probe, 'must fail on read-only root');
    fs.unlinkSync(probe);
  } catch (error) {
    readOnly = error.code === 'EROFS';
    rootError = String(error);
  }
  return {
    uid: process.getuid(), gid: process.getgid(),
    read_only_root: readOnly, root_write_error: rootError,
    writable_tmp: writable('/tmp'), writable_app_work: writable('/app/work'),
    cap_eff: fields.CapEff, no_new_privileges: fields.NoNewPrivs === '1',
  };
}

const server = http.createServer((request, response) => {
  let status = 200;
  let body = { status: 'ok' };
  try {
    const pathname = new URL(request.url, 'http://localhost').pathname;
    if (request.method !== 'GET') {
      status = 405;
      body = { status: 'method_not_allowed' };
    } else if (pathname === '/info') {
      body = {
        status: 'ok', runtime: 'node', runtime_version: process.versions.node,
        architecture: ({ x64: 'amd64', arm64: 'arm64' })[process.arch] || process.arch,
        security: security(),
      };
    } else if (!['/health', '/ready'].includes(pathname)) {
      status = 404;
      body = { status: 'not_found' };
    }
  } catch (error) {
    status = 500;
    body = { status: 'error', error: String(error) };
  }
  response.writeHead(status, { 'Content-Type': 'application/json' });
  response.end(JSON.stringify(body));
});
server.listen(8080, '0.0.0.0');

let shuttingDown = false;
function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;
  server.close(error => {
    if (error) {
      console.error(error);
      process.exitCode = 1;
    } else {
      console.log('consumer shutdown complete');
    }
  });
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
