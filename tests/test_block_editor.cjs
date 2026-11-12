const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const B = require('../page/dashboard/vendor/blockly/blockly_compressed.js');
const fields = {Blockly:B};
vm.runInNewContext(fs.readFileSync(path.join(root,'page/dashboard/vendor/blockly/multiline/index.js'),'utf8'),fields);
globalThis.FieldMultilineInput=fields.FieldMultilineInput;
const Model = require('../page/dashboard/block-model.js');
const Editor = require('../page/dashboard/block-editor.js');
Editor.register(B);

function workspace(event) {
  const w = new B.Workspace();
  w.horseRaceCatalog = Model.catalog([event]);
  B.serialization.workspaces.load(Model.fromEvent(event), w);
  return w;
}
const read = w => Model.toEvent(B.serialization.workspaces.save(w));
function normalize(value) {
  if (Array.isArray(value)) return value.map(normalize);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).filter(([k,v]) => !(['target_is_buff','target_no_buff'].includes(k) && v === '')).map(([k,v]) => [k,normalize(v)]));
}

test('every bundled event survives real Blockly serialization and JSON roundtrip', () => {
  let count=0;
  for (const filename of fs.readdirSync(path.join(root,'events')).filter(name=>name.endsWith('.json'))) {
    const pack=JSON.parse(fs.readFileSync(path.join(root,'events',filename),'utf8').replace(/^\uFEFF/,''));
    for (const event of pack) {
      const w=workspace(event);
      try { assert.deepEqual(normalize(read(w)),normalize(event),filename+' / '+event.event_name); count++; }
      finally { w.dispose(); }
    }
  }
  assert.ok(count>=107);
});

test('empty events remain editable and messages keep line breaks', () => {
  const w=workspace({target:0,describe:'第一行\n第二行'});
  assert.equal(w.getTopBlocks()[0].isDuplicatable(),false);
  assert.ok(w.getTopBlocks()[0].getField('DESCRIPTION') instanceof fields.FieldMultilineInput);
  assert.deepEqual(read(w),{target:0,describe:'第一行\n第二行'});
  w.getTopBlocks()[0].setFieldValue('修改后的名称','NAME');
  assert.equal(read(w).event_name,'修改后的名称'); w.dispose();
});

test('buff conditions and removals use dropdowns and preserve custom buff values', () => {
  const w=workspace({target:1,target_is_buff:'自定义护盾',target_no_buff:'die',del_buff:['hiding','自定义护盾']});
  for (const block of w.getAllBlocks()) if (['hr_condition','hr_remove_buff'].includes(block.type)) assert.ok(block.getField('BUFF') instanceof B.FieldDropdown);
  const condition=w.getAllBlocks().find(b=>b.type==='hr_condition' && b.getFieldValue('KIND')==='target_is_buff');
  condition.setFieldValue('negative_immunity','BUFF');
  assert.equal(read(w).target_is_buff,'negative_immunity');
  condition.setFieldValue('','BUFF');
  assert.equal(read(w).target_is_buff,undefined);
  assert.deepEqual(read(w).del_buff,['hiding','自定义护盾']); w.dispose();
});

test('random weights, nested delay and buff timing compile to the existing event format', () => {
  const event={target:0,random_event_once:[[49,{target:0,move:3}],[99,{target:0,rounds:1,locate_lock:1}]],delay_event_self:[2,{target:0,away:1,immediate:1}]};
  const w=workspace(event);
  const branches=w.getAllBlocks().filter(b=>b.type==='hr_branch');
  branches[0].setFieldValue(30,'WEIGHT'); branches[1].setFieldValue(70,'WEIGHT');
  const result=read(w);
  assert.deepEqual(result.random_event_once.map(pair=>pair[0]),[29,99]);
  assert.deepEqual(result.delay_event_self,event.delay_event_self); w.dispose();
});

test('advanced fields and unsupported values are retained explicitly', () => {
  const event={target:0,move:2,race_only:123,other_buff:'legacy',add_horse:{horsename:'新马',owner:'测试者'},future_field:{enabled:true}};
  const w=workspace(event);
  assert.ok(w.getAllBlocks().some(b=>b.type==='hr_extra'));
  assert.deepEqual(read(w),event);
  w.getAllBlocks().find(b=>b.type==='hr_move').setFieldValue(-3,'VALUE');
  assert.equal(read(w).move,-3); assert.deepEqual(read(w).future_field,{enabled:true}); w.dispose();
});

test('orphan, duplicate and incomplete stacks fail instead of silently dropping blocks', () => {
  const w=workspace({target:0,move:3});
  const orphan=w.newBlock('hr_move');
  assert.throws(()=>read(w),/游离积木/);
  const first=w.getAllBlocks().find(b=>b.type==='hr_move' && b!==orphan);
  first.nextConnection.connect(orphan.previousConnection);
  assert.throws(()=>read(w),/重复设置 move/);
  orphan.dispose();
  const delay=w.newBlock('hr_delay'); first.nextConnection.connect(delay.previousConnection);
  assert.throws(()=>read(w),/子事件积木/); w.dispose();
});

test('empty legacy containers do not prevent adding new visual effects', () => {
  const w=workspace({target:0,random_event_once:[],del_buff:[],delay_event:[],another_event:{},add_horse:{},future_field:null});
  const randomState=Model.fromEvent({target:0,random_event_once:[[0,{target:0,move:3}]]}).blocks.blocks[0].inputs.EFFECTS.block;
  const added=B.serialization.blocks.append(randomState,w);
  const extra=w.getAllBlocks().find(b=>b.type==='hr_extra');
  extra.nextConnection.connect(added.previousConnection);
  const result=read(w);
  assert.deepEqual(result.random_event_once,[[0,{target:0,move:3}]]);
  assert.equal(result.future_field,null); w.dispose();
});

test('serialized Blockly drafts remain reusable and editable', () => {
  const w=workspace({target:0,move:3,die:0});
  const data=B.serialization.workspaces.save(w), restored=new B.Workspace();
  restored.horseRaceCatalog=w.horseRaceCatalog; B.serialization.workspaces.load(data,restored);
  assert.deepEqual(read(restored),read(w));
  const move=restored.getAllBlocks().find(b=>b.type==='hr_move'); move.setFieldValue(8,'VALUE');
  assert.equal(read(restored).move,8);
  w.dispose(); restored.dispose();
});
