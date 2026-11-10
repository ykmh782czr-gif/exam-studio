'use strict';
// BEGIN SAFE_FORMATTING
// A bounded MathML renderer. Unsupported notation stays visible as literal text.
function renderTutorMath(source,display=false){
  const namespace='http://www.w3.org/1998/Math/MathML';let position=0,budget=0;
  if(source.length>2000)throw new Error('Formula too long');
  const tag=(name,...children)=>{if(++budget>600)throw new Error('Formula too complex');const node=document.createElementNS(namespace,name);children.forEach(child=>node.append(typeof child==='string'?document.createTextNode(child):child));return node;};
  const symbols={alpha:'α',beta:'β',gamma:'γ',delta:'δ',epsilon:'ε',theta:'θ',lambda:'λ',mu:'μ',pi:'π',rho:'ρ',sigma:'σ',tau:'τ',phi:'φ',chi:'χ',omega:'ω',Sigma:'Σ',Delta:'Δ',times:'×',cdot:'·',le:'≤',leq:'≤',ge:'≥',geq:'≥',ne:'≠',neq:'≠',approx:'≈',pm:'±',infty:'∞',sum:'∑',in:'∈',to:'→'};
  function skip(){while(/\s/.test(source[position]||'')&&position<source.length)position++;}
  function textGroup(){skip();if(source[position++]!=='{')throw new Error('Expected text group');let depth=1,text='';while(position<source.length&&depth){const c=source[position++];if(c==='\\'&&/[{}$%_]/.test(source[position]||'')){text+=source[position++];continue;}if(c==='{')depth++;if(c==='}')depth--;if(depth)text+=c;}if(depth)throw new Error('Unclosed text');return text;}
  function argument(depth){skip();if(source[position]==='{'){position++;return row(depth+1,true);}return atom(depth+1);}
  function atom(depth){
    if(depth>24)throw new Error('Formula nesting too deep');skip();const c=source[position++];if(c===undefined)throw new Error('Missing term');
    if(c==='{')return row(depth+1,true);
    if(c==='\\'){
      const command=/^[A-Za-z]+/.exec(source.slice(position));
      if(!command){const escaped=source[position++];if([',',';','!',' '].includes(escaped))return tag('mspace');if(['$','%','_','{','}'].includes(escaped))return tag('mo',escaped);throw new Error('Unsupported escape');}
      position+=command[0].length;const name=command[0];
      if(name==='text'||name==='operatorname')return tag('mtext',textGroup());
      if(name==='frac')return tag('mfrac',argument(depth),argument(depth));
      if(name==='sqrt')return tag('msqrt',argument(depth));
      if(name==='hat'||name==='bar'||name==='overline')return tag('mover',argument(depth),tag('mo',name==='hat'?'^':'¯'));
      if(name==='left'||name==='right')return atom(depth);
      if(name==='mathrm'||name==='mathbf'||name==='mathit'){const styled=tag('mstyle',argument(depth));styled.setAttribute('mathvariant',name==='mathbf'?'bold':name==='mathit'?'italic':'normal');return styled;}
      if(Object.hasOwn(symbols,name))return tag(['times','cdot','le','leq','ge','geq','ne','neq','approx','pm','sum','in','to'].includes(name)?'mo':'mi',symbols[name]);
      throw new Error('Unsupported notation');
    }
    if(/[0-9.]/.test(c)){
      const rest=/^(?:\d+(?:,\d{3})*(?:\.\d+)?|\.\d+)/.exec(source.slice(position-1));
      if(rest){position=position-1+rest[0].length;return tag('mn',rest[0]);}
    }
    if(/[A-Za-z]/.test(c)){const rest=/^[A-Za-z]+/.exec(source.slice(position-1))[0];position=position-1+rest.length;return tag('mi',rest);}
    if(c==='}')throw new Error('Unexpected brace');
    return tag('mo',c);
  }
  function row(depth,group=false){
    if(depth>24)throw new Error('Formula nesting too deep');const nodes=[];
    while(position<source.length){
      skip();if(position>=source.length)break;
      if(source[position]==='}'){if(!group)throw new Error('Unexpected brace');position++;return tag('mrow',...nodes);}
      if(source[position]==='_'||source[position]==='^'){
        const kind=source[position++],base=nodes.pop();if(!base)throw new Error('Missing script base');const script=argument(depth);
        if(kind==='^'&&base.localName==='msub')nodes.push(tag('msubsup',...Array.from(base.childNodes),script));
        else if(kind==='_'&&base.localName==='msup'){const parts=Array.from(base.childNodes);nodes.push(tag('msubsup',parts[0],script,parts[1]));}
        else nodes.push(tag(kind==='_'?'msub':'msup',base,script));
      }else nodes.push(atom(depth));
    }
    if(group)throw new Error('Unclosed group');return tag('mrow',...nodes);
  }
  const math=tag('math',row(0));math.setAttribute('display',display?'block':'inline');return math;
}
function appendTutorInline(container,text,depth=0){
  if(depth>8){container.append(document.createTextNode(text));return;}
  const pattern=/(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+?\$|`[^`\n]+`|\*\*[^*\n]+?\*\*|\*[^*\n]+?\*)/g;
  let last=0;
  for(const match of text.matchAll(pattern)){
    container.append(document.createTextNode(text.slice(last,match.index)));const token=match[0];let node;
    if(token.startsWith('`')){node=document.createElement('code');node.textContent=token.slice(1,-1);}
    else if(token.startsWith('**')||token.startsWith('*')){const n=token.startsWith('**')?2:1;node=document.createElement(n===2?'strong':'em');appendTutorInline(node,token.slice(n,-n),depth+1);}
    else{
      const block=token.startsWith('$$')||token.startsWith('\\['),n=block||token.startsWith('\\(')?2:1;const formula=token.slice(n,-n);
      // A currency amount is not a math delimiter, and must stay intact.
      if(n===1&&!/[=+*/_^\\×<>−]/.test(formula)&&!/^\s*[A-Za-z]\s*$/.test(formula)){node=document.createTextNode(token);}
      else try{node=renderTutorMath(formula,block);}catch{node=document.createElement('code');node.className='math-literal';node.textContent=token;}
    }
    container.append(node);last=match.index+token.length;
  }
  container.append(document.createTextNode(text.slice(last)));
}
function renderTutorContent(container,text){
  container.replaceChildren();const blocks=/```([^\n`]*)\n([\s\S]*?)```/g;let last=0;
  function prose(value){
    for(const paragraph of value.split(/\n\s*\n/).filter(v=>v.trim())){
      const lines=paragraph.trim().split('\n');const ordered=lines.every(line=>/^\d+\.\s/.test(line)),unordered=lines.every(line=>/^[-*]\s/.test(line));
      if(ordered||unordered){const list=document.createElement(ordered?'ol':'ul');for(const line of lines){const item=document.createElement('li');appendTutorInline(item,line.replace(ordered?/^\d+\.\s/:/^[-*]\s/,''));list.append(item);}container.append(list);}
      else{const p=document.createElement('p');appendTutorInline(p,paragraph.replace(/^#{1,4}\s/,''));container.append(p);}
    }
  }
  for(const match of text.matchAll(blocks)){prose(text.slice(last,match.index));const pre=document.createElement('pre'),code=document.createElement('code');code.textContent=match[2];pre.append(code);container.append(pre);last=match.index+match[0].length;}
  prose(text.slice(last));
}
// END SAFE_FORMATTING
const questions = window.EXAM_QUESTIONS;
const byId = id => document.getElementById(id);
const STORAGE_KEY = 'exam-studio-learning-v2';
let saved = {};
let storageOK = true;
try {
  const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  if (stored && typeof stored === 'object' && !Array.isArray(stored)) saved = stored;
} catch { storageOK = false; }
const drafts = new Map();
const chats = new Map();
const messageDrafts = new Map();
const feedbackAttachments = new Map();
const pending = new Set();
let connection = {configured:false, token:'', model:''};
let settingsBusy = false;
let currentIndex = 0;
const fields = ['answer', 'method', 'output'];
const PROGRESS_KEY = 'exam-studio-progress-v1';
const STATUSES = {'not-started':'Not started','in-progress':'In progress','completed':'Completed'};
const practiceSets = [
  {id:'film-permits-v1',title:'PWC · Film permits',description:'20 original Excel questions',ids:questions.filter(q=>q.id.startsWith('PWC-EXCEL-')).map(q=>q.id)},
  {id:'songs-intro-v1',title:'CS50 · Songs introduction',description:'1 original SQL question · introductory sample',ids:['CS50-SONGS-001']},
  {id:'songs-full-v1',title:'CS50 · Songs full assignment',description:'8 original SQL questions',ids:questions.filter(q=>q.id.startsWith('CS50-SONGS-')).map(q=>q.id)},
  {id:'chinook-checked-v1',title:'PWC · Chinook introduction',description:'7 original SQL questions · introductory sample',ids:['001','004','005','006','008','009','015'].map(id=>'CHINOOK-'+id)},
  {id:'chinook-full-v1',title:'PWC · Chinook full assignment',description:'23 original SQL questions',ids:questions.filter(q=>q.id.startsWith('CHINOOK-')).map(q=>q.id)},
  {id:'movies-v1',title:'CS50 · Movies',description:'13 course SQL questions',ids:questions.filter(q=>q.id.startsWith('CS50-MOVIES-')).map(q=>q.id)},
  {id:'pcards-controls-v1',title:'P-Cards · Spending controls',description:'4 course SQL questions',ids:questions.filter(q=>q.id.startsWith('PCARD-')).map(q=>q.id)},
  {id:'etl-v1',title:'ETL · Clean and combine data',description:'8 exercises from four course cases',ids:questions.filter(q=>q.id.startsWith('ETL-')).map(q=>q.id)},
  {id:'integrateco-v1',title:'IntegrateCo · Payroll',description:'5 exercises from the payroll case',ids:questions.filter(q=>q.id.startsWith('INT-')).map(q=>q.id)},
  {id:'restaurant-output-v1',title:'Restaurant · Model interpretation introduction',description:'4 adapted regression-output questions',ids:['REST-REG-P','REST-REG-S','REST-REG-Q','REST-REG-I']},
  {id:'restaurant-expanded-v1',title:'Restaurant · Additional model interpretation',description:'36 adapted regression-output questions',ids:questions.filter(q=>q.id.startsWith('REST-EXAM-')).map(q=>q.id)}
];
let progress = readProgress();
let progressStored = true;
let cataloguePage = 1;
const PAGE_SIZE = 6;
let matchingQuestions = [...questions];
function readProgress() {
  const clean={sets:{},revision:{},last:{}};
  try {
    const value=JSON.parse(localStorage.getItem(PROGRESS_KEY)||'{}');
    if(value && typeof value==='object') {
      practiceSets.forEach(set=>{if(Object.hasOwn(STATUSES,value.sets?.[set.id]))clean.sets[set.id]=value.sets[set.id];});
      questions.forEach(q=>{if(value.revision?.[q.id]===true)clean.revision[q.id]=true;});
      practiceSets.forEach(set=>{if(set.ids.includes(value.last?.[set.id]))clean.last[set.id]=value.last[set.id];});
    }
  } catch { /* Keep local changes available even when storage is disabled. */ }
  return clean;
}
function changeProgress(kind,id,value) {
  // Merge the latest saved changes rather than overwriting another tab's markers.
  let latest;
  try {localStorage.getItem(PROGRESS_KEY);latest=progressStored?readProgress():progress;}catch{latest=progress;}
  latest[kind][id]=value;
  if(kind==='sets' && value==='not-started')delete latest.last[id];
  progress=latest;
  try {localStorage.setItem(PROGRESS_KEY,JSON.stringify(progress));progressStored=true;byId('progress-status').textContent='Progress saved in this browser. It does not sync between devices.';}
  catch {progressStored=false;byId('progress-status').textContent='Browser storage is unavailable or full. This progress change is kept only while the page stays open.';}
  renderPracticeSets();renderCatalogue();updateQuestionNavigation();
}
function element(tag,text,className) {
  const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;
}
function renderPracticeSets() {
  const container=byId('practice-sets');container.replaceChildren();
  practiceSets.forEach(set=>{
    const category=byId('category-filter').value;
    if(category&&!questions.some(q=>set.ids.includes(q.id)&&(q.category||'Data Manipulation')===category))return;
    const state=progress.sets[set.id]||'not-started';
    const card=element('article',undefined,'practice-set');
    const top=element('div',undefined,'set-heading');
    top.append(element('h3',set.title),element('span',(state==='completed'?'✓ ':'')+STATUSES[state],`set-status ${state}`));
    const count=set.ids.filter(id=>progress.revision[id]).length;
    const info=element('p',`${set.description} · ${count} marked for revision`,'helper');
    const actions=element('div',undefined,'set-actions');
    const open=element('button',state==='not-started'?'Start practice':state==='in-progress'?'Resume practice':'Review practice');open.type='button';
    open.setAttribute('aria-label',`${open.textContent}: ${set.title}`);
    open.addEventListener('click',()=>{
      if(state==='not-started')changeProgress('sets',set.id,'in-progress');
      clearFilters();openQuestionSection(questions.find(q=>q.id===(progress.last[set.id]||set.ids[0])));
    });
    const complete=element('button','Mark completed');complete.type='button';complete.disabled=state==='completed';complete.setAttribute('aria-label',`Mark completed: ${set.title}`);
    complete.addEventListener('click',()=>changeProgress('sets',set.id,'completed'));
    const label=element('label','Set status');label.htmlFor=`status-${set.id}`;
    const select=element('select');select.id=`status-${set.id}`;select.setAttribute('aria-label',`Status for ${set.title}`);
    Object.entries(STATUSES).forEach(([key,value])=>{const option=element('option',value);option.value=key;select.append(option);});
    select.value=state;select.addEventListener('change',()=>changeProgress('sets',set.id,select.value));
    actions.append(open,complete);card.append(top,info,actions,label,select);container.append(card);
  });
}
function filteredQuestions() {
  const terms=byId('question-search').value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return questions.filter(q=>{
    const tool=q.tool||'Excel';
    const text=[q.id,q.title,q.prompt,q.skill,tool,q.category||'Data Manipulation',q.case||'PWC Film permits'].join(' ').toLocaleLowerCase();
    return (!byId('category-filter').value||(q.category||'Data Manipulation')===byId('category-filter').value) && (!byId('tool-filter').value||tool===byId('tool-filter').value) && (!byId('topic-filter').value||q.skill===byId('topic-filter').value) && (!byId('revision-only').checked||progress.revision[q.id]) && terms.every(term=>text.includes(term));
  });
}
function renderCatalogue() {
  matchingQuestions=filteredQuestions();
  byId('reset-filters').hidden=!(['question-search','tool-filter','topic-filter'].some(id=>byId(id).value)||byId('revision-only').checked);
  const pages=Math.ceil(matchingQuestions.length/PAGE_SIZE);
  cataloguePage=Math.max(1,Math.min(cataloguePage,pages||1));
  const first=(cataloguePage-1)*PAGE_SIZE;
  const category=byId('category-filter').value;
  const total=category?questions.filter(q=>(q.category||'Data Manipulation')===category).length:questions.length;
  byId('catalogue-count').textContent=matchingQuestions.length?`${matchingQuestions.length} of ${total} questions · Showing ${first+1}–${Math.min(first+PAGE_SIZE,matchingQuestions.length)} · Page ${cataloguePage} of ${pages}`:`No questions match these filters. Try another search or reset filters.`;
  const results=byId('catalogue-results');results.replaceChildren();results.setAttribute('role','list');
  matchingQuestions.slice(first,first+PAGE_SIZE).forEach(q=>{
    const card=element('article',undefined,'catalogue-question');card.setAttribute('role','listitem');
    if(q.id===questions[currentIndex].id)card.classList.add('active');
    const open=element('button',undefined,'open-question');open.type='button';open.setAttribute('aria-label',`Open ${q.id}: ${q.title}`);
    open.append(element('span',q.id,'question-id'),element('strong',q.title),element('span',`${q.tool||'Excel'} · ${q.skill}`,'helper'));
    open.addEventListener('click',()=>openQuestionSection(q));
    const revision=element('button',progress.revision[q.id]?'★ Revision':'☆ Revision','catalogue-revision');revision.type='button';revision.setAttribute('aria-label',`Mark ${q.id} for revision`);revision.setAttribute('aria-pressed',String(!!progress.revision[q.id]));
    revision.addEventListener('click',()=>changeProgress('revision',q.id,!progress.revision[q.id]));
    card.append(open,revision);results.append(card);
  });
  const numbers=byId('page-numbers');numbers.replaceChildren();
  for(let page=1;page<=pages;page++) {
    const button=element('button',String(page));button.type='button';button.setAttribute('aria-label',`Catalogue page ${page}`);
    if(page===cataloguePage)button.setAttribute('aria-current','page');
    button.addEventListener('click',()=>{cataloguePage=page;renderCatalogue();});numbers.append(button);
  }
  byId('page-previous').disabled=cataloguePage<=1;
  byId('page-next').disabled=!pages||cataloguePage>=pages;
  byId('page-jump').max=String(pages||1);byId('page-jump').value=String(cataloguePage);byId('page-jump').disabled=!pages;
  byId('page-jump-form').querySelector('button').disabled=!pages;
  byId('page-error').textContent='';
}
function updateQuestionNavigation() {
  const current=questions[currentIndex];const index=matchingQuestions.indexOf(current);
  const select=byId('question-select');select.replaceChildren();
  if(index<0) {const option=element('option','Current question is outside the filters');option.value='';option.disabled=true;option.selected=true;select.append(option);}
  matchingQuestions.forEach(q=>{const option=element('option',`${q.id} · ${q.title}`);option.value=String(questions.indexOf(q));select.append(option);});
  if(index>=0)select.value=String(currentIndex);
  select.disabled=!matchingQuestions.length;
  byId('position').textContent=index>=0?`${index+1} / ${matchingQuestions.length}`:'Outside results';
  byId('previous').disabled=index<=0;byId('next').disabled=index<0||index>=matchingQuestions.length-1;
  byId('outside-filters').textContent=index<0?'Your current question remains open to preserve your work. Open a matching result or reset filters.':'';
  const marked=!!progress.revision[current.id];byId('revision-toggle').setAttribute('aria-pressed',String(marked));byId('revision-toggle').textContent=marked?'★ Marked for revision':'☆ Mark for revision';
}
function clearFilters() {
  byId('question-search').value='';byId('tool-filter').value='';byId('topic-filter').value='';byId('revision-only').checked=false;
  cataloguePage=1;renderCatalogue();updateQuestionNavigation();
}
function storageId(q) { return `${q.id}:v1:${q.prompt}`; }
questions.forEach(q => {
  const value = saved[storageId(q)];
  if (!value || typeof value !== 'object') return;
  if (value.work && typeof value.work === 'object') drafts.set(q.id, Object.fromEntries(fields.map(id => [id, typeof value.work[id] === 'string' ? value.work[id].slice(0,12000) : ''])));
  if (Array.isArray(value.chat) && value.chat.length <= 40 && value.chat.length % 2 === 0 && value.chat.every((t,i) => t && t.role === (i % 2 ? 'model' : 'user') && typeof t.text === 'string' && t.text.length <= 12000 && (!t.work || (typeof t.work === 'object' && Object.entries(t.work).every(([k,v])=>fields.includes(k) && typeof v==='string' && v.length<=12000))))) chats.set(q.id,value.chat);
  if (typeof value.messageDraft === 'string') messageDrafts.set(q.id,value.messageDraft.slice(0,8000));
  if(value.feedback && typeof value.feedback.text==='string' && value.feedback.work && fields.every(k=>typeof value.feedback.work[k]==='string'&&value.feedback.work[k].length<=4000))feedbackAttachments.set(q.id,value.feedback);
});
function persist() {
  const value = {};
  questions.forEach(q => { value[storageId(q)] = {work:drafts.get(q.id) || {},chat:chats.get(q.id) || [],messageDraft:messageDrafts.get(q.id) || '',feedback:feedbackAttachments.get(q.id)}; });
  try { localStorage.setItem(STORAGE_KEY,JSON.stringify(value)); storageOK=true; }
  catch { storageOK=false; }
  byId('draft-status').textContent = storageOK ? 'Answers and chats are saved in this browser. Clearing browser data removes them.' : 'Browser storage is unavailable or full. Keep this page open; recent changes may not survive a refresh.';
}
function saveDraft() {
  drafts.set(questions[currentIndex].id, Object.fromEntries(fields.map(id => [id, byId(id).value])));
  persist();
}
function showQuestion(index, moveFocus = false, remember = true) {
  if (!Number.isInteger(index) || index < 0 || index >= questions.length) return;
  if (byId('question-id').textContent) {
    saveDraft();
    messageDrafts.set(questions[currentIndex].id,byId('tutor-message').value);
    persist();
  }
  currentIndex = index;
  const q = questions[index];
  byId('question-id').textContent = q.id;
  byId('question-title').textContent = q.title;
  byId('prompt').textContent = q.prompt;
  const sql=q.tool==='SQL',regression=q.tool==='Regression',excelCase=q.tool==='Excel'&&q.dataset;
  byId('question-category').textContent=q.category||'Data Manipulation';
  byId('skill').textContent = `${q.tool||'Excel'} · ${q.skill}`;
  byId('question-dataset').hidden=regression;
  renderModel(q,byId('question-model'));
  const filename=q.dataset||'NYC_Film_Permits.xlsx';
  byId('dataset-description').textContent=`${filename} · ${sql?'SQLite database':filename.endsWith('.csv')?'CSV file':'Excel workbook'}`;
  byId('dataset-download').href='files/'+filename;
  byId('dataset-download').textContent=sql?'Download database ↓':filename.endsWith('.csv')?'Download CSV ↓':'Download workbook ↓';
  const extraDownloads=byId('additional-downloads');
  extraDownloads.replaceChildren();
  for(const extra of q.additional_datasets||[]){
    const link=element('a','Download '+extra,'download');
    link.href='files/'+extra;link.download='';extraDownloads.append(link);
  }
  byId('method').placeholder=regression?'Explain the prediction or interpretation using the supplied model.':sql?'Paste your SQL query and explain your approach.':'Paste your Excel formula or explain your PivotTable steps.';
  byId('source-instructions').textContent=regression?q.adaptation:sql?`${q.output_requirement} ${q.scope_note||''} Do not modify the original database.`:excelCase?`${q.adaptation} ${q.output_requirement}`:'Use Excel formulas and PivotTables, and show how you obtained your answer. The source refers to a CSV; this preview provides the original Excel dataset available in your materials.';
  byId('scope').textContent = regression?'Use only the model output supplied for this question. You do not need to fit or run a regression.':sql?([q.scope_note,q.output_requirement].filter(Boolean).join(' ')||'Use the supplied SQLite database.'):excelCase?q.scope_note:q.source_index > 9
    ? 'Use only records where EventType is Shooting Permit. This instruction comes from source question 9 and applies to all following questions.'
    : q.source_index === 9
      ? 'Use all records for this question. Your result determines the event type to use in questions 10–20.'
      : 'Use all records in the dataset. No event-type filter applies.';
  byId('source-location').textContent = q.source_file?`${q.source_file} · ${q.source_section}`:`Assignment_01_Excel-SQL.xlsx · Excel Questions · B${q.source_row} · Original question ${q.source_index}`;
  byId('tutor-context').textContent = `${q.id} · ${q.title}`;
  byId('position').textContent = `${index + 1} / ${questions.length}`;
  byId('question-select').value = String(index);
  byId('previous').disabled = index === 0;
  byId('next').disabled = index === questions.length - 1;
  const draft = drafts.get(q.id) || {};
  fields.forEach(id => { byId(id).value = draft[id] || ''; });
  byId('tutor-message').value = messageDrafts.get(q.id) || '';
  byId('share-work').checked = false;
  byId('tutor-status').textContent = pending.has(q.id) ? 'The tutor is replying… You can switch questions while you wait.' : '';
  renderChat();
  byId('reference-solution').replaceChildren();byId('show-reference').hidden=!q.has_reference;byId('reference-status').textContent='';
  const resultIndex=matchingQuestions.indexOf(q);if(resultIndex>=0)cataloguePage=Math.floor(resultIndex/PAGE_SIZE)+1;
  const set=practiceSets.find(item=>item.ids.includes(q.id));
  if(remember && set && progress.sets[set.id] && progress.sets[set.id]!=='not-started')changeProgress('last',set.id,q.id);
  else {renderCatalogue();updateQuestionNavigation();}
  if (moveFocus) byId('question-region').focus();
}
function renderChat() {
  const q = questions[currentIndex];
  const messages = byId('messages');
  messages.replaceChildren();
  const history = chats.get(q.id) || [];
  if (!history.length) {
    const p = document.createElement('p'); p.className='helper';
    p.textContent='Ask for a hint, share your formula, or explain where you are stuck. Your follow-up replies stay with this question.';
    messages.append(p);
  }
  history.forEach(turn => {
    const item=document.createElement('div');item.className=`message ${turn.role}`;
    const label=document.createElement('strong');label.textContent=turn.role==='user'?'You':'Tutor';
    const content=document.createElement('div');content.className='message-text';if(turn.role==='model')renderTutorContent(content,turn.text);else content.textContent=turn.text;
    item.append(label,content);
    if (turn.work) { const detail=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Work shared with this message';const work=document.createElement('pre');work.textContent=fields.map(id=>`${id}: ${turn.work[id] || ''}`).join('\n');detail.append(summary,work);item.append(detail); }
    messages.append(item);
  });
  messages.scrollTop = messages.scrollHeight;
  updateControls();
}
function updateControls() {
  const q=questions[currentIndex];
  const attachment=feedbackAttachments.get(q.id);
  const attached=!!attachment&&attachment.text===byId('tutor-message').value.trim();
  byId('feedback-preview').hidden=!attached;
  byId('feedback-preview-text').textContent=attached?fields.map(k=>`${k}: ${attachment.work[k]||'(not supplied)'}`).join('\n'):'';
  byId('share-work').disabled=attached;
  byId('send').disabled=!!window.isSimulationActive?.() || !connection.configured || settingsBusy || pending.has(q.id) || pending.size>0 || (chats.get(q.id)||[]).length>=40;
  byId('clear-chat').disabled=pending.has(q.id);
  const hosted=connection.provider==='cloudflare';
  byId('connection-state').textContent=connection.configured?`Connected · ${hosted?'Cloudflare Workers AI':connection.model}`:hosted?'Hosted tutor unavailable':'Gemini not connected';
  byId('connection-settings').hidden=hosted;
  byId('disconnect').hidden=!connection.configured;
  byId('disconnect').disabled=settingsBusy || pending.size>0;
  byId('connect').disabled=settingsBusy || pending.size>0;
}
async function api(path,data) {
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),65000);
  try {
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Exam-Studio-Token':connection.token},body:JSON.stringify(data),signal:controller.signal});
    const result=await response.json();
    if (!response.ok) throw new Error(result.error || 'The request failed. Please retry.');
    return result;
  } finally { clearTimeout(timer); }
}
byId('connection-form').addEventListener('submit',async event=>{
  event.preventDefault();if(settingsBusy || pending.size) return;
  settingsBusy=true;updateControls();byId('setup-status').textContent='Checking your key and model access…';
  const key=byId('gemini-key').value.trim();
  byId('gemini-key').value='';
  try {
    const result=await api('/api/connect',{key,model:byId('gemini-model').value.trim(),free_project_confirmed:byId('free-project').checked});
    connection={...connection,...result};
    byId('setup-status').textContent='Connected. Your key is held in this local server only.';
    byId('connection-settings').open=false;
  } catch(error) { byId('setup-status').textContent=error.name==='AbortError'?'Connection timed out. You can retry.':error.message; }
  finally { settingsBusy=false;updateControls(); }
});
byId('disconnect').addEventListener('click',async()=>{
  if(settingsBusy || pending.size) return;
  settingsBusy=true;updateControls();
  try { await api('/api/disconnect',{});connection.configured=false;byId('setup-status').textContent='Key forgotten by the local server.'; }
  catch(error) { byId('setup-status').textContent=error.message; }
  finally { settingsBusy=false;updateControls(); }
});
byId('tutor-message').addEventListener('input',()=>{const id=questions[currentIndex].id;messageDrafts.set(id,byId('tutor-message').value);if(feedbackAttachments.get(id)?.text!==byId('tutor-message').value.trim())feedbackAttachments.delete(id);persist();updateControls();});
byId('message-form').addEventListener('submit',async event=>{
  event.preventDefault();
  const q=questions[currentIndex],text=byId('tutor-message').value.trim();
  if(window.isSimulationActive?.() || !text || !connection.configured || settingsBusy || pending.size || (chats.get(q.id)||[]).length>=40) return;
  saveDraft();
  const turn={role:'user',text};
  if(byId('share-work').checked) turn.work={...drafts.get(q.id)};
  if(feedbackAttachments.get(q.id)?.text===text)turn.work={...feedbackAttachments.get(q.id).work};
  const history=[...(chats.get(q.id)||[]),turn];
  pending.add(q.id);byId('tutor-status').textContent='The tutor is replying…';updateControls();
  try {
    const attached=feedbackAttachments.get(q.id);
    const result=await api('/api/chat',{question_id:q.id,messages:history,question_snapshot:attached?.text===text?attached.question_snapshot:undefined});
    chats.set(q.id,[...history,{role:'model',text:result.text}]);
    if(feedbackAttachments.get(q.id)?.text===text)feedbackAttachments.delete(q.id);
    // Preserve text typed while waiting or a draft on another question.
    if(messageDrafts.get(q.id)?.trim()===text) messageDrafts.set(q.id,'');
    persist();
    if(questions[currentIndex].id===q.id) {byId('tutor-message').value=messageDrafts.get(q.id)||'';byId('tutor-status').textContent=history.length>=39?'Conversation limit reached. Clear this conversation to start a new one.':'Reply received. You can continue the conversation.';renderChat();}
  } catch(error) {
    if(questions[currentIndex].id===q.id) byId('tutor-status').textContent=(error.name==='AbortError'?'The request timed out.':error.message)+' Your draft is kept. Send again to retry.';
  } finally {pending.delete(q.id);updateControls();}
});
byId('clear-chat').addEventListener('click',()=>{
  const q=questions[currentIndex];if(pending.has(q.id)) return;
  if((chats.get(q.id)||[]).length && !window.confirm('Clear this question’s saved conversation? Your answer and method will stay.')) return;
  chats.delete(q.id);messageDrafts.delete(q.id);feedbackAttachments.delete(q.id);byId('tutor-message').value='';persist();renderChat();byId('tutor-status').textContent='This question’s conversation is cleared.';
});
byId('question-select').addEventListener('change', event => showQuestion(Number(event.target.value), true));
function stepQuestion(offset){
  const index=matchingQuestions.indexOf(questions[currentIndex]);
  const next=index>=0&&matchingQuestions[index+offset];
  if(!next)return;
  if(document.querySelector('#session-active:not([hidden])'))showQuestion(questions.indexOf(next),true);
  else openQuestionSection(next,true);
}
byId('previous').addEventListener('click',()=>stepQuestion(-1));
byId('next').addEventListener('click',()=>stepQuestion(1));
fields.forEach(id => byId(id).addEventListener('input', saveDraft));
function renderReference(reference,container){
  container.replaceChildren();container.className='reference-solution';
  container.append(element('h4','Worked solution'),element('p',reference.answer));
  const steps=element('ol');reference.steps.forEach(text=>steps.append(element('li',text)));container.append(steps);
  if(reference.query)container.append(element('pre',reference.query));
  if(reference.sample_rows)container.append(element('pre',`Sample output (${reference.sample_rows.length} rows; not necessarily the full result)\n${reference.result_columns.join(' | ')}\n${reference.sample_rows.map(row=>row.map(value=>value===null?'NULL':String(value)).join(' | ')).join('\n')}`));
  container.append(element('p',reference.verification,'helper'));
  if(reference.limitations)container.append(element('p',reference.limitations,'helper'));
  container.append(element('p','This reference is not an automatic grade. Equivalent valid methods are acceptable.','helper'));
}
byId('show-reference').addEventListener('click',async()=>{
  if(window.isSimulationActive?.())return;
  const id=questions[currentIndex].id;byId('show-reference').disabled=true;
  try{const result=await api('/api/reference',{question_id:id});if(questions[currentIndex].id===id){renderReference(result.reference,byId('reference-solution'));byId('reference-status').textContent='Reference shown at your request.';}}
  catch(error){if(questions[currentIndex].id===id)byId('reference-status').textContent=error.message;}
  finally{byId('show-reference').disabled=false;}
});
Array.from(new Set(questions.map(q=>q.skill))).sort().forEach(skill=>{const option=element('option',skill);option.value=skill;byId('topic-filter').append(option);});
['question-search','tool-filter','topic-filter','category-filter','revision-only'].forEach(id=>byId(id).addEventListener(id==='question-search'?'input':'change',()=>{cataloguePage=1;renderCatalogue();updateQuestionNavigation();}));
byId('reset-filters').addEventListener('click',clearFilters);
byId('page-previous').addEventListener('click',()=>{cataloguePage--;renderCatalogue();});
byId('page-next').addEventListener('click',()=>{cataloguePage++;renderCatalogue();});
byId('page-jump-form').addEventListener('submit',event=>{event.preventDefault();const value=Number(byId('page-jump').value),max=Math.ceil(matchingQuestions.length/PAGE_SIZE);if(!Number.isInteger(value)||value<1||value>max){byId('page-error').textContent=`Enter a page between 1 and ${max}.`;return;}cataloguePage=value;renderCatalogue();});
byId('revision-toggle').addEventListener('click',()=>{const id=questions[currentIndex].id;changeProgress('revision',id,!progress.revision[id]);});
window.addEventListener('storage',event=>{if(event.key===PROGRESS_KEY){progress=readProgress();renderPracticeSets();renderCatalogue();updateQuestionNavigation();}});
renderPracticeSets();
showQuestion(0,false,false);
persist();
fetch('/api/status').then(response=>{if(!response.ok)throw new Error();return response.json();}).then(result=>{
  connection=result;
  if(result.provider==='cloudflare'){
    byId('preview-label').textContent='Hosted preview';
    byId('verification-note').textContent='Messages, question context and any work you choose to include are sent to Cloudflare Workers AI for feedback. The tutor reviews reasoning without running Excel or SQL. Chats stay in this browser.';
  }else{
    byId('gemini-model').value=result.model;
    byId('connection-settings').open=!result.configured;
  }
  updateControls();window.dispatchEvent(new Event('tutor-ready'));
}).catch(()=>{byId('connection-state').textContent='Tutor unavailable';byId('setup-status').textContent='Check the preview connection and reload.';});

function renderModel(q,container) {
  container.replaceChildren();if(!q.model)return;
  container.classList.add('model-output');container.append(element('p','Adapted Restaurant exercise · calculated model output','helper'),element('p',q.equation,'model-equation'));
  const definitions=element('ul');q.definitions.forEach(text=>definitions.append(element('li',text)));container.append(definitions);
  const table=element('table');table.append(element('caption',`OLS model · ${q.model.n} days · R² ${q.model.r_squared.toFixed(3)}`));
  const head=element('thead'),header=element('tr');['Parameter / term','Estimate','p-value'].forEach(text=>{const cell=element('th',text);cell.scope='col';header.append(cell);});head.append(header);table.append(head);
  const body=element('tbody');q.model.terms.forEach((term,index)=>{const row=element('tr');row.append(element('td',`b${index} · ${term.name}`),element('td',term.estimate.toFixed(6)),element('td',term.p_value<.0001?'<0.0001':term.p_value.toFixed(4)));body.append(row);});table.append(body);container.append(table);
  const detail=element('details'),summary=element('summary','Source and model assumptions');detail.append(summary,element('p',q.adaptation),element('p',q.model_notes));container.append(detail);
}
