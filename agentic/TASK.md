# Agentic long-context task: "Deepdelve"

Every harness and model gets this file verbatim as its first message, in an empty
git repo. The task is deliberately larger than any model can finish, so sessions run
until the context reaches the target (1M tokens for DeepSeek V4, 262k for Qwen)
instead of stopping early.

---

Build **Deepdelve**, a browser roguelike dungeon crawler, in TypeScript with no
frameworks (Vite for dev/build, Vitest for tests). Work through the milestones below
in order. After each milestone:

1. run `npm test` and fix every failure before moving on,
2. run `npm run build` and fix every error,
3. commit with the message `milestone N: <title>`.

Do not skip milestones, do not stub features, and do not ask for confirmation. When
you finish the last milestone, start again at milestone 1 and extend each system
(more content, more tests, refactors that improve the code).

## Required interfaces

Some modules must expose these exact paths and exports (more exports, extra optional
fields and internal helpers are fine). Keep them pure logic: importing them must not
need a DOM, `window` or `localStorage`. Coordinates are integers, `x` = column,
`y` = row, `(0,0)` is the top-left corner.

```ts
// shared shapes (declare them wherever you like)
interface Point { x: number; y: number }
interface Rect { x: number; y: number; w: number; h: number }  // w x h tiles from (x,y)
interface Rng { next(): number; int(min: number, max: number): number }
interface Combatant { hp: number; maxHp: number; attack: number; defense: number }

// src/rng.ts (milestone 2)
export function createRng(seed: number): Rng;
//   next(): float in [0, 1); int(min, max): integer in [min, max], both inclusive.
//   Same seed => same sequence; instances share no state.

// src/map.ts (milestone 3)
export type Tile = 'wall' | 'floor' | 'door';  // you may add more tile kinds
export interface GameMap {
  readonly width: number; readonly height: number;
  get(x: number, y: number): Tile;        // out of bounds => 'wall'
  set(x: number, y: number, tile: Tile): void;
  inBounds(x: number, y: number): boolean;
  isWalkable(x: number, y: number): boolean;     // floor and door: true; wall/out of bounds: false
  isTransparent(x: number, y: number): boolean;  // floor: true; wall/out of bounds: false
}
export function createMap(width: number, height: number, fill?: Tile): GameMap; // default fill 'wall'
export function mapToJSON(map: GameMap): string;
export function mapFromJSON(json: string): GameMap;  // exact round-trip

// src/dungeon.ts (milestone 4)
export function generateDungeon(seed: number, width: number, height: number):
  { map: GameMap; rooms: Rect[]; start: Point };
//   Deterministic per seed. Outer border is never walkable. Rooms do not overlap and
//   every tile inside a room rect is walkable. All walkable tiles form one region
//   under 4-directional movement. `start` is walkable.

// src/movement.ts (milestone 6)
export function tryMove(map: GameMap, pos: Point, dx: number, dy: number): Point;
//   Returns the new position, or `pos` unchanged if the target is not walkable.

// src/fov.ts (milestone 7)
export function computeFov(map: GameMap, origin: Point, radius: number): Set<string>;
//   Keys are `${x},${y}` of visible tiles (origin included, blocking tiles that are
//   seen included). Only in-bounds tiles within Euclidean distance `radius`.

// src/pathfinding.ts (milestone 10)
export function findPath(map: GameMap, from: Point, to: Point): Point[] | null;
//   A* over walkable tiles, 4-directional, shortest path. Returns the steps after
//   `from`, ending with `to` ([] if from equals to), or null if unreachable.

// src/scheduler.ts (milestone 11)
export class Scheduler<T> {
  add(actor: T, speed: number): void;  // speed 100 = normal, 200 = twice as fast
  remove(actor: T): void;
  next(): T | undefined;               // the actor whose turn it is; undefined if empty
}

// src/combat.ts (milestone 12)
export function resolveAttack(attacker: Combatant, defender: Combatant, rng: Rng):
  { hit: boolean; critical: boolean; damage: number; killed: boolean };
//   Uses only `rng` for randomness. Applies damage to defender.hp (never below 0).
//   A miss deals 0 damage. killed === (defender.hp === 0).

// src/inventory.ts (milestone 13)
export type ItemKind = 'potion' | 'scroll' | 'weapon' | 'armor';
export interface Item { id: string; name: string; kind: ItemKind; power?: number }
export interface Inventory {
  items: Item[]; capacity: number;
  equipped: { weapon?: Item; armor?: Item };
}
export function createInventory(capacity: number): Inventory;
export function addItem(inv: Inventory, item: Item): boolean;         // false when full
export function removeItem(inv: Inventory, id: string): Item | undefined; // unequips it
export function equip(inv: Inventory, id: string): boolean;  // weapons/armor only; replaces the slot
export function useItem(inv: Inventory, id: string, target: Combatant): boolean;
//   Potions and scrolls are consumed (return true). A potion heals `power` HP (default
//   of your choice), never above maxHp. Weapons/armor cannot be used (false).
//   Equipped items stay in `items`.

// src/levels.ts (milestone 15)
export interface Level { depth: number; map: GameMap; stairsDown: Point; stairsUp?: Point }
export function createLevelManager(seed: number): { getLevel(depth: number): Level };
//   Depth starts at 1; stairsUp exists from depth 2. Levels are generated on first
//   visit and the same Level object (with any changes) is returned on later visits.

// src/save.ts (milestone 16)
export const SAVE_VERSION: number;
export function createGameState(seed: number): GameState;   // GameState is yours
export function serializeGame(state: GameState): string;     // JSON with a numeric "version"
export function deserializeGame(json: string): GameState;    // migrates old versions, throws on newer
export function migrateSave(data: { version: number }): { version: number }; // -> SAVE_VERSION

// src/status.ts (milestone 17)
export type StatusKind = 'poison' | 'haste' | 'slow' | 'confusion';
export interface StatusTarget { hp: number; maxHp: number; effects: { kind: StatusKind; turns: number }[] }
export function applyStatus(target: StatusTarget, kind: StatusKind, turns: number): void;
//   Re-applying a kind refreshes its duration instead of adding a second entry.
export function tickStatus(target: StatusTarget): void;
//   One turn: poison deals at least 1 damage (hp never below 0); every duration drops
//   by 1 and effects at 0 are removed.
export function hasStatus(target: StatusTarget, kind: StatusKind): boolean;
```

## Milestones

1. Project scaffold: Vite + TypeScript strict mode + Vitest, `src/`, `tests/`, a README.
2. Seeded RNG (mulberry32) with tests proving determinism.
3. Tile map model: walls, floors, doors; map serialization to/from JSON; tests.
4. Dungeon generator: rooms and corridors (BSP), guaranteed connectivity; property tests over 200 seeds.
5. Canvas renderer with a camera that follows the player; resize handling.
6. Player movement with keyboard input and wall collision; tests for movement rules.
7. Field of view (recursive shadowcasting) and fog of war; tests on hand-made maps.
8. Entities and components: health, attack, defense, inventory.
9. Monsters: five types with distinct behaviour (wander, chase, flee at low HP, ranged, pack).
10. A* pathfinding with tests, used by chasing monsters.
11. Turn scheduler with speed-based energy system; tests.
12. Combat: to-hit, damage, criticals, death; message log UI.
13. Items: potions, scrolls, weapons, armor; pick up, drop, equip, use.
14. Inventory UI with keyboard navigation.
15. Multiple dungeon levels with stairs; level persistence when you return.
16. Save and load the whole game to localStorage, versioned, with a migration test.
17. Status effects: poison, haste, slow, confusion, with durations; tests.
18. Traps: hidden, detectable, disarmable.
19. Shops on every third level with gold economy.
20. Experience, levelling and three character classes with different skills.
21. Skills with cooldowns and targeting (line, cone, radius); tests for targeting math.
22. Boss monster on level 10 with multiple phases.
23. Sound effects via WebAudio synthesis (no audio files); mute toggle.
24. Settings screen: keybindings (remappable), colour themes, text size.
25. Accessibility: full keyboard play, screen-reader friendly message log.
26. Achievements system with persistence.
27. Replay system: record inputs + seed, play back deterministically; test that a replay reproduces the same final state.
28. Performance pass: profile a 200x200 map with 300 monsters, keep a turn under 5 ms; add a benchmark test.
29. End-to-end tests driving the game loop headlessly for 1,000 turns across 20 seeds.
30. Documentation: architecture overview, contribution guide, and a changelog.
