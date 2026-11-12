/* Local Blockly UI. Buff fields are dropdowns; JSON is produced by block-model. */
((root, factory) => {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./block-model.js'));
  else root.HorseRaceBlockEditor = factory(root.HorseRaceBlockModel);
})(globalThis, Model => {
  'use strict';
  const targets = [['自己','0'],['随机另一匹马','1'],['全部马匹','2'],['除自己外全部','3'],['全场随机一匹','4'],['自己和另一匹','5'],['随机相邻赛道','6'],['两侧赛道','7']];
  const flagOptions = [['复活','live'],['获得图腾保护','negative_immunity'],['交换位置（目标选另一匹或相邻赛道）','track_exchange_location'],['随机传送','track_random_location']];
  const types = {hr_condition:'buff 条件',hr_unique:'本场唯一标识',hr_move:'额外位移',hr_teleport:'传送位置',hr_flag:'复活 / 图腾 / 交换 / 随机传送',hr_die:'死亡',hr_away:'下回合离场',hr_status:'持续 buff',hr_remove_buff:'移除 buff',hr_buff_time:'调整 buff 时长',hr_random:'随机分支',hr_branch:'随机结果',hr_delay:'延迟事件',hr_chain:'连锁事件',hr_nested_event:'子事件',hr_buff_ref:'附加 buff'};

  function register(B) {
    if (B.Blocks.hr_event) return;
    const num = (value = 0, min = -Infinity) => new B.FieldNumber(value, min, Infinity, 1);
    const text = (value = '') => new B.FieldTextInput(value);
    const MessageField = globalThis.FieldMultilineInput || B.FieldTextInput;
    if (globalThis.FieldMultilineInput) globalThis.FieldMultilineInput.showHint = false;
    const message = () => new MessageField('<0>发生了一件事', undefined, {maxLines:3,spellcheck:false});
    const buff = scope => new B.FieldDropdown(function () {
      const block = this.getSourceBlock(), current = this.getValue();
      const catalog = block?.workspace?.horseRaceCatalog || Model.catalog([]);
      const result = [['不选择', ''], ...catalog.buffs.filter(([, value]) => scope === 'condition' || value !== 'negative_immunity')];
      if (scope === 'remove') for (const name of catalog.names) if (!result.some(([,v]) => v === name)) result.push([`buff 名称 · ${name}`, name]);
      if (current && !result.some(([,value]) => value === current)) result.push([`已有 buff · ${current}`, current]);
      return result;
    });
    const effect = (block, colour = '#4c97ff') => { block.setPreviousStatement(true, 'Effect'); block.setNextStatement(true, 'Effect'); block.setColour(colour); };
    for (const nested of [false, true]) B.Blocks[nested ? 'hr_nested_event' : 'hr_event'] = {init() {
      this.appendDummyInput().appendField(nested ? '子事件' : '当事件发生').appendField(text(nested ? '子事件' : '新事件'), 'NAME');
      this.appendDummyInput().appendField('作用于').appendField(new B.FieldDropdown(targets), 'TARGET');
      this.appendDummyInput().appendField('消息').appendField(message(), 'DESCRIPTION');
      this.appendStatementInput('EFFECTS').setCheck('Effect').appendField('效果');
      this.setColour('#e6a317'); this.setInputsInline(false);
      if (nested) this.setPreviousStatement(true, 'Event');
      else { this.setDeletable(false); this.isDuplicatable = () => false; }
      this.setTooltip('把效果积木接到内部。文字中的 <0> 是发起马匹，<1> 是目标。每种效果只放一次。');
    }};
    B.Blocks.hr_condition = {init() { this.appendDummyInput().appendField('目标').appendField(new B.FieldDropdown([['必须拥有 buff','target_is_buff'],['不能拥有 buff','target_no_buff']]),'KIND').appendField(buff('condition'),'BUFF'); effect(this,'#5b80bd'); }};
    B.Blocks.hr_unique = {init() { this.appendDummyInput().appendField('本场仅触发一次，标识').appendField(text('唯一事件'),'KEY'); effect(this,'#5b80bd'); }};
    for (const [type, label, value] of [['hr_move','额外位移（负数后退）',3],['hr_teleport','传送到位置',5],['hr_buff_time','全部 buff 时长增减',1]]) B.Blocks[type] = {init() { this.appendDummyInput().appendField(label).appendField(num(value),'VALUE'); effect(this,type === 'hr_buff_time' ? '#56a56b' : '#4c97ff'); }};
    B.Blocks.hr_flag = {init() { this.appendDummyInput().appendField(new B.FieldDropdown(flagOptions),'KIND').appendField(new B.FieldCheckbox('TRUE'),'ENABLED').appendField('启用'); effect(this,'#9966cc'); }};
    B.Blocks.hr_die = {init() { this.appendDummyInput().appendField('死亡').appendField(new B.FieldCheckbox('TRUE'),'ENABLED').appendField('当回合生效').appendField(new B.FieldCheckbox('FALSE'),'NOW'); this.appendDummyInput().appendField('显示为').appendField(text('死亡'),'NAME'); effect(this,'#b45c76'); }};
    B.Blocks.hr_away = {init() { this.appendDummyInput().appendField('下回合离场').appendField(new B.FieldCheckbox('TRUE'),'ENABLED').appendField('显示为').appendField(text('离开'),'NAME'); effect(this,'#b45c76'); this.setTooltip('始终在下一回合生效，保持原赛马引擎的离场逻辑。'); }};
    B.Blocks.hr_remove_buff = {init() { this.appendDummyInput().appendField('移除 buff').appendField(buff('remove'),'BUFF'); effect(this,'#56a56b'); this.setTooltip('可叠放多块以移除多个 buff。图腾保护不能被普通移除。'); }};
    B.Blocks.hr_buff_ref = {init() { this.appendDummyInput().appendField('附加 buff').appendField(buff('other'),'BUFF'); this.setPreviousStatement(true,'Buff'); this.setNextStatement(true,'Buff'); this.setColour('#56a56b'); }};
    B.Blocks.hr_status = {init() {
      this.appendDummyInput().appendField('持续').appendField(num(1,0),'ROUNDS').appendField('回合，名称').appendField(text('持续状态'),'NAME');
      this.appendDummyInput().appendField('移动加成').appendField(num(0),'MIN').appendField('至').appendField(num(0),'MAX');
      this.appendDummyInput().appendField('停滞').appendField(new B.FieldCheckbox('FALSE'),'STOP').appendField('眩晕').appendField(new B.FieldCheckbox('FALSE'),'DIZZY').appendField('隐藏').appendField(new B.FieldCheckbox('FALSE'),'HIDE');
      this.appendStatementInput('BUFFS').setCheck('Buff').appendField('附加 buff（可选）');
      effect(this,'#56a56b'); this.setInputsInline(false); this.setTooltip('持续状态从下一回合生效。名称用于显示；附加 buff 用于条件判断。');
    }};
    B.Blocks.hr_random = {init() { this.appendDummyInput().appendField(new B.FieldDropdown([['立即随机抽取一个结果','random_event_once'],['持续状态中每回合随机','random_event']]),'KIND'); this.appendStatementInput('BRANCHES').setCheck('Branch').appendField('结果'); effect(this,'#df9728'); this.setTooltip('每回合随机需要同时设置持续 buff 的回合数。结果按权重比例抽取。'); }};
    B.Blocks.hr_branch = {init() { this.appendDummyInput().appendField('随机结果，权重').appendField(num(50,1),'WEIGHT'); this.appendStatementInput('EVENT').setCheck('Event').appendField('执行'); this.setPreviousStatement(true,'Branch'); this.setNextStatement(true,'Branch'); this.setColour('#df9728'); }};
    for (const delayed of [false,true]) B.Blocks[delayed ? 'hr_delay' : 'hr_chain'] = {init() {
      const line=this.appendDummyInput();
      if (delayed) line.appendField('延迟').appendField(num(2,2),'ROUNDS').appendField('回合'); else line.appendField('立即执行子事件');
      line.appendField('由').appendField(new B.FieldDropdown([['当前目标','target'],['原发起马匹','self']]),'WHO').appendField('发起');
      this.appendStatementInput('EVENT').setCheck('Event').appendField('执行'); effect(this,'#df9728');
    }};
    B.Blocks.hr_extra = {init() { this.appendDummyInput().appendField('高级字段（保留）').appendField(new B.FieldLabelSerializable(''),'KEYS'); effect(this,'#777d85'); this.setTooltip('未提供专用积木的字段原样保留。如需修改，可展开高级 JSON。删除此积木会删除这些字段。'); }};
  }

  const block = (type, fields, inputs) => ({kind:'block',type,...(fields ? {fields} : {}),...(inputs ? {inputs} : {})});
  const nested = () => ({block:{type:'hr_nested_event',fields:{NAME:'子事件',TARGET:'0',DESCRIPTION:'<0>触发效果'}}});
  const randomInputs = () => ({BRANCHES:{block:{type:'hr_branch',fields:{WEIGHT:50},inputs:{EVENT:nested()},next:{block:{type:'hr_branch',fields:{WEIGHT:50},inputs:{EVENT:nested()}}}}}});
  const toolbox = {kind:'categoryToolbox',contents:[
    {kind:'category',name:'位移',colour:'#4c97ff',contents:[block('hr_move'),block('hr_teleport'),block('hr_flag',{KIND:'track_exchange_location',ENABLED:true}),block('hr_flag',{KIND:'track_random_location',ENABLED:true})]},
    {kind:'category',name:'buff',colour:'#56a56b',contents:[block('hr_status'),block('hr_status',{ROUNDS:1,NAME:'停留',STOP:true}),block('hr_buff_ref'),block('hr_remove_buff'),block('hr_buff_time'),block('hr_flag',{KIND:'negative_immunity',ENABLED:true})]},
    {kind:'category',name:'条件',colour:'#5b80bd',contents:[block('hr_condition'),block('hr_unique')]},
    {kind:'category',name:'死亡 / 离场',colour:'#b45c76',contents:[block('hr_die'),block('hr_away'),block('hr_flag',{KIND:'live',ENABLED:true})]},
    {kind:'category',name:'随机 / 延迟',colour:'#df9728',contents:[block('hr_random',undefined,randomInputs()),block('hr_branch',undefined,{EVENT:nested()}),block('hr_delay',undefined,{EVENT:nested()}),block('hr_chain',undefined,{EVENT:nested()}),block('hr_nested_event')]},
  ]};

  class Editor {
    static register = register;
    static types = types;
    constructor({container, onChange}) {
      const B = globalThis.Blockly;
      if (!B || !Model) throw new Error('积木编辑器加载失败，请检查本地资源');
      register(B); this.B=B; this.onChange=onChange;
      this.workspace=B.inject(container,{toolbox,renderer:'zelos',media:new URL('./vendor/blockly/media/',document.baseURI).href,trashcan:true,sounds:false,maxBlocks:1000,disable:false,grid:{spacing:24,length:2,colour:'#dce3df',snap:true},zoom:{controls:true,wheel:true,startScale:.85,minScale:.3,maxScale:1.5,scaleSpeed:1.1},move:{scrollbars:true,drag:true,wheel:true}});
      this.workspace.horseRaceCatalog=Model.catalog([]);
      this.workspace.addChangeListener(event => {
        if (event.isUiEvent || this.loading) return;
        const current=JSON.stringify(this.getState()); if (current===this.last) return; this.last=current;
        try { this.onChange?.(this.read(),null); } catch(error) { this.onChange?.(null,error); }
      });
      this.observer=new ResizeObserver(()=>this.resize()); this.observer.observe(container);
    }
    setCatalog(catalog) { this.workspace.horseRaceCatalog=catalog; }
    getState() { return this.B.serialization.workspaces.save(this.workspace); }
    read() { return Model.toEvent(this.getState()); }
    load(event) { this.loadState(Model.fromEvent(event)); }
    loadState(state) {
      if (JSON.stringify(state).length>1024*1024) throw new Error('积木草稿过大');
      this.loading=true;
      try { this.B.serialization.workspaces.load(state,this.workspace); this.workspace.clearUndo(); this.last=JSON.stringify(this.getState()); }
      finally { this.loading=false; }
      this.resize();
    }
    resize() { this.B.svgResize(this.workspace); }
    fit() { this.resize(); this.workspace.zoomToFit(); }
    undo(redo=false) { this.workspace.undo(redo); }
    add(type) {
      if (!types[type]) return;
      let node={type};
      if (type==='hr_random') node.inputs=randomInputs();
      if (['hr_branch','hr_delay','hr_chain'].includes(type)) node.inputs={EVENT:nested()};
      const created=this.B.serialization.blocks.append(node,this.workspace);
      const selected=this.B.common.getSelected(), root=this.workspace.getTopBlocks(false).find(b=>b.type==='hr_event');
      const expected=created.previousConnection?.getCheck()?.[0];
      let destination;
      if (selected?.workspace===this.workspace) {
        const matching=selected.inputList.find(input=>input.connection?.getCheck()?.includes(expected));
        if (matching) {
          let candidate=matching.connection;
          while (candidate.targetBlock()?.nextConnection) candidate=candidate.targetBlock().nextConnection;
          if (!candidate.isConnected()) destination=candidate;
        }
        if (!destination && selected.nextConnection?.getCheck()?.includes(expected) && !selected.nextConnection.isConnected()) destination=selected.nextConnection;
      }
      if (!destination && expected==='Effect' && root) {
        destination=root.getInput('EFFECTS').connection;
        while (destination.targetBlock()?.nextConnection) destination=destination.targetBlock().nextConnection;
      }
      if (destination && !destination.isConnected()) destination.connect(created.previousConnection);
      else created.moveBy(70,70);
      created.select();
    }
  }
  return Editor;
});
