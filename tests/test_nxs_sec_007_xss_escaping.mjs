// NXS-SEC-007 — escHtml() escaped only & < > " , but several values are
// interpolated INSIDE single-quoted JS strings within double-quoted on*
// attributes, e.g. onclick="navigateTo('${escHtml(path)}')". A single quote in
// an attacker-controlled value (a file/dir name, a remote container name, ...)
// breaks out of the JS string and executes. This test extracts the escaping
// helpers from static/js/app.js and proves the JS-string context is safe.
//
// Run: node tests/test_nxs_sec_007_xss_escaping.mjs  (exit 0 = pass)
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import assert from 'node:assert/strict';

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, '..', 'static', 'js', 'app.js'), 'utf8');

function extract(name) {
  const m = src.match(new RegExp('function ' + name + '\\(s\\) \\{[\\s\\S]*?\\n\\}'));
  if (!m) throw new Error('helper not found in app.js: ' + name);
  return new Function('return ' + m[0])();
}

const escHtml = extract('escHtml');
const escJs = extract('escJs'); // must exist post-fix

// 1. escHtml must now also neutralize single quotes and backticks (HTML contexts)
const h = escHtml(`a'"<>&\``);
assert.ok(!/[<>]/.test(h), 'escHtml must encode < >');
assert.ok(!h.includes("'"), 'escHtml must encode single quotes');
assert.ok(!h.includes('`'), 'escHtml must encode backticks');

// 2. escJs output must have NO unescaped single quote (would break the JS string)
const payload = "a');alert(document.cookie);//";
const out = escJs(payload);
assert.ok(!/(^|[^\\])'/.test(out), 'escJs leaves an unescaped single quote: ' + out);
assert.ok(!/[\n\r]/.test(escJs("a\nb")), 'escJs must escape newlines');

// 3. End-to-end: a value placed inside a single-quoted JS string literal must
//    round-trip back to itself (i.e. it stays DATA and does not execute).
const roundtrip = new Function("return '" + escJs(payload) + "'")();
assert.strictEqual(roundtrip, payload, 'payload must remain an inert string, not break out');

console.log('NXS-SEC-007 escaping tests: PASS');
