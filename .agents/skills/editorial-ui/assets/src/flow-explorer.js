(() => {
 const byId=id=>document.getElementById(id);
 const stages=[
  ['候选架构','在明确约束下提出待评估的硬件资源组合，不在这一层替代整个编译过程。','工作负载、资源范围、搜索约束。','带有稳定标识的架构候选。','候选必须满足预先定义的合法性检查。','这是界面行为示例，不代表任何特定架构工具的已实现能力。'],
  ['映射与执行计划','把工作负载组织为可执行的任务、依赖与资源使用计划，使后续评估面对同一份语义。','模型表示、架构候选、映射约束。','任务依赖、数据布局与显式搬运计划。','计划中的数据与依赖必须保持语义一致。','示意：图优化和映射是独立职责，不应仅由一个“搜索”按钮掩盖。'],
  ['执行与资源竞争','沿着计划推进任务，并观察计算、片上存储和传输资源之间的等待与重叠。','执行计划与资源模型。','任务完成事件、等待原因与请求序列。','竞争和背压是否被建模，需要在真实工具中明确验证。','这里仅展示信息组织方式，不生成周期精确性能。'],
  ['存储请求与反馈','在选定的精度层次下评估访存，并把完成时间和阻塞反馈给执行模型。','带依赖与时间语义的访存请求。','完成反馈、统计与约束证据。','简单固定延迟与详细存储仿真不能混称为同一精度。','界面应标明假设与证据来源，不能让精美图形替代模型可信度。']
 ];
 const fields=['stage-title','stage-summary','stage-input','stage-output','stage-constraint','stage-note'];
 function select(index,animate=true){
  document.querySelectorAll('[data-stage]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.stage)===index)));
  stages[index].forEach((text,i)=>{byId(fields[i]).textContent=text;});
  byId('stage-label').textContent=`当前阶段 / ${String(index+1).padStart(2,'0')}`;
  EU.status(byId('selection-status'),`已选择：${stages[index][0]}。`);
  if(animate)EU.reveal(byId('inspector'));
 }
 document.querySelectorAll('[data-stage]').forEach(button=>button.addEventListener('click',()=>select(Number(button.dataset.stage))));
 const box=byId('explorer'), handle=byId('splitter'), narrow=matchMedia('(max-width:900px)');
 let ratio=.54, drag=null;
 const limits=()=>{ const width=Math.max(1,box.clientWidth-14); return [Math.min(.49,320/width),Math.max(.51,1-300/width)]; };
 function apply(value){
  const [min,max]=limits(); ratio=Math.max(min,Math.min(max,value));
  box.style.gridTemplateColumns=`minmax(0, ${ratio}fr) 14px minmax(0, ${1-ratio}fr)`;
  handle.setAttribute('aria-valuemin',String(Math.ceil(min*100))); handle.setAttribute('aria-valuemax',String(Math.floor(max*100)));
  handle.setAttribute('aria-valuenow',String(Math.round(ratio*100))); handle.setAttribute('aria-valuetext',`流程概览占 ${Math.round(ratio*100)}%`);
 }
 function finish(rollback){
  if(!drag)return;
  const previous=drag; drag=null;
  if(rollback)apply(previous.ratio);
  delete box.dataset.dragging;
  if(handle.hasPointerCapture(previous.id))handle.releasePointerCapture(previous.id);
 }
 handle.addEventListener('pointerdown',event=>{
  if(event.button!==0 || !event.isPrimary || narrow.matches || drag)return;
  event.preventDefault(); handle.focus({preventScroll:true});
  drag={id:event.pointerId,x:event.clientX,ratio,started:false}; handle.setPointerCapture(event.pointerId);
 });
 handle.addEventListener('pointermove',event=>{
  if(!drag || drag.id!==event.pointerId)return;
  const delta=event.clientX-drag.x;
  if(!drag.started && Math.abs(delta)<4)return;
  drag.started=true; box.dataset.dragging='true'; apply(drag.ratio+delta/Math.max(1,box.clientWidth-14));
 });
 handle.addEventListener('pointerup',event=>{if(drag?.id===event.pointerId)finish(false);});
 handle.addEventListener('pointercancel',()=>finish(true));
 handle.addEventListener('lostpointercapture',()=>finish(true));
 document.addEventListener('keydown',event=>{if(event.key==='Escape' && drag){event.preventDefault(); finish(true);}});
 handle.addEventListener('keydown',event=>{
  const [min,max]=limits(); let next=ratio;
  if(event.key==='ArrowLeft')next-=.02; else if(event.key==='ArrowRight')next+=.02;
  else if(event.key==='Home')next=min; else if(event.key==='End')next=max; else return;
  event.preventDefault(); finish(false); apply(next);
 });
 handle.addEventListener('dblclick',()=>{finish(false);apply(.5);});
 byId('equalize').addEventListener('click',()=>{finish(false);apply(.5);});
 const onResize=()=>{if(drag)finish(true);if(!narrow.matches)apply(ratio);};
 window.addEventListener('resize',onResize);
 if(narrow.addEventListener)narrow.addEventListener('change',onResize);
 const reset=EU.dialogController(byId('reset-dialog'));
 byId('reset-explorer').addEventListener('click',event=>reset.open(event.currentTarget,'#cancel-reset'));
 byId('confirm-reset').addEventListener('click',()=>{finish(true);apply(.54);select(0,false);reset.close();});
 apply(ratio);
})();
