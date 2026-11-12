(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const clone = value => JSON.parse(JSON.stringify(value));
  const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const newEvent = () => ({event_name:'新事件', describe:'<0>遇到了一件新鲜事！', target:0});
  let pack = [newEvent()], selected = 0, dirty = false, jsonDirty = false;
  let online = false, library = [], test = null, frameIndex = 0, playback = null;
  let canDeleteCustom=false, deletingPack=false, loadedPackId=null, aiPanel=null;
  const draftKey = 'astrbot-horserace-event-studio-v1';
  const targets = ['自己','随机另一匹马','全场马匹','除自己外全部','全场随机一匹','自己和另一匹','随机相邻赛道','两侧赛道'];
  let blockEditor = null, restoredBlocks = null;
  const blockCatalog = () => window.HorseRaceBlockModel.catalog([pack, ...library.map(item => item.pack)]);

  function notice(message, error = false) {
    $('notice').textContent = String(message);
    $('notice').className = 'notice' + (error ? ' error' : '');
    $('notice').hidden = !message;
  }

  async function confirmAction(title, message) {
    const dialog = $('confirmDialog');
    $('confirmTitle').textContent = title;
    $('confirmText').textContent = message;
    return new Promise(resolve => {
      dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), {once:true});
      dialog.returnValue = 'cancel';
      dialog.showModal();
    });
  }

  function saveDraft() {
    try { localStorage.setItem(draftKey, JSON.stringify({pack, selected, filename:$('filename').value, blocks:blockEditor?.getState()})); }
    catch { $('draftState').textContent = '浏览器草稿不可用'; }
  }

  function changed() {
    dirty = true;
    $('draftState').textContent = '有未保存修改';
    $('validation').className = 'validation';
    $('validation').textContent = '○ 内容已变更，请重新校验';
    saveDraft();
  }

  async function api(action, body) {
    if (!online) throw new Error('尚未连接 AstrBot。可先编辑、导入或导出；请从机器人插件页面打开以使用真实引擎和保存。');
    let result;
    if (window.HorseRaceDev) {
      const response = await fetch('/dev-api/' + action, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
      result = await response.json();
    } else {
      const bridge = window.AstrBotPluginPage;
      result = body === undefined ? await bridge.apiGet('dashboard/' + action) : await bridge.apiPost('dashboard/' + action, body);
    }
    // Bridge returns the endpoint response body; tolerate host response wrappers.
    if (result?.data?.status) result = result.data;
    if (result?.status === 'error') throw new Error(result.message || '请求失败');
    return result?.status === 'ok' ? result.data : result;
  }

  function renderList() {
    $('eventCount').textContent = pack.length;
    $('eventList').replaceChildren();
    const query = $('eventSearch').value.trim().toLowerCase();
    pack.forEach((event, index) => {
      if (query && !String(event.event_name || '').toLowerCase().includes(query)) return;
      const button = document.createElement('button');
      button.className = 'event-card' + (index === selected ? ' active' : '');
      button.innerHTML = `<span class="event-num">${String(index + 1).padStart(2,'0')}</span><span><strong>${esc(event.event_name || '未命名事件')}</strong><small>${esc(targets[event.target] || '待设置目标')}</small></span>`;
      button.addEventListener('click', () => safe(() => { applyPending(); selected = index; renderEditor(); saveDraft(); }));
      $('eventList').append(button);
    });
  }

  function syncSource() {
    $('eventJson').value = JSON.stringify(pack[selected], null, 2);
    jsonDirty = false;
  }

  function applyPending() {
    if (jsonDirty) {
      const event = JSON.parse($('eventJson').value);
      basicValidate(event);
      pack[selected] = event; jsonDirty = false;
      blockEditor.setCatalog(blockCatalog()); blockEditor.load(event); changed();
    } else pack[selected] = blockEditor.read();
  }

  function renderEditor() {
    renderList();
    $('editingTitle').textContent = pack[selected]?.event_name || '编辑事件';
    blockEditor.setCatalog(blockCatalog()); blockEditor.load(pack[selected]);
    syncSource();
  }

  function basicValidate(value, depth = 0) {
    if (!value || typeof value !== 'object' || Array.isArray(value) || depth > 20) throw new Error('事件必须是对象，嵌套不能超过 20 层');
    if (!Number.isInteger(value.target) || value.target < 0 || value.target > 7) throw new Error('每条事件的 target 必须是 0~7 的整数');
    for (const key of ['move','rounds','move_min','move_max','buff_time_add','track_to_location']) if (value[key] !== undefined && !Number.isInteger(value[key])) throw new Error(key + ' 必须是整数');
    for (const key of ['random_event_once','random_event']) if (value[key] !== undefined) {
      if (!Array.isArray(value[key])) throw new Error(key + ' 必须是数组');
      let last = -1;
      value[key].forEach(pair => { if (!Array.isArray(pair) || pair.length !== 2 || !Number.isInteger(pair[0]) || pair[0] <= last) throw new Error('随机分支阈值必须为递增非负整数'); last = pair[0]; basicValidate(pair[1], depth + 1); });
    }
    for (const key of ['another_event','another_event_self']) if (value[key] && Object.keys(value[key]).length) basicValidate(value[key], depth + 1);
    for (const key of ['delay_event','delay_event_self']) if (value[key]?.length) { if (value[key].length !== 2 || !Number.isInteger(value[key][0]) || value[key][0] < 2) throw new Error('延迟事件至少需要 2 回合'); basicValidate(value[key][1], depth + 1); }
  }

  async function validate() {
    const pending = jsonDirty;
    applyPending();
    if (pending) renderEditor();
    if (!pack.length || pack.length > 128) throw new Error('事件包需要包含 1~128 条事件');
    pack.forEach((event,index) => { try { basicValidate(event); } catch (error) { throw new Error(`第 ${index+1} 条：${error.message}`); } });
    if (online) await api('validate', {pack});
    $('validation').textContent = `✓ ${pack.length} 条事件${online ? '通过引擎校验' : '通过本地结构检查'}`;
    $('validation').className = 'validation ok';
    return true;
  }

  function download(value, filename) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2) + '\n'], {type:'application/json'}));
    const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 3000);
  }

  async function safe(action) {
    try { await action(); } catch (error) { notice(error.message || error, true); $('validation').className = 'validation bad'; $('validation').textContent = '✕ ' + (error.message || error); }
  }

  async function loadLibrary() {
    const previous=$('library').value;
    const data = await api('packs'); library = data.packs || [];
    $('library').replaceChildren(new Option('选择事件包…', ''));
    library.forEach(item => $('library').append(new Option(`${item.source === 'builtin' ? '内置' : '自定义'} · ${item.filename}${item.error ? '（无法读取）' : ''}`, item.id)));
    if (library.some(item=>item.id===previous)) $('library').value=previous;
    updateDeleteButton();
    blockEditor?.setCatalog(blockCatalog());
    if (data.errors?.length) notice('部分事件包未读取：\n' + data.errors.join('\n'), true);
  }

  const selectedPack = () => library.find(item=>item.id===$('library').value);
  function updateDeleteButton() {
    const item=selectedPack();
    $('deletePack').disabled=deletingPack || !online || !canDeleteCustom || item?.source!=='custom';
    $('deletePack').title=item?.source==='builtin' ? '内置事件包不能删除' : '仅可删除选中的自定义事件包';
  }
  function checkCandidate(value) {
    if (!Array.isArray(value) || !value.length || value.length>128) throw new Error('生成内容必须是事件包数组');
    value.forEach(event=>{ basicValidate(event); window.HorseRaceBlockModel.fromEvent(event); });
  }
  async function applyAI(value,filename,save) {
    checkCandidate(value);
    if ((dirty || jsonDirty) && !await confirmAction('导入 AI 事件包？',`将用 ${value.length} 条 AI 事件替换当前草稿，请先导出需要保留的内容。`)) return;
    if (save) {
      const body={pack:value,filename}; let result=await api('save',body);
      if (result.conflict) {
        if (!await confirmAction('覆盖已有自定义包？',`将覆盖 ${filename} 并重载事件。`)) return;
        await api('save',{...body,overwrite:true});
      }
    }
    pack=clone(value); selected=0; $('filename').value=filename || 'AI生成事件.json';
    loadedPackId=save ? 'custom/'+filename : null;
    renderEditor(); dirty=!save; $('draftState').textContent=save ? '已保存到机器人' : 'AI 草稿待保存'; saveDraft();
    if (save) { await loadLibrary(); $('library').value=loadedPackId; updateDeleteButton(); }
    notice(save ? 'AI 事件包已导入并保存、重载。' : 'AI 事件包已导入编辑器，可检查积木后保存。');
  }

  function showTab(tab) {
    $('editorPanel').hidden = tab !== 'editor'; $('testPanel').hidden = tab !== 'test';
    document.querySelectorAll('[data-tab]').forEach(button => button.classList.toggle('active', button.dataset.tab === tab));
    if (tab === 'test') refreshActors();
    else requestAnimationFrame(() => blockEditor?.resize());
    if (tab !== 'test') stopPlayback();
  }

  function getPlayers() {
    return $('players').value.split('\n').filter(s => s.trim()).map((line,index) => {
      const parts = line.split('|');
      return {name:parts[0].trim(), location:parts.length > 1 ? Number(parts[1]) : 0, protected:$('protectedActor').checked && index === Number($('actor').value)};
    });
  }

  function refreshActors() {
    const previous = $('actor').value;
    $('actor').replaceChildren();
    getPlayers().forEach((player,index) => $('actor').append(new Option(player.name || `马匹 ${index+1}`, index)));
    if ([...$('actor').options].some(o => o.value === previous)) $('actor').value = previous;
  }

  function stopPlayback() { if (playback) clearInterval(playback); playback = null; $('playFrames').textContent = '播放'; }

  function renderFrame(index) {
    if (!test) return;
    frameIndex = Math.min(Math.max(0,index), test.frames.length - 1);
    const frame = test.frames[frameIndex];
    $('frameSlider').value = frameIndex; $('frameLabel').textContent = `第 ${frame.round} 回合`;
    $('roundLog').textContent = frame.log;
    $('tracks').replaceChildren();
    frame.horses.forEach(horse => {
      const row = document.createElement('div'); row.className = 'lane' + (horse.dead || horse.away ? ' dead' : '');
      const states = [horse.protected ? '图腾保护' : '', horse.dead ? '死亡' : '', horse.away ? '离场' : '', ...horse.buffs].filter(Boolean);
      const percent = Math.max(2, Math.min(96, horse.position / test.length * 96));
      row.innerHTML = `<div class="lane-title">${esc(horse.name)}<small>${esc(states.join(' · ') || '正常')}</small></div><div class="track"><div class="track-progress" style="width:${percent}%"></div><span class="horse-icon" style="left:${percent}%">♞</span></div><div class="lane-score">${esc(horse.position)}<small> / ${test.length}</small></div>`;
      $('tracks').append(row);
    });
  }

  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => safe(() => { applyPending(); showTab(button.dataset.tab); })));
  document.querySelector('.brand').addEventListener('click', e => { e.preventDefault(); safe(() => { applyPending(); showTab('editor'); }); });
  $('eventSearch').addEventListener('input', renderList);
  $('filename').addEventListener('input', changed);
  $('eventJson').addEventListener('input', () => { jsonDirty = true; $('validation').textContent = '○ JSON 尚未应用'; });
  $('applyJson').addEventListener('click', () => safe(() => { applyPending(); renderEditor(); notice('JSON 已应用到当前事件。'); }));
  $('formatJson').addEventListener('click', () => safe(() => { $('eventJson').value = JSON.stringify(JSON.parse($('eventJson').value),null,2); jsonDirty = true; }));
  $('newEvent').addEventListener('click', () => safe(() => { applyPending(); if (pack.length >= 128) throw new Error('最多 128 条事件'); pack.push(newEvent()); selected = pack.length - 1; renderEditor(); changed(); }));
  $('duplicateEvent').addEventListener('click', () => safe(() => { applyPending(); if (pack.length >= 128) throw new Error('最多 128 条事件'); const copy = clone(pack[selected]); copy.event_name = (copy.event_name || '事件') + ' · 副本'; pack.splice(selected+1,0,copy); selected++; renderEditor(); changed(); }));
  $('deleteEvent').addEventListener('click', () => safe(async () => { applyPending(); if (!await confirmAction('删除当前事件？','此操作只修改当前草稿。保存到机器人后才会更新事件包。')) return; pack.splice(selected,1); if (!pack.length) pack.push(newEvent()); selected = Math.min(selected,pack.length-1); renderEditor(); changed(); }));
  $('validateBtn').addEventListener('click', () => safe(validate));
  $('exportBtn').addEventListener('click', () => safe(async () => { await validate(); download(pack, $('filename').value || '赛马事件.json'); }));
  $('importBtn').addEventListener('click', () => $('importFile').click());
  $('importFile').addEventListener('change', () => safe(async () => {
    const file = $('importFile').files[0]; if (!file) return;
    try {
      if (file.size > 128*1024) throw new Error('导入文件不能超过 128KB');
      const value = JSON.parse((await file.text()).replace(/^\uFEFF/,''));
      if (!Array.isArray(value) || !value.length || value.length > 128 || !value.every(e => e && typeof e === 'object' && !Array.isArray(e))) throw new Error('导入内容必须是包含 1~128 个事件对象的数组');
      value.forEach(event => { basicValidate(event); window.HorseRaceBlockModel.fromEvent(event); });
      if (dirty && !await confirmAction('替换当前草稿？','导入后会替换当前事件包，请先导出需要保留的内容。')) return;
      pack = value; selected = 0; $('filename').value = file.name; renderEditor(); changed(); notice(`已导入 ${pack.length} 条事件。`);
    } finally { $('importFile').value = ''; }
  }));
  $('refreshLibrary').addEventListener('click', () => safe(loadLibrary));
  $('library').addEventListener('change', () => safe(async () => {
    updateDeleteButton();
    const item = selectedPack(); if (!item) return;
    if (!Array.isArray(item.pack) || !item.pack.length || item.pack.length > 128 || !item.pack.every(e => e && typeof e === 'object' && !Array.isArray(e))) throw new Error('此事件包需要包含 1~128 个事件对象');
    if ((dirty || jsonDirty) && !await confirmAction('载入事件包？','当前草稿会被替换，请先导出需要保留的内容。')) return;
    item.pack.forEach(event => { basicValidate(event); window.HorseRaceBlockModel.fromEvent(event); });
    pack = clone(item.pack); selected = 0; loadedPackId=item.id; $('filename').value = item.source === 'builtin' ? '我的-' + item.filename : item.filename;
    renderEditor(); dirty = false; $('draftState').textContent = item.source === 'builtin' ? '内置包的编辑副本' : '已载入'; saveDraft(); notice('已载入。修改后可保存到自定义事件目录。');
  }));
  $('deletePack').addEventListener('click',()=>safe(async()=>{
    const item=selectedPack();
    if (!item || item.source!=='custom' || !canDeleteCustom || deletingPack) throw new Error('仅可删除选中的自定义事件包');
    if (!await confirmAction('删除自定义事件包？',`将删除 ${item.filename} 并重载事件。文件会保留备份；当前编辑草稿及进行中的比赛保留。`)) return;
    deletingPack=true; updateDeleteButton();
    try {
      const result=await api('delete',{id:item.id,confirm:true});
      if (loadedPackId===item.id) { loadedPackId=null; dirty=true; $('draftState').textContent='事件包已删除，草稿保留'; saveDraft(); }
      await loadLibrary(); notice(`${result.filename} 已删除并重载，备份已保留。`);
    } finally { deletingPack=false; updateDeleteButton(); }
  }));
  $('saveBtn').addEventListener('click', () => safe(async () => {
    await validate();
    const body = {pack,filename:$('filename').value.trim()};
    let result = await api('save',body);
    if (result.conflict) { if (!await confirmAction('覆盖已有自定义包？',`将覆盖 ${body.filename} 并重载事件。进行中的比赛仍使用原快照。`)) return; result = await api('save',{...body,overwrite:true}); }
    dirty = false; $('draftState').textContent = '已保存到机器人'; saveDraft(); notice(`${result.filename} 已保存并重载。`); await loadLibrary();
    loadedPackId='custom/'+result.filename; $('library').value=loadedPackId; updateDeleteButton();
  }));
  $('players').addEventListener('input', refreshActors);
  $('runTest').addEventListener('click', () => safe(async () => {
    await validate(); stopPlayback(); $('runTest').disabled = true;
    try {
      const body = {pack,selected,mode:$('testMode').value,actor:Number($('actor').value),seed:Number($('seed').value),rounds:Number($('rounds').value),length:Number($('length').value),event_rate:Number($('eventRate').value),players:getPlayers()};
      test = await api('simulate',body); $('frameSlider').max = test.frames.length-1; $('testResult').textContent = test.result;
      $('exportTest').disabled = false; renderFrame(0); notice('试跑完成。拖动回合进度或点击播放查看结算。');
    } finally { $('runTest').disabled = !online; }
  }));
  $('prevFrame').addEventListener('click', () => { stopPlayback(); renderFrame(frameIndex-1); });
  $('nextFrame').addEventListener('click', () => { stopPlayback(); renderFrame(frameIndex+1); });
  $('frameSlider').addEventListener('input', () => { stopPlayback(); renderFrame(Number($('frameSlider').value)); });
  $('playFrames').addEventListener('click', () => {
    if (playback) return stopPlayback(); if (!test) return;
    if (frameIndex >= test.frames.length-1) renderFrame(0);
    $('playFrames').textContent = '暂停'; playback = setInterval(() => { renderFrame(frameIndex+1); if (frameIndex >= test.frames.length-1) stopPlayback(); },650);
  });
  $('exportTest').addEventListener('click', () => { if (test) download(test, '赛马测试记录.json'); });

  try {
    const draft = JSON.parse(localStorage.getItem(draftKey) || 'null');
    if (draft && Array.isArray(draft.pack) && draft.pack.length > 0 && draft.pack.length <= 128 && draft.pack.every(e => e && typeof e === 'object' && !Array.isArray(e))) {
      restoredBlocks = draft.blocks || null;
      pack = draft.pack; selected = Math.min(Math.max(0,Number(draft.selected)||0),pack.length-1); $('filename').value = draft.filename || '我的赛马事件.json';
    }
  } catch { /* Storage is optional. */ }
  blockEditor = new window.HorseRaceBlockEditor({container:$('blocklyWorkspace'), onChange:(event,error) => {
    if (error) {
      $('validation').className='validation bad'; $('validation').textContent='✕ '+error.message;
      dirty=true; $('draftState').textContent='积木尚未连接完整'; saveDraft(); return;
    }
    pack[selected]=event; syncSource(); changed(); renderList();
    $('editingTitle').textContent=event.event_name || '编辑事件';
    blockEditor.setCatalog(blockCatalog());
  }});
  for (const [type,label] of Object.entries(window.HorseRaceBlockEditor.types)) $('blockType').append(new Option(label,type));
  $('addBlock').addEventListener('click', () => safe(() => blockEditor.add($('blockType').value)));
  $('undoBlocks').addEventListener('click', () => blockEditor.undo());
  $('redoBlocks').addEventListener('click', () => blockEditor.undo(true));
  $('fitBlocks').addEventListener('click', () => blockEditor.fit());
  renderEditor();
  if (restoredBlocks) {
    try { blockEditor.loadState(restoredBlocks); pack[selected]=blockEditor.read(); syncSource(); }
    catch (error) { $('validation').className='validation bad'; $('validation').textContent='草稿：'+error.message; }
  }
  refreshActors(); showTab(location.hash === '#test' ? 'test' : 'editor');
  aiPanel=new window.HorseRaceAIEventPanel({api,notice,validate:checkCandidate,apply:applyAI});
  (async () => {
    try {
      if (!window.HorseRaceDev) {
        if (!window.AstrBotPluginPage) throw new Error('standalone');
        await Promise.race([window.AstrBotPluginPage.ready(),new Promise((_,reject) => setTimeout(() => reject(new Error('bridge timeout')),7000))]);
      }
      online = true; await loadLibrary();
      try {
        const info=await api('capabilities'); canDeleteCustom=info.can_delete_custom===true; aiPanel.configure(info);
      } catch { notice('请重载插件后使用事件包删除和 AI 功能。'); }
      updateDeleteButton();
      $('connection').textContent = '已连接'; $('connectionDot').classList.add('online');
      $('saveBtn').disabled = false; $('runTest').disabled = false;
    } catch {
      online = false; $('connection').textContent = '离线编辑模式';
      notice('可编辑、导入和导出草稿。从 AstrBot 插件页面打开后可保存到机器人并使用真实引擎测试。');
    }
  })();
})();
