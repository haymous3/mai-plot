import { describe, expect, it } from 'vitest';

import { AREAS, areasIn, describeBase, isInNigeria, nearestArea, states } from './nigeria-areas';

// SCRUM-214 — the realtor base-location list. A wrong coordinate here would put
// a realtor out of range of the very properties around them, so the data itself
// is checked, not just the helpers.
describe('the area list', () => {
  it('has every area inside Nigeria, so the server never refuses a picked area', () => {
    for (const a of AREAS) expect(isInNigeria(a.lat, a.lng), `${a.area}, ${a.state}`).toBe(true);
  });

  it('covers all 36 states and the FCT', () => {
    expect(states()).toHaveLength(37);
  });

  it('has no duplicate area within a state', () => {
    const keys = AREAS.map((a) => `${a.state}|${a.area}`);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('lists the launch markets first', () => {
    expect(states().slice(0, 3)).toEqual(['Lagos', 'FCT (Abuja)', 'Rivers']);
  });

  it('offers finer areas where it matters', () => {
    expect(areasIn('Lagos').length).toBeGreaterThan(10);
    expect(areasIn('Kano').map((a) => a.area)).toEqual(['Kano']);
  });
});

describe('isInNigeria', () => {
  it('refuses the usual mistakes', () => {
    expect(isInNigeria(51.5, -0.12)).toBe(false); // London (VPN)
    expect(isInNigeria(3.38, 6.52)).toBe(false); // Lagos, swapped
    expect(isInNigeria(0, 0)).toBe(false); // broken GPS
  });
});

describe('describing a base', () => {
  it('names the closest listed area', () => {
    expect(nearestArea(6.47, 3.59).area).toBe('Lekki');
    expect(describeBase(6.4698, 3.5852)).toBe('In Lekki, Lagos');
    expect(describeBase(6.49, 3.6)).toBe('Near Lekki, Lagos');
  });

  it('does not repeat a city that shares its state name', () => {
    expect(describeBase(12.0022, 8.592)).toBe('In Kano');
  });
});
