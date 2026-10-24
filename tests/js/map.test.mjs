import { test } from 'node:test';
import assert from 'node:assert/strict';
import { sameSpot } from '../../site/js/components/map.js';

test('sameSpot: markers on one point (a parcel centroid shared by many records) open a list instead of zooming', () => {
  assert.equal(sameSpot([[52.24, 21.08], [52.24, 21.08], { lat: 52.240001, lng: 21.080002 }]), true);
  assert.equal(sameSpot([[52.24, 21.08], [52.2401, 21.08]]), false, '~11 m apart: zoom in instead');
  assert.equal(sameSpot([[52.24, 21.08]]), false, 'a single marker is not a group');
  assert.equal(sameSpot([]), false);
});
