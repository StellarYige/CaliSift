// @vitest-environment jsdom
import 'fake-indexeddb/auto';
import {expect,it} from 'vitest';
import {commitSnapshot,readSnapshot,openDatabase} from '../src/database';
it('rechecks versions inside the transaction; exactly one writer wins',async()=>{
  const before=await readSnapshot();
  const results=await Promise.allSettled([commitSnapshot(before.revision,{name:'first'}),commitSnapshot(before.revision,{name:'second'})]);
  expect(results.filter(r=>r.status==='fulfilled')).toHaveLength(1);
  expect((await readSnapshot()).revision).toBe(before.revision+1);
});
it('quota and transaction abort preserve the previous snapshot and reject success',async()=>{
  const before=await readSnapshot();
  const original=IDBObjectStore.prototype.put;
  IDBObjectStore.prototype.put=function(){throw new DOMException('full','QuotaExceededError');};
  try {await expect(commitSnapshot(before.revision,{name:'lost'})).rejects.toThrow('空间不足');}
  finally {IDBObjectStore.prototype.put=original;}
  expect(await readSnapshot()).toEqual(before);
  (await openDatabase()).close();
});
