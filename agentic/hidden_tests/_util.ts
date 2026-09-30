// Shared helpers for the hidden acceptance tests. Not a test file itself.
export type P = { x: number; y: number };

/** Tiny independent RNG so tests don't depend on the implementation under test. */
export function testRng(seed: number) {
  let a = seed >>> 0;
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  return { next, int: (min: number, max: number) => min + Math.floor(next() * (max - min + 1)) };
}

/** Build a GameMap-like grid from ASCII art using the implementation's createMap. */
export function fromAscii(createMap: any, rows: string[]) {
  const h = rows.length, w = rows[0].length;
  const map = createMap(w, h, 'wall');
  let origin: P | null = null;
  const marks: Record<string, P> = {};
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const c = rows[y][x];
      if (c === '#') map.set(x, y, 'wall');
      else if (c === '+') map.set(x, y, 'door');
      else {
        map.set(x, y, 'floor');
        if (c === '@') origin = { x, y };
        else if (c !== '.') marks[c] = { x, y };
      }
    }
  return { map, origin: origin as P | null, marks, w, h };
}

/** 4-directional BFS distances over walkable tiles. */
export function bfs(map: any, from: P): Map<string, number> {
  const dist = new Map<string, number>([[`${from.x},${from.y}`, 0]]);
  const q: P[] = [from];
  for (let i = 0; i < q.length; i++) {
    const c = q[i];
    const d = dist.get(`${c.x},${c.y}`)!;
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nx = c.x + dx, ny = c.y + dy, k = `${nx},${ny}`;
      if (!dist.has(k) && map.inBounds(nx, ny) && map.isWalkable(nx, ny)) {
        dist.set(k, d + 1);
        q.push({ x: nx, y: ny });
      }
    }
  }
  return dist;
}

export function walkableTiles(map: any): P[] {
  const out: P[] = [];
  for (let y = 0; y < map.height; y++)
    for (let x = 0; x < map.width; x++) if (map.isWalkable(x, y)) out.push({ x, y });
  return out;
}
