/* The panel only requests data; importing/saving requires a user action. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  class AIEventPanel {
    constructor({api, notice, validate, apply}) {
      this.api=api; this.notice=notice; this.validate=validate; this.apply=apply;
      this.messages=[]; this.lastPack=null; this.candidate=null; this.enabled=false;
      $('aiForm').addEventListener('submit', event=>{ event.preventDefault(); this.send(); });
      $('clearAI').addEventListener('click',()=>this.clear());
      $('importAI').addEventListener('click',()=>this.import(false));
      $('saveAI').addEventListener('click',()=>this.import(true));
    }
    configure(info) {
      this.enabled=info.ai_enabled===true;
      $('aiPanel').hidden=!this.enabled;
      $('editorPanel').classList.toggle('with-ai',this.enabled);
      $('aiModel').textContent=info.ai_provider_id ? '模型：'+info.ai_provider_id : '模型：AstrBot 默认聊天模型';
      this.buttons();
    }
    buttons() {
      const busy=this.generating || this.applying;
      for (const id of ['sendAI','clearAI','importAI','saveAI']) $(id).disabled=busy || !this.enabled;
      $('sendAI').textContent=this.generating ? '生成中…' : '发送';
      $('aiForm').setAttribute('aria-busy',String(Boolean(busy)));
    }
    append(role,content) {
      this.messages.push({role,content:String(content)});
      this.messages=this.messages.slice(-20);
      $('aiMessages').replaceChildren();
      for (const message of this.messages) {
        const row=document.createElement('div'); row.className='ai-message '+message.role;
        const label=document.createElement('strong'); label.textContent=message.role==='user' ? '你' : 'AI';
        row.append(label,document.createTextNode(message.content)); $('aiMessages').append(row);
      }
      $('aiMessages').scrollTop=$('aiMessages').scrollHeight;
    }
    clear() {
      if (this.generating || this.applying) return;
      this.messages=[]; this.candidate=null; this.lastPack=null;
      $('aiMessages').replaceChildren(); $('aiCandidate').hidden=true; $('aiPrompt').value='';
    }
    async send() {
      if (!this.enabled || this.generating || this.applying) return;
      const prompt=$('aiPrompt').value.trim(); if (!prompt) return;
      const history=this.messages.slice(-8).map(item=>({role:item.role,content:item.content.slice(0,2000)}));
      this.append('user',prompt); $('aiPrompt').value='';
      this.generating=true; this.candidate=null; $('aiCandidate').hidden=true; this.buttons();
      try {
        const result=await this.api('ai_chat',{prompt,history,candidate:this.lastPack});
        if (result.pack) this.validate(result.pack);
        this.append('assistant',result.reply);
        if (result.pack) {
          this.candidate={pack:result.pack,filename:result.filename}; this.lastPack=result.pack;
          $('aiFilename').value=result.filename; $('aiEventNames').replaceChildren();
          result.pack.forEach((event,index)=>{ const item=document.createElement('li'); item.textContent=event.event_name || '事件 '+(index+1); $('aiEventNames').append(item); });
          $('aiCandidate').hidden=false;
        }
      } catch(error) { this.append('assistant','生成失败：'+(error.message || error)); }
      finally { this.generating=false; this.buttons(); }
    }
    async import(save) {
      if (!this.candidate || this.generating || this.applying) return;
      this.applying=true; this.buttons();
      try {
        await this.apply(this.candidate.pack,$('aiFilename').value.trim(),save);
      } catch(error) { this.notice(error.message || error,true); }
      finally { this.applying=false; this.buttons(); }
    }
  }
  window.HorseRaceAIEventPanel=AIEventPanel;
})();
