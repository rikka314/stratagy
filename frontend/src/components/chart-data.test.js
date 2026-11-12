import test from 'node:test'
import assert from 'node:assert/strict'
import { monthlyMatrix, toSeries } from './chart-data.js'

test('walk-forward equity fields and null gaps are preserved', () => {
  assert.deepEqual(toSeries([{date:'2025-01-01',strategy_equity:1.2},{date:'2025-01-02',strategy_equity:null}]), {x:['2025-01-01','2025-01-02'],y:[1.2,null]})
})
test('benchmark value selection does not fall back to strategy', () => {
  assert.deepEqual(toSeries([{date:'x',strategy_equity:2,buy_hold_equity:1}], 'buy_hold_equity').y, [1])
})
test('monthly matrix distinguishes missing months from a zero return', () => {
  const result=monthlyMatrix([{month:'2025-02',strategy_return:0}])
  assert.equal(result.z[0][0],null)
  assert.equal(result.z[0][1],0)
})
