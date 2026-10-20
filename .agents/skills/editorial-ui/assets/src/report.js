(() => {
 const byId=id=>document.getElementById(id);
 // Entire fixture is illustrative. No hardware measurements or hidden data source.
 const rows=[
  {name:'Plan A',direction:'单核基线',cores:1,sram:2,latency:18.4,status:'checked'},
  {name:'Plan B',direction:'增加核数',cores:2,sram:4,latency:12.8,status:'checked'},
  {name:'Plan C',direction:'增加片上容量',cores:2,sram:8,latency:10.6,status:'review'},
  {name:'Plan D',direction:'四核分工',cores:4,sram:8,latency:9.7,status:'review'},
  {name:'Plan E',direction:'调整数据布局',cores:2,sram:6,latency:11.9,status:'checked'},
  {name:'Plan F',direction:'带宽敏感方案',cores:4,sram:12,latency:10.1,status:'review'}
 ];
 const statusLabel=value=>value==='checked'?'示例已核对':'待复核';
 const controller=EU.dialogController(byId('detail-dialog'));
 function current(){
  const query=byId('filter-query').value.trim().toLocaleLowerCase();
  const status=byId('filter-status').value;
  const sort=byId('sort-order').value;
  return rows.filter(row=>(status==='all'||row.status===status)&&`${row.name} ${row.direction}`.toLocaleLowerCase().includes(query))
   .sort((a,b)=>sort==='name'?a.name.localeCompare(b.name):a[sort]-b[sort]||a.name.localeCompare(b.name));
 }
 function showDetail(row,trigger){
  byId('detail-title').textContent=row.name;
  byId('detail-direction').textContent=row.direction;
  byId('detail-cores').textContent=String(row.cores);
  byId('detail-sram').textContent=`${row.sram} MiB`;
  byId('detail-latency').textContent=`${row.latency.toFixed(1)} ms（示例）`;
  byId('detail-assumption').textContent='仅用于验证筛选、排序、详情和导出。未连接执行模型，未校准任何真实硬件。';
  controller.open(trigger,'[data-close]');
 }
 function render(){
  const filtered=current(), fragment=document.createDocumentFragment();
  filtered.forEach(row=>{
   const tr=document.createElement('tr'), first=document.createElement('td'), button=document.createElement('button');
   button.type='button';button.className='row-link';button.textContent=row.name;button.setAttribute('aria-haspopup','dialog');
   button.addEventListener('click',()=>showDetail(row,button));first.append(button);tr.append(first);
   [row.direction,row.cores,row.sram,row.latency.toFixed(1),statusLabel(row.status)].forEach((value,index)=>{
    const td=document.createElement('td');td.textContent=String(value);
    if(index>=1&&index<=3)td.className='numeric';
    if(index===4)td.className='status-badge'+(row.status==='review'?' review':'');
    tr.append(td);
   });fragment.append(tr);
  });
  byId('rows').replaceChildren(fragment);byId('empty-state').hidden=filtered.length!==0;
  const summary=filtered.length?`显示 ${filtered.length} / ${rows.length} 个方案 · 当前最低示例时延 ${Math.min(...filtered.map(r=>r.latency)).toFixed(1)} ms`:`显示 0 / ${rows.length} 个方案`;
  EU.status(byId('result-status'),summary);byId('export-csv').disabled=filtered.length===0;
 }
 byId('filter-form').addEventListener('submit',event=>event.preventDefault());
 byId('filter-query').addEventListener('input',render);
 byId('filter-status').addEventListener('change',render);
 byId('sort-order').addEventListener('change',render);
 byId('filter-form').addEventListener('reset',()=>{setTimeout(()=>{render();EU.status(byId('export-status'),'');},0);});
 byId('empty-reset').addEventListener('click',()=>{byId('filter-form').reset();byId('filter-query').focus();});
 byId('export-csv').addEventListener('click',()=>{
  const filtered=current();if(!filtered.length)return;
  EU.downloadCsv([['方案','设计方向','核数','SRAM_MiB','示例时延_ms','状态','数据性质'],...filtered.map(r=>[r.name,r.direction,r.cores,r.sram,r.latency,statusLabel(r.status),'手工构造的示例数据'])],'editorial-ui-demo.csv');
  EU.status(byId('export-status'),`已生成 ${filtered.length} 行本地 CSV，请在浏览器下载项中查看。`,'success');
 });
 render();
})();
