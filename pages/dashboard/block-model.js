/* JSON <-> Blockly state only. Never evaluates or generates executable code. */
((root, factory) => {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.HorseRaceBlockModel = api;
})(globalThis, () => {
  'use strict';
  const copy = x => JSON.parse(JSON.stringify(x));
  const own = (x, k) => Object.prototype.hasOwnProperty.call(x, k);
  const builtins = [['死亡', 'die'], ['离场', 'away'], ['停滞', 'locate_lock'], ['眩晕', 'vertigo'], ['隐藏', 'hiding'], ['图腾保护', 'negative_immunity']];
  const statusKeys = ['rounds', 'name', 'move_min', 'move_max', 'locate_lock', 'vertigo', 'hiding', 'other_buff'];
  const numericTypes = {move: 'hr_move', track_to_location: 'hr_teleport', buff_time_add: 'hr_buff_time'};
  const flags = ['live', 'negative_immunity', 'track_exchange_location', 'track_random_location'];
  const state = (type, fields = {}, inputs = {}, data) => ({type, fields, inputs: Object.fromEntries(Object.entries(inputs).filter(([,value]) => value)), ...(data ? {data: JSON.stringify(data)} : {})});
  const chain = blocks => {
    for (let i = 0; i < blocks.length - 1; i++) blocks[i].next = {block: blocks[i + 1]};
    return blocks.length ? {block: blocks[0]} : undefined;
  };
  const meta = block => {
    try { return JSON.parse(block.data || '{}'); } catch { throw new Error('积木附加数据无效'); }
  };

  function catalog(packs) {
    const values = new Map(builtins.map(([label, value]) => [value, label]));
    const names = new Set();
    const visit = (value, depth = 0) => {
      if (!value || typeof value !== 'object' || depth > 24) return;
      if (!Array.isArray(value)) {
        for (const key of ['target_is_buff', 'target_no_buff', 'other_buff', 'del_buff']) {
          const list = Array.isArray(value[key]) ? value[key] : [value[key]];
          for (const item of list) if (typeof item === 'string' && item && !values.has(item)) values.set(item, item);
        }
        for (const key of ['name', 'die_name', 'away_name']) if (typeof value[key] === 'string' && value[key]) names.add(value[key]);
      }
      Object.values(value).forEach(item => visit(item, depth + 1));
    };
    visit(packs);
    return {buffs: [...values].map(([value, label]) => [label === value ? `自定义 buff · ${value}` : `${label} (${value})`, value]), names: [...names]};
  }

  function eventBlock(event, nested = false, depth = 0) {
    if (depth > 20 || !event || typeof event !== 'object' || Array.isArray(event)) throw new Error('事件嵌套无效或超过 20 层');
    if (!Number.isInteger(event.target) || event.target < 0 || event.target > 7) throw new Error('事件 target 必须是 0~7 的整数，请在高级 JSON 中修正');
    for (const key of ['event_name','describe']) if (own(event,key) && typeof event[key] !== 'string') throw new Error(`${key} 必须是文字，请在高级 JSON 中修正`);
    const rest = copy(event), effects = [];
    const take = key => { const value = rest[key]; delete rest[key]; return value; };
    const fields = {NAME: event.event_name ?? '', DESCRIPTION: event.describe ?? '', TARGET: String(event.target)};
    for (const key of ['event_name', 'describe', 'target']) take(key);
    for (const key of ['target_is_buff', 'target_no_buff']) if (typeof rest[key] === 'string') {
      const value = take(key);
      if (value) effects.push(state('hr_condition', {KIND: key, BUFF: value}));
    }
    if (typeof rest.race_only === 'string') effects.push(state('hr_unique', {KEY: take('race_only')}));
    for (const [key, type] of Object.entries(numericTypes)) if (Number.isInteger(rest[key])) effects.push(state(type, {VALUE: take(key)}));
    for (const key of flags) if (rest[key] === 1 || rest[key] === 0) effects.push(state('hr_flag', {KIND: key, ENABLED: take(key) === 1 ? 'TRUE' : 'FALSE'}));
    for (const key of ['die', 'away']) if (rest[key] === 1 || rest[key] === 0) {
      const f = {ENABLED: take(key) === 1 ? 'TRUE' : 'FALSE', NAME: event[`${key}_name`] ?? (key === 'die' ? '死亡' : '离开')};
      const present = [];
      if (own(rest, `${key}_name`)) { present.push(`${key}_name`); take(`${key}_name`); }
      if (key === 'die' && (rest.immediate === 0 || rest.immediate === 1)) { present.push('immediate'); f.NOW = take('immediate') === 1 ? 'TRUE' : 'FALSE'; }
      effects.push(state(key === 'die' ? 'hr_die' : 'hr_away', f, {}, {present}));
    }
    if (Array.isArray(rest.del_buff) && rest.del_buff.every(v => typeof v === 'string') || typeof rest.del_buff === 'string') {
      const raw = take('del_buff'), values = Array.isArray(raw) ? raw : [raw];
      if (values.length) for (const value of values) effects.push(state('hr_remove_buff', {BUFF: value}, {}, {asString: typeof raw === 'string'}));
    }
    if (statusKeys.some(key => own(rest, key))) {
      const valid = statusKeys.every(key => !own(rest, key) || (key === 'name' ? typeof rest[key] === 'string' : key === 'other_buff' ? Array.isArray(rest[key]) && rest[key].every(v => typeof v === 'string') : Number.isInteger(rest[key]))) && ['locate_lock', 'vertigo', 'hiding'].every(key => !own(rest, key) || rest[key] === 0 || rest[key] === 1);
      if (valid) {
        const present = statusKeys.filter(key => own(rest, key));
        const f = {ROUNDS: rest.rounds ?? 0, NAME: rest.name ?? '', MIN: rest.move_min ?? 0, MAX: rest.move_max ?? 0, STOP: rest.locate_lock === 1 ? 'TRUE' : 'FALSE', DIZZY: rest.vertigo === 1 ? 'TRUE' : 'FALSE', HIDE: rest.hiding === 1 ? 'TRUE' : 'FALSE'};
        const extras = (rest.other_buff || []).map(value => state('hr_buff_ref', {BUFF: value}));
        statusKeys.forEach(take);
        effects.push(state('hr_status', f, {BUFFS: chain(extras)}, {present}));
      }
    }
    for (const key of ['random_event_once', 'random_event']) if (Array.isArray(rest[key]) && rest[key].length) {
      let previous = -1;
      const branches = rest[key].map(pair => {
        if (!Array.isArray(pair) || pair.length !== 2 || !Number.isInteger(pair[0]) || pair[0] <= previous) throw new Error('随机分支阈值无效，请在高级 JSON 中修正');
        const weight = pair[0] - previous; previous = pair[0];
        return state('hr_branch', {WEIGHT: weight}, {EVENT: {block: eventBlock(pair[1], true, depth + 1)}});
      });
      take(key); effects.push(state('hr_random', {KIND: key}, {BRANCHES: chain(branches)}));
    }
    for (const key of ['random_event_once','random_event','delay_event','delay_event_self','another_event','another_event_self','add_horse','replace_horse']) {
      if (rest[key] && typeof rest[key] === 'object' && !Object.keys(rest[key]).length) take(key);
    }
    for (const key of ['delay_event', 'delay_event_self', 'another_event', 'another_event_self']) if (rest[key] && Object.keys(rest[key]).length) {
      const delayed = key.startsWith('delay_'), value = rest[key];
      if (delayed && (!Array.isArray(value) || value.length !== 2 || !Number.isInteger(value[0]) || value[0] < 2)) throw new Error('延迟事件至少需要 2 回合');
      take(key);
      effects.push(state(delayed ? 'hr_delay' : 'hr_chain', {WHO: key.endsWith('_self') ? 'self' : 'target', ...(delayed ? {ROUNDS:value[0]} : {})}, {EVENT: {block: eventBlock(delayed ? value[1] : value, true, depth + 1)}}));
    }
    if (Object.keys(rest).length) effects.push(state('hr_extra', {KEYS:Object.keys(rest).join(', ')}, {}, {value: rest}));
    return state(nested ? 'hr_nested_event' : 'hr_event', fields, {EFFECTS: chain(effects)}, {namePresent: own(event, 'event_name'), descriptionPresent: own(event, 'describe')});
  }

  function fromEvent(event) {
    const root = eventBlock(event); root.x = 35; root.y = 30;
    return {blocks: {languageVersion: 0, blocks: [root]}};
  }

  function toEvent(workspace) {
    let budget = 1000;
    const roots = workspace?.blocks?.blocks || [];
    if (roots.length !== 1 || roots[0].type !== 'hr_event') throw new Error('请把所有积木接到唯一的事件积木内；游离积木不会被保存');
    const check = (block, depth) => {
      if (--budget < 0 || depth > 24) throw new Error('积木过多或嵌套过深');
      if (block.disabled || block.disabledReasons?.length) throw new Error('请删除或重新启用已禁用的积木');
    };
    const stack = (block, callback, depth) => {
      while (block) { check(block, depth); callback(block); block = block.next?.block; }
    };
    const input = (block, name) => block.inputs?.[name]?.block;
    const number = (block, name) => {
      const value = Number(block.fields?.[name]);
      if (!Number.isSafeInteger(value)) throw new Error('积木数值必须是安全范围内的整数');
      return value;
    };
    const text = (block, name) => String(block.fields?.[name] ?? '');
    const yes = (block, name) => block.fields?.[name] === true || block.fields?.[name] === 'TRUE';
    function readEvent(block, depth = 0) {
      if (!block || !['hr_event', 'hr_nested_event'].includes(block.type)) throw new Error('请在事件槽中放入子事件积木');
      check(block, depth);
      if (block.next?.block) throw new Error('子事件槽只能放入一个子事件');
      const data = meta(block), target = number(block, 'TARGET');
      if (target < 0 || target > 7) throw new Error('作用目标无效');
      let out = {target};
      if (text(block, 'NAME') || data.namePresent) out.event_name = text(block, 'NAME');
      if (text(block, 'DESCRIPTION') || data.descriptionPresent) out.describe = text(block, 'DESCRIPTION');
      const removals = []; let removalString = false;
      const add = part => {
        for (const key of Object.keys(part)) if (own(out, key)) throw new Error(`同一事件重复设置 ${key}，请合并为一个效果积木`);
        out = {...out, ...part};
      };
      stack(input(block, 'EFFECTS'), effect => {
        const f = effect.fields || {}, info = meta(effect);
        if (effect.type === 'hr_condition') {
          if (!['target_is_buff', 'target_no_buff'].includes(f.KIND)) throw new Error('buff 条件无效');
          if (f.BUFF) add({[f.KIND]: text(effect, 'BUFF')});
        } else if (effect.type === 'hr_unique') add({race_only: text(effect, 'KEY')});
        else if (Object.values(numericTypes).includes(effect.type)) add({[Object.keys(numericTypes).find(key => numericTypes[key] === effect.type)]: number(effect, 'VALUE')});
        else if (effect.type === 'hr_flag') {
          if (!flags.includes(f.KIND)) throw new Error('效果类型无效');
          add({[f.KIND]: yes(effect, 'ENABLED') ? 1 : 0});
        } else if (effect.type === 'hr_die' || effect.type === 'hr_away') {
          const key = effect.type === 'hr_die' ? 'die' : 'away', part = {[key]: yes(effect, 'ENABLED') ? 1 : 0};
          if (text(effect, 'NAME') !== (key === 'die' ? '死亡' : '离开') || info.present?.includes(`${key}_name`)) part[`${key}_name`] = text(effect, 'NAME');
          if (key === 'die' && (yes(effect, 'NOW') || info.present?.includes('immediate'))) part.immediate = yes(effect, 'NOW') ? 1 : 0;
          add(part);
        } else if (effect.type === 'hr_remove_buff') {
          if (f.BUFF) removals.push(text(effect, 'BUFF'));
          removalString ||= info.asString === true;
        } else if (effect.type === 'hr_status') {
          const part = {}, values = {rounds: number(effect, 'ROUNDS'), name: text(effect, 'NAME'), move_min: number(effect, 'MIN'), move_max: number(effect, 'MAX'), locate_lock: yes(effect, 'STOP') ? 1 : 0, vertigo: yes(effect, 'DIZZY') ? 1 : 0, hiding: yes(effect, 'HIDE') ? 1 : 0};
          for (const [key, value] of Object.entries(values)) if (value || info.present?.includes(key)) part[key] = value;
          const refs = [];
          stack(input(effect, 'BUFFS'), ref => { if (ref.type !== 'hr_buff_ref') throw new Error('附加 buff 槽只能放入 buff 积木'); if (ref.fields?.BUFF) refs.push(text(ref, 'BUFF')); }, depth + 1);
          if (refs.length || info.present?.includes('other_buff')) part.other_buff = refs;
          add(part);
        } else if (effect.type === 'hr_random') {
          if (!['random_event_once', 'random_event'].includes(f.KIND)) throw new Error('随机模式无效');
          const rows = []; let threshold = -1;
          stack(input(effect, 'BRANCHES'), branch => {
            if (branch.type !== 'hr_branch') throw new Error('随机槽只能放入随机结果积木');
            const weight = number(branch, 'WEIGHT'); if (weight < 1) throw new Error('随机结果权重至少为 1');
            threshold += weight; if (!Number.isSafeInteger(threshold)) throw new Error('随机权重总和过大');
            rows.push([threshold, readEvent(input(branch, 'EVENT'), depth + 1)]);
          }, depth + 1);
          if (!rows.length) throw new Error('随机积木至少需要一个结果');
          add({[f.KIND]: rows});
        } else if (effect.type === 'hr_delay' || effect.type === 'hr_chain') {
          if (!['self', 'target'].includes(f.WHO)) throw new Error('子事件发起者无效');
          const child = readEvent(input(effect, 'EVENT'), depth + 1), delayed = effect.type === 'hr_delay';
          const key = (delayed ? 'delay_event' : 'another_event') + (f.WHO === 'self' ? '_self' : '');
          if (delayed) { const turns = number(effect, 'ROUNDS'); if (turns < 2) throw new Error('延迟事件至少为 2 回合'); add({[key]: [turns, child]}); }
          else add({[key]: child});
        } else if (effect.type === 'hr_extra') {
          if (!info.value || typeof info.value !== 'object' || Array.isArray(info.value)) throw new Error('高级字段无效');
          add(copy(info.value));
        } else throw new Error('该积木不能放入事件效果槽');
      }, depth + 1);
      if (removals.length) add({del_buff: removalString && removals.length === 1 ? removals[0] : removals});
      return out;
    }
    return readEvent(roots[0]);
  }
  return {fromEvent, toEvent, catalog, builtins};
});
