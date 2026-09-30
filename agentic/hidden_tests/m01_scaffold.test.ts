import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync, statSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';

const root = fileURLToPath(new URL('..', import.meta.url));

describe('m01 scaffold', () => {
  it('package.json has build and test scripts and uses vite + vitest + typescript', () => {
    const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
    expect(typeof pkg.scripts?.build).toBe('string');
    expect(typeof pkg.scripts?.test).toBe('string');
    const deps = { ...pkg.dependencies, ...pkg.devDependencies };
    for (const d of ['vite', 'vitest', 'typescript']) expect(deps, d).toHaveProperty(d);
  });
  it('tsconfig enables strict mode', () => {
    const p = join(root, 'tsconfig.json');
    expect(existsSync(p)).toBe(true);
    const text = readFileSync(p, 'utf8');
    // tsconfig may contain comments, so check textually; also accept strict via an extended base
    const strict = /"strict"\s*:\s*true/.test(text) ||
      ['tsconfig.app.json', 'tsconfig.base.json'].some(f => existsSync(join(root, f)) &&
        /"strict"\s*:\s*true/.test(readFileSync(join(root, f), 'utf8')));
    expect(strict).toBe(true);
  });
  it('has src/, tests/ and a README', () => {
    expect(statSync(join(root, 'src')).isDirectory()).toBe(true);
    expect(statSync(join(root, 'tests')).isDirectory()).toBe(true);
    expect(['README.md', 'README', 'readme.md'].some(f => existsSync(join(root, f)))).toBe(true);
  });
});
