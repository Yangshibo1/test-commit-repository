import assert from 'node:assert/strict';
import test from 'node:test';
import {StableTerminalResize} from '../frontend/src/utils/terminalResize.ts';
const wide={rows:40,cols:160},small={rows:24,cols:80};
test('alternating transient resolutions do not reach the PTY until stable',()=>{
 const gate=new StableTerminalResize(120),sent=[];
 for(let time=0;time<1000;time+=30){const value=gate.offer(time%60===0?wide:small,time);if(value)sent.push(value);}
 assert.deepEqual(sent,[]);
 assert.equal(gate.offer(wide,1100),null);
 assert.deepEqual(gate.offer(wide,1220),wide);
});
test('repeated fits for one geometry send exactly once, including returning from a transient size',()=>{
 const gate=new StableTerminalResize(120);
 gate.offer(wide,0);assert.deepEqual(gate.offer(wide,120),wide);
 for(let time=130;time<1000;time+=10)assert.equal(gate.offer(wide,time),null);
 assert.equal(gate.offer(small,1010),null);
 assert.equal(gate.offer(wide,1030),null);
 assert.equal(gate.pending,false);
 assert.equal(gate.offer(small,1100),null);
 assert.deepEqual(gate.offer(small,1220),small);
});
test('a new socket receives the current geometry once; unusable dimensions are ignored',()=>{
 const gate=new StableTerminalResize();
 gate.offer(wide,0);gate.offer(wide,120);gate.reset();
 assert.equal(gate.offer({rows:0,cols:0},140),null);
 assert.equal(gate.offer({rows:NaN,cols:80},160),null);
 assert.equal(gate.offer(wide,200),null);
 assert.deepEqual(gate.offer(wide,320),wide);
});
