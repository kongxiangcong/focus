(() => {
  const byId=id=>document.getElementById(id);
  let expanded=1, composing=false, timer=null, pendingQuestion='';
  const controller=EU.dialogController(byId('explanation'));
  byId('explain').addEventListener('click',e=>controller.open(e.currentTarget,'#question'));
  byId('continue').addEventListener('click',()=>{
    if(expanded>=3) return;
    expanded++; const section=document.querySelector(`[data-section="${expanded}"]`);
    section.hidden=false; EU.reveal(section);
    byId('progress').textContent=`已展开 ${expanded} / 3 段`;
    EU.status(byId('reading-status'),expanded===3?'全文已展开，前文仍保留。':'下一段已追加在下方，当前阅读位置保持不变。');
    if(expanded===3){ byId('continue').textContent='全文已展开'; byId('continue').disabled=true; }
  });
  const follower=EU.scrollFollower(byId('stream'),byId('stream-content'),byId('jump-latest'));
  function setBusy(value) { byId('send').disabled=value; byId('stop').disabled=!value; byId('stream').setAttribute('aria-busy',String(value)); }
  function stop() {
    if(timer===null) return;
    clearInterval(timer); timer=null; setBusy(false); byId('retry').hidden=false;
    EU.status(byId('answer-status'),'已停止。问题草稿与已生成内容保留，可重试。');
  }
  byId('stop').addEventListener('click',stop);
  byId('explanation').addEventListener('close',stop);
  function submit() {
    if(timer!==null || composing) return;
    const text=byId('question').value.trim();
    if(!text){ EU.status(byId('answer-status'),'请先输入问题。','error'); byId('question').focus(); return; }
    pendingQuestion=byId('question').value;
    const fail=byId('simulate-error').checked;
    const paragraph='辅助界面的职责，是在需要的时候出现，并在结束后把控制权交还给用户。以阅读为例，正文的位置、输入草稿和当前选择都属于需要保留的状态；打开解释层不能把它们隐式重置。短暂的视觉反馈应当解释状态变化，而不是代替真实行为。';
    const answer=`关于“${text}”的本地示例\n\n`+
      Array.from({length:8},(_,i)=>`${i+1}. ${paragraph}`).join('\n\n')+
      '\n\n示例结束。以上内容来自本地固定文本，不是模型生成。';
    byId('stream-content').textContent=''; byId('retry').hidden=true; setBusy(true); follower.reset();
    EU.status(byId('answer-status'),'正在生成本地示例。可停止，也可向上阅读。');
    let offset=0;
    timer=setInterval(()=>{
      if(fail && offset>=96){ clearInterval(timer); timer=null; setBusy(false); byId('retry').hidden=false; EU.status(byId('answer-status'),'模拟失败：没有网络请求。草稿已保留，取消勾选后重试。','error'); return; }
      offset+=9; byId('stream-content').textContent=answer.slice(0,offset); follower.update();
      if(offset>=answer.length){ clearInterval(timer); timer=null; setBusy(false); if(byId('question').value===pendingQuestion)byId('question').value=''; EU.status(byId('answer-status'),'本地示例已完成。阅读进度没有改变。','success'); }
    },20);
  }
  byId('question-form').addEventListener('submit',event=>{event.preventDefault(); submit();});
  byId('retry').addEventListener('click',submit);
  byId('question').addEventListener('compositionstart',()=>{composing=true;});
  byId('question').addEventListener('compositionend',()=>{composing=false;});
  byId('question').addEventListener('keydown',event=>{
    if(composing || event.isComposing || event.keyCode===229) return;
    if(event.key==='Enter' && !event.shiftKey){event.preventDefault(); submit();}
  });
})();
