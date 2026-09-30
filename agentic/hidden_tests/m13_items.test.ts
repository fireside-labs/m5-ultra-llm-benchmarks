import { describe, it, expect } from 'vitest';
import { createInventory, addItem, removeItem, equip, useItem } from '../src/inventory';

const sword = { id: 'w1', name: 'Sword', kind: 'weapon' as const, power: 3 };
const axe = { id: 'w2', name: 'Axe', kind: 'weapon' as const, power: 4 };
const mail = { id: 'a1', name: 'Mail', kind: 'armor' as const, power: 2 };
const potion = { id: 'p1', name: 'Healing Potion', kind: 'potion' as const, power: 10 };
const scroll = { id: 's1', name: 'Scroll', kind: 'scroll' as const };

describe('m13 items and inventory', () => {
  it('respects capacity', () => {
    const inv = createInventory(2);
    expect(addItem(inv, sword)).toBe(true);
    expect(addItem(inv, mail)).toBe(true);
    expect(addItem(inv, potion)).toBe(false);
    expect(inv.items.map(i => i.id).sort()).toEqual(['a1', 'w1']);
  });
  it('drop returns the item and removes it', () => {
    const inv = createInventory(5);
    addItem(inv, sword); addItem(inv, potion);
    expect(removeItem(inv, 'p1')?.id).toBe('p1');
    expect(inv.items.map(i => i.id)).toEqual(['w1']);
    expect(removeItem(inv, 'nope')).toBeUndefined();
  });
  it('equips weapons and armor into slots, replacing the previous one', () => {
    const inv = createInventory(5);
    addItem(inv, sword); addItem(inv, axe); addItem(inv, mail); addItem(inv, potion);
    expect(equip(inv, 'w1')).toBe(true);
    expect(equip(inv, 'a1')).toBe(true);
    expect(inv.equipped.weapon?.id).toBe('w1');
    expect(inv.equipped.armor?.id).toBe('a1');
    expect(equip(inv, 'w2')).toBe(true);
    expect(inv.equipped.weapon?.id).toBe('w2');
    expect(inv.items.map(i => i.id)).toContain('w1');
    expect(equip(inv, 'p1')).toBe(false);
    expect(equip(inv, 'missing')).toBe(false);
  });
  it('dropping an equipped item unequips it', () => {
    const inv = createInventory(5);
    addItem(inv, sword); equip(inv, 'w1');
    removeItem(inv, 'w1');
    expect(inv.equipped.weapon).toBeUndefined();
  });
  it('potions heal (capped at maxHp) and are consumed; gear cannot be used', () => {
    const inv = createInventory(5);
    addItem(inv, potion); addItem(inv, { ...potion, id: 'p2' }); addItem(inv, sword); addItem(inv, scroll);
    const hero = { hp: 3, maxHp: 30, attack: 5, defense: 1 };
    expect(useItem(inv, 'p1', hero)).toBe(true);
    expect(hero.hp).toBeGreaterThan(3);
    expect(hero.hp).toBeLessThanOrEqual(30);
    expect(inv.items.map(i => i.id)).not.toContain('p1');
    const full = { hp: 30, maxHp: 30, attack: 5, defense: 1 };
    useItem(inv, 'p2', full);
    expect(full.hp).toBe(30);
    expect(useItem(inv, 'w1', hero)).toBe(false);
    expect(inv.items.map(i => i.id)).toContain('w1');
    expect(useItem(inv, 's1', hero)).toBe(true);
    expect(inv.items.map(i => i.id)).not.toContain('s1');
  });
});
