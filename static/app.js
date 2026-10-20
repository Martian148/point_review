const app = document.querySelector('#app');
let routeVersion = 0;
let editorNodes = null;
let editorPointId = null;
let importPreview = null;
let reviewSession = null;
let selectedOption = null;
let feedback = null;
let questionStartedAt = 0;
let busy = false;
let toastTimer;

function esc(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function stars(value) { return value == null ? '<span class="badge">未评估</span>' : `<span class="stars" aria-label="熟练度 ${value} 星">${'★'.repeat(value)}<span style="color:#e5e7eb">${'★'.repeat(5-value)}</span></span>`; }
function dateLabel(value) {
  if (!value) return '—';
  const date = new Date(value), today = new Date();
  if (date.toDateString() === today.toDateString()) return '今天';
  const tomorrow = new Date(today); tomorrow.setDate(today.getDate()+1);
  if (date.toDateString() === tomorrow.toDateString()) return '明天';
  return new Intl.DateTimeFormat('zh-CN',{month:'numeric',day:'numeric'}).format(date);
}
function toast(message) { const el=document.querySelector('#toast'); el.textContent=message; el.classList.add('show'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>el.classList.remove('show'),3200); }
async function api(path, options={}) {
  const init={...options,headers:{'Content-Type':'application/json',...(options.headers||{})}};
  if (options.body && typeof options.body !== 'string') init.body=JSON.stringify(options.body);
  const response=await fetch('/api'+path,init);
  let data; try { data=await response.json(); } catch { throw Error('服务器返回内容无效'); }
  if (!response.ok) throw Error(data?.error || `请求失败 (${response.status})`);
  return data;
}
function nav(path) { history.pushState({},'',path); render(); window.scrollTo(0,0); }
function shell(content,active='') {
  app.innerHTML=`<div class="app-shell"><aside class="sidebar"><a class="brand" href="/" data-link><span class="brand-mark">P</span>Point-review</a><nav class="nav" aria-label="主导航">
  <a href="/" data-link class="${active==='home'?'active':''}"><span class="nav-icon">⌂</span>首页</a>
  <a href="/points" data-link class="${active==='points'?'active':''}"><span class="nav-icon">▤</span>Point</a>
  <a href="/review" data-link class="${active==='review'?'active':''}"><span class="nav-icon">◎</span>开始复习</a>
  </nav><div class="sidebar-foot">一个 Point，一次语境练习。<br>从记住走向真正理解。</div></aside><main class="main"><div class="container">${content}</div></main></div>`;
}
function loading(focus=false, message='正在加载…') { app.innerHTML=focus?`<div class="focus-shell"><div class="loading"><div class="spinner"></div>${esc(message)}</div></div>`:`<div class="app-shell"><div class="main" style="margin:auto"><div class="loading"><div class="spinner"></div>${esc(message)}</div></div></div>`; }
function errorPage(message) { shell(`<div class="narrow"><a class="back" href="/" data-link>← 返回首页</a><div class="card empty"><div class="empty-icon">!</div><h3>页面暂时无法打开</h3><p>${esc(message)}</p><button class="btn" id="retry">重试</button></div></div>`); document.querySelector('#retry').onclick=render; }
function empty(title,text,href,label) {return `<div class="empty"><div class="empty-icon">◇</div><h3>${title}</h3><p>${text}</p>${href?`<a class="btn btn-primary" href="${href}" data-link>${label}</a>`:''}</div>`;}

async function render() {
  const version=++routeVersion, path=location.pathname;
  loading(path.startsWith('/review/session/'));
  try {
    if (path==='/') await dashboardPage();
    else if (path==='/points') await pointsPage();
    else if (path==='/points/new') await editorPage(null);
    else if (path==='/points/import/markdown') await importPage();
    else if (/^\/points\/\d+\/edit$/.test(path)) await editorPage(Number(path.split('/')[2]));
    else if (/^\/points\/\d+$/.test(path)) await detailPage(Number(path.split('/')[2]));
    else if (path==='/review') await reviewStartPage();
    else if (/^\/review\/session\/\d+$/.test(path)) await sessionPage(Number(path.split('/')[3]));
    else if (/^\/review\/result\/\d+$/.test(path)) await resultPage(Number(path.split('/')[3]));
    else shell(`<div class="narrow">${empty('页面不存在','请检查链接或返回首页。','/','返回首页')}</div>`);
  } catch (error) { if(version===routeVersion) errorPage(error.message); }
}

async function dashboardPage() {
  const d=await api('/dashboard');
  shell(`<div class="page-heading"><div><div class="eyebrow">DASHBOARD</div><h1>你好，今天也继续前进。</h1><p class="subtle">把记下的知识，放回真实语境里。</p></div></div>
  <section class="hero"><div><div class="eyebrow">TODAY'S REVIEW</div><h2>今日待复习 ${d.due} 个 Point</h2><p>${d.due ? '每次最多 10 题，系统会优先挑选到期和薄弱的内容。' : '新的 Point 会进入复习队列。现在就开始一次练习。'}</p></div><div class="actions"><span class="hero-count">${d.due}</span><a class="btn" href="/review" data-link>开始复习 →</a></div></section>
  <div class="stats"><div class="card stat"><div class="stat-label">Point 总数</div><div class="stat-value">${d.total}</div><div class="subtle">知识库里的内容</div></div><div class="card stat"><div class="stat-label">未评估</div><div class="stat-value">${d.unevaluated}</div><div class="subtle">等待第一次练习</div></div><div class="card stat"><div class="stat-label">今日完成</div><div class="stat-value">${d.completedToday}</div><div class="subtle">已作答的题目</div></div></div>
  <div class="section-top"><h2>最近添加的 Point</h2><a class="btn btn-text" href="/points" data-link>查看全部 →</a></div>
  <div class="card card-pad">${d.recentPoints.length?`<ul class="list-simple">${d.recentPoints.map(p=>`<li><a class="point-title" href="/points/${p.id}" data-link>${esc(p.title)}</a>${stars(p.mastery)}</li>`).join('')}</ul>`:empty('从第一个 Point 开始','记录一个单词或词组，添加释义后就能开始复习。','/points/new','添加 Point')}</div>
  ${d.recentSessions.some(s=>s.status==='COMPLETED')?`<div class="section-top"><h2>最近复习</h2></div><div class="card card-pad"><ul class="list-simple">${d.recentSessions.filter(s=>s.status==='COMPLETED').map(s=>`<li><span>完成 ${s.actual_question_count} 道题 · ${dateLabel(s.completed_at)}</span><a class="btn btn-text" href="/review/result/${s.id}" data-link>查看结果 →</a></li>`).join('')}</ul></div>`:''}`, 'home');
}

async function pointsPage() {
  const q=new URLSearchParams(location.search).get('q') || '';
  const rows=await api('/points?q='+encodeURIComponent(q));
  if(location.pathname!=='/points'||(new URLSearchParams(location.search).get('q')||'')!==q)return;
  shell(`<div class="page-heading"><div><div class="eyebrow">POINT LIBRARY</div><h1>Point</h1><p class="subtle">管理你想记住的每一个知识点。</p></div></div>
  <div class="toolbar"><div class="search"><input id="search" class="input" value="${esc(q)}" placeholder="搜索 Point 标题…" aria-label="搜索 Point 标题"></div><div class="actions"><a class="btn" href="/points/import/markdown" data-link>Markdown 导入</a><a class="btn btn-primary" href="/points/new" data-link>＋ 添加 Point</a></div></div>
  <div class="card table-wrap">${rows.length?`<table class="table"><thead><tr><th>POINT</th><th>熟练度</th><th>下次复习</th><th>复习次数</th><th>操作</th></tr></thead><tbody>${rows.map(p=>`<tr><td class="title-cell"><a href="/points/${p.id}" data-link>${esc(p.title)}</a></td><td>${stars(p.mastery)}</td><td>${p.next_review_at?dateLabel(p.next_review_at):'<span class="muted">待首次复习</span>'}</td><td>${p.review_count}</td><td><a class="btn btn-text" href="/points/${p.id}/edit" data-link>编辑</a></td></tr>`).join('')}</tbody></table>`:empty(q?'没有找到匹配的 Point':'还没有 Point',q?'换个关键词试试。':'添加一个单词或词组，建立你的知识库。',q?null:'/points/new','添加 Point')}</div>`, 'points');
  const input=document.querySelector('#search'); let timer;
  input.oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{if(location.pathname!=='/points')return;const value=input.value.trim(), cursor=input.selectionStart;history.replaceState({},'',value?'/points?q='+encodeURIComponent(value):'/points');pointsPage().then(()=>{if(location.pathname!=='/points')return;const next=document.querySelector('#search');if(next){next.focus();next.setSelectionRange(cursor,cursor);}}).catch(e=>toast(e.message));},250);};
}

function treeView(nodes) { return `<ul class="tree-view">${nodes.map(n=>`<li>${esc(n.content)}${n.children?.length?treeView(n.children):''}</li>`).join('')}</ul>`; }
async function detailPage(id) {
  const p=await api('/points/'+id); if(!p) throw Error('Point 不存在');
  shell(`<div class="narrow"><a class="back" href="/points" data-link>← 返回 Point 列表</a><div class="page-heading"><div><div class="eyebrow">POINT DETAIL</div><h1>${esc(p.title)}</h1><p class="subtle">${p.source_type==='MARKDOWN'?'由 Markdown 导入':'手动添加'} · ${dateLabel(p.created_at)} 创建</p></div><div class="actions"><a class="btn" href="/points/${id}/edit" data-link>编辑</a><button class="btn btn-danger" id="delete-point">删除</button></div></div>
  <div class="detail-meta"><div class="meta-box"><span>熟练度</span><strong>${stars(p.mastery)}</strong></div><div class="meta-box"><span>下次复习</span><strong>${p.next_review_at?dateLabel(p.next_review_at):'待首次复习'}</strong></div><div class="meta-box"><span>上次复习</span><strong>${dateLabel(p.last_reviewed_at)}</strong></div><div class="meta-box"><span>复习次数</span><strong>${p.review_count}</strong></div></div>
  <div class="section-top"><h2>释义与理解</h2></div><div class="card card-pad">${treeView(p.nodes)}</div></div>`, 'points');
  document.querySelector('#delete-point').onclick=async()=>{if(!confirm(`确定删除「${p.title}」吗？`))return;try{await api('/points/'+id,{method:'DELETE'});toast('Point 已删除');nav('/points');}catch(e){toast(e.message);}};
}

let nextNodeKey=0;
function prepareNodes(nodes) { return nodes.map(n=>({_key:'n'+(++nextNodeKey),content:n.content||'',children:prepareNodes(n.children||[])})); }
function nodeHTML(nodes,depth=0) {return `<div class="node-list">${nodes.map(n=>`<div class="node-item" data-node="${n._key}"><div class="node-row"><div class="node-line"><span class="node-bullet">•</span><input class="input node-input" data-key="${n._key}" value="${esc(n.content)}" placeholder="输入释义、例句或理解说明"></div><div class="node-buttons"><button type="button" data-node-op="child" data-key="${n._key}" title="添加子级">＋ 子级</button><button type="button" data-node-op="up" data-key="${n._key}" title="上移">↑</button><button type="button" data-node-op="down" data-key="${n._key}" title="下移">↓</button><button type="button" data-node-op="indent" data-key="${n._key}" title="降一级">→</button><button type="button" data-node-op="outdent" data-key="${n._key}" title="升一级">←</button><button type="button" data-node-op="remove" data-key="${n._key}" title="删除">删除</button></div></div>${n.children.length?`<div class="node-children">${nodeHTML(n.children,depth+1)}</div>`:''}</div>`).join('')}</div>`;}
function locateNode(nodes,key,parent=null,grand=null) { for(let i=0;i<nodes.length;i++){if(nodes[i]._key===key)return {nodes,index:i,node:nodes[i],parent,grand};const found=locateNode(nodes[i].children,key,nodes[i],nodes);if(found)return found;}return null; }
function drawNodes() {document.querySelector('#node-editor').innerHTML=nodeHTML(editorNodes);}
function plainNodes(nodes) {return nodes.map(n=>({content:n.content.trim(),children:plainNodes(n.children)}));}
async function editorPage(id) {
  editorPointId=id; nextNodeKey=0;
  const p=id?await api('/points/'+id):null;
  editorNodes=prepareNodes(p?.nodes || [{content:'',children:[]}]);
  shell(`<div class="narrow"><a class="back" href="${id?'/points/'+id:'/points'}" data-link>← 返回</a><div class="page-heading"><div><div class="eyebrow">${id?'EDIT POINT':'NEW POINT'}</div><h1>${id?'编辑 Point':'添加 Point'}</h1><p class="subtle">一个单词或词组，加上你自己的理解。</p></div></div>
  <form id="point-form" class="card form-card"><div class="field"><label for="point-title">Point 标题</label><input id="point-title" class="input" maxlength="255" required placeholder="例如 perspective" value="${esc(p?.title||'')}"></div>
  <div class="field"><label>释义与理解</label><p class="field-help" style="margin:-2px 0 13px">支持多层释义。可以添加子级，也可以调整顺序和层级。</p><div id="node-editor"></div><button type="button" class="btn btn-small" id="add-root" style="margin-top:15px">＋ 添加一条释义</button></div>
  <div class="form-footer"><a class="btn" href="${id?'/points/'+id:'/points'}" data-link>取消</a><button class="btn btn-primary" type="submit">保存 Point</button></div></form></div>`, 'points');
  drawNodes();
  document.querySelector('#add-root').onclick=()=>{editorNodes.push({_key:'n'+(++nextNodeKey),content:'',children:[]});drawNodes();document.querySelector('#node-editor .node-item:last-child .node-input')?.focus();};
  document.querySelector('#node-editor').oninput=event=>{if(!event.target.matches('.node-input'))return;const found=locateNode(editorNodes,event.target.dataset.key);if(found)found.node.content=event.target.value;};
  document.querySelector('#node-editor').onclick=event=>{const button=event.target.closest('[data-node-op]');if(!button)return;const op=button.dataset.nodeOp, found=locateNode(editorNodes,button.dataset.key);if(!found)return;const {nodes,index,node,parent,grand}=found;
    if(op==='child')node.children.push({_key:'n'+(++nextNodeKey),content:'',children:[]});
    else if(op==='remove'){if(!confirm('删除这条释义及其子级？'))return;nodes.splice(index,1);}
    else if(op==='up'&&index>0)[nodes[index-1],nodes[index]]=[nodes[index],nodes[index-1]];
    else if(op==='down'&&index<nodes.length-1)[nodes[index],nodes[index+1]]=[nodes[index+1],nodes[index]];
    else if(op==='indent'&&index>0){nodes.splice(index,1);nodes[index-1].children.push(node);}
    else if(op==='outdent'&&parent){nodes.splice(index,1);const parentLocation=locateNode(editorNodes,parent._key);parentLocation.nodes.splice(parentLocation.index+1,0,node);}
    drawNodes();};
  document.querySelector('#point-form').onsubmit=async event=>{event.preventDefault();const title=document.querySelector('#point-title').value.trim();if(!title){toast('请输入 Point 标题');return;}if(!editorNodes.length||editorNodes.some(n=>!n.content.trim())){toast('请至少填写一条完整释义');return;}const button=event.submitter;button.disabled=true;try{const item=await api(id?'/points/'+id:'/points',{method:id?'PUT':'POST',body:{title,nodes:plainNodes(editorNodes)}});toast('Point 已保存');nav('/points/'+item.id);}catch(error){toast(error.message);}finally{button.disabled=false;}};
}

async function importPage() {
  importPreview=null;
  shell(`<div><a class="back" href="/points" data-link>← 返回 Point 列表</a><div class="page-heading"><div><div class="eyebrow">BATCH IMPORT</div><h1>Markdown 批量导入</h1><p class="subtle">用无序列表描述 Point 及多层释义，预览确认后一次导入。</p></div></div>
  <div class="split"><div class="card card-pad"><h3>Markdown 输入</h3><textarea id="markdown" class="textarea" style="min-height:420px" placeholder="- perspective&#10;  - n. 观点，看法，视角&#10;    - from a different perspective = 从不同角度看&#10;  - keep sth in perspective = 客观看待某事"></textarea><p class="field-help">顶层列表项是 Point，缩进列表项是它的释义或子级。</p><div class="actions" style="margin-top:18px"><button class="btn" id="preview-md">解析并预览</button></div></div>
  <div class="card card-pad"><h3>导入预览</h3><div id="import-preview" class="preview-list">${empty('等待解析','粘贴 Markdown 后点击「解析并预览」。')}</div></div></div><div class="actions" style="justify-content:flex-end;margin-top:18px"><button class="btn btn-primary" id="confirm-import" disabled>确认导入</button></div></div>`, 'points');
  document.querySelector('#preview-md').onclick=async()=>{try{const text=document.querySelector('#markdown').value;importPreview=await api('/import/preview',{method:'POST',body:{markdown:text}});const count=importPreview.filter(p=>!p.duplicate).length;document.querySelector('#import-preview').innerHTML=`<div class="callout">解析到 ${importPreview.length} 个 Point，可导入 ${count} 个。重复标题将跳过。</div>${importPreview.map(p=>`<div class="preview-point"><strong>${esc(p.title)} ${p.duplicate?'<span class="badge">重复 · 跳过</span>':'<span class="badge badge-green">可导入</span>'}</strong>${treeView(p.nodes)}</div>`).join('')}`;document.querySelector('#confirm-import').disabled=count===0;}catch(e){importPreview=null;document.querySelector('#confirm-import').disabled=true;toast(e.message);}};
  document.querySelector('#markdown').oninput=()=>{importPreview=null;document.querySelector('#confirm-import').disabled=true;document.querySelector('#import-preview').innerHTML=empty('内容已变化','请重新解析并预览。');};
  document.querySelector('#confirm-import').onclick=async event=>{event.target.disabled=true;try{const result=await api('/import',{method:'POST',body:{markdown:document.querySelector('#markdown').value}});toast(`成功导入 ${result.createdIds.length} 个，跳过 ${result.skippedTitles.length} 个重复标题`);nav('/points');}catch(e){toast(e.message);event.target.disabled=false;}};
}

async function reviewStartPage() {
  const p=await api('/review/preview');
  shell(`<div class="narrow"><div class="page-heading"><div><div class="eyebrow">REVIEW SESSION</div><h1>开始复习</h1><p class="subtle">在英语语境里确认你是否真正理解了这些 Point。</p></div></div>
  <div class="card review-intro"><h2>准备好开始了吗？</h2><p>本轮将练习 <strong>${p.plannedCount}</strong> 个 Point。系统优先选择到期、薄弱和新加入的内容；每题只可提交一次。</p>
  ${p.points.length?`<div class="candidate-list">${p.points.map(x=>`<span>${esc(x.title)}</span>`).join('')}</div>`:''}
  ${!p.aiConfigured?'<div class="callout callout-warning" style="margin-bottom:20px">AI 出题尚未配置。请在启动前设置 OPENAI_API_KEY 和 OPENAI_MODEL，具体方法见 README。</div>':''}
  ${p.availableCount===0?'<div class="callout" style="margin-bottom:20px">知识库还没有 Point。先添加一个，就能开始练习。</div>':''}
  <div class="actions"><button class="btn btn-primary" id="begin-review" ${!p.aiConfigured||!p.availableCount?'disabled':''}>生成本轮题目 →</button><a class="btn" href="/points/new" data-link>添加 Point</a></div></div></div>`, 'review');
  document.querySelector('#begin-review').onclick=async()=>{if(busy)return;busy=true;loading(false,'AI 正在生成考研语境题，可能需要一点时间…');try{const session=await api('/review/sessions',{method:'POST',body:{}});nav('/review/session/'+session.id);}catch(e){toast(e.message);await reviewStartPage();}finally{busy=false;}};
}

function markedContext(context,title) {let target=title;let i=context.toLowerCase().indexOf(target.toLowerCase());if(i<0&&/\b(sth|sb|somebody|something|doing)\b/i.test(title)){const words=title.toLowerCase().match(/[a-z]+/g)||[];const excluded=new Set(['sth','sb','somebody','something','doing','be','to','in','on','at','of','for','with','a','the']);target=words.filter(w=>!excluded.has(w)).sort((a,b)=>b.length-a.length)[0]||title;i=context.toLowerCase().indexOf(target);}if(i<0)return esc(context);return esc(context.slice(0,i))+'<mark class="highlight">'+esc(context.slice(i,i+target.length))+'</mark>'+esc(context.slice(i+target.length));}
function drawSession() {
  const s=reviewSession;
  if(!s)return;
  const firstUnanswered=s.questions.findIndex(q=>!q.answer);
  const index=feedback ? feedback.index : (firstUnanswered<0?s.questions.length-1:firstUnanswered);
  const q=s.questions[index];
  const answer=feedback?.index===index?feedback.answer:q.answer;
  const selected=answer?.selectedOption||selectedOption;
  const progress=answer?(index+1)/s.questions.length:index/s.questions.length;
  app.innerHTML=`<div class="focus-shell"><header class="focus-header"><a class="brand" href="/" data-link><span class="brand-mark">P</span>Point-review</a><button class="btn btn-text" id="leave-review">退出本轮</button></header><main class="focus-main"><div class="progress-label"><span>复习进度</span><span>${index+1} / ${s.questions.length}</span></div><div class="progress"><span style="width:${progress*100}%"></span></div>
  <div class="card question-card"><div class="question-number">QUESTION ${String(index+1).padStart(2,'0')}</div><p class="context">${markedContext(q.context,q.title)}</p><div class="question-prompt">${esc(q.question)}</div>
  <div class="options">${q.options.map(o=>`<button class="option ${selected===o.key?'selected':''} ${answer&&o.key===answer.correctOption?'correct':''} ${answer&&selected===o.key&&!answer.isCorrect?'wrong':''}" data-option="${o.key}" ${answer?'disabled':''}><span class="option-key">${o.key}</span><span>${esc(o.text)}</span></button>`).join('')}</div>
  ${answer?`<div class="feedback ${answer.isCorrect?'':'wrong'}"><strong>${answer.isCorrect?'✓ 回答正确':'✕ 回答错误 · 正确答案 '+answer.correctOption}</strong>${esc(answer.explanation)}</div>`:''}
  <div class="question-footer"><button class="btn btn-primary" id="question-action" ${!answer&&!selectedOption?'disabled':''}>${answer?(index===s.questions.length-1?'查看复习结果 →':'下一题 →'):'提交答案'}</button></div></div></main></div>`;
  document.querySelectorAll('[data-option]').forEach(button=>button.onclick=()=>{selectedOption=button.dataset.option;drawSession();});
  document.querySelector('#question-action').onclick=async()=>{if(answer){if(index===s.questions.length-1){nav('/review/result/'+s.id);}else{feedback=null;selectedOption=null;questionStartedAt=Date.now();drawSession();}return;}
    const button=document.querySelector('#question-action');button.disabled=true;
    try{const result=await api(`/review/sessions/${s.id}/answers`,{method:'POST',body:{questionId:q.id,selectedOption,responseTimeMs:Math.min(Date.now()-questionStartedAt,3600000)}});q.answer=result;feedback={index,answer:result};selectedOption=null;if(result.completed)s.status='COMPLETED';drawSession();}catch(e){toast(e.message);button.disabled=false;}};
  document.querySelector('#leave-review').onclick=async()=>{if(!confirm('退出后本轮已答题目不会计入熟练度。确定退出吗？'))return;try{await api(`/review/sessions/${s.id}/abandon`,{method:'POST',body:{}});nav('/review');}catch(e){toast(e.message);}};
}
async function sessionPage(id) {
  reviewSession=await api('/review/sessions/'+id);
  if(!reviewSession)throw Error('本轮复习不存在');
  if(reviewSession.status==='COMPLETED'){nav('/review/result/'+id);return;}
  if(!['READY','IN_PROGRESS'].includes(reviewSession.status)){toast('本轮复习无法继续，请重新开始');nav('/review');return;}
  selectedOption=null;feedback=null;questionStartedAt=Date.now();drawSession();
}

async function resultPage(id) {
  const r=await api('/review/sessions/'+id+'/result');
  shell(`<div class="narrow"><div class="card result-hero"><div class="result-icon">✓</div><h1>本轮复习完成</h1><p class="subtle">每一次回答，都会让下一次复习更有方向。</p><div class="result-metrics"><div class="result-metric"><strong>${r.total}</strong><span>题目总数</span></div><div class="result-metric"><strong style="color:var(--success)">${r.correct}</strong><span>回答正确</span></div><div class="result-metric"><strong style="color:var(--error)">${r.wrong}</strong><span>回答错误</span></div><div class="result-metric"><strong>${r.accuracy}%</strong><span>正确率</span></div></div><div class="actions" style="justify-content:center"><a class="btn btn-primary" href="/review" data-link>继续复习</a><a class="btn" href="/points" data-link>查看 Point</a></div></div>
  <div class="section-top"><h2>本轮 Point</h2></div><div class="card card-pad">${r.items.map(item=>`<div class="result-item"><div><a class="point-title" href="/points/${item.point_id}" data-link>${esc(item.title)}</a><div class="subtle" style="margin-top:5px">${item.is_correct?'回答正确':'回答错误 · 正确答案 '+esc(item.correct_option)}</div></div><span class="badge ${item.is_correct?'badge-green':''}">${item.is_correct?'正确':'错误'}</span><span class="transition">${item.mastery_before??'未评估'} → ${item.mastery_after} 星</span></div>`).join('')}</div></div>`, 'review');
}

document.addEventListener('click',event=>{const link=event.target.closest('a[data-link]');if(!link||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;event.preventDefault();nav(link.getAttribute('href'));});
window.addEventListener('popstate',render);
render();
