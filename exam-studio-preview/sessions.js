'use strict';
const SESSION_KEY='exam-studio-attempts-v1';
const sessionNames={manipulation:'Data Manipulation',interpretation:'Data Interpretation',combined:'Combined'};
const examFiles={'NYC_Film_Permits.xlsx':'Film Permits workbook','songs.db':'Songs database','Chinook_Sqlite.sqlite':'Chinook database','movies.db':'Movies database'};
let session=null,sessionQuestion=0,reviewAttempt=null,reviewQuestion=0,sessionHistory=[],sessionSaving=null,sessionDirty=false,sessionSubmitting=false;
let clockBase=0,clockRemaining=0,sessionSyncing=false;
const sessionFields=['answer','method','output'];
function attemptQuestion(a,id){return a.question_snapshot?.[id]||questions.find(item=>item.id===id);}
let restoredActive=null;
try {
  const value=JSON.parse(localStorage.getItem(SESSION_KEY)||'{}');
  const valid=a=>a&&typeof a.id==='string'&&sessionNames[a.kind]&&Array.isArray(a.question_ids)&&a.question_ids.length<=10&&a.question_ids.every(id=>questions.some(q=>q.id===id))&&a.answers&&typeof a.answers==='object';
  if(valid(value.active))restoredActive=value.active;
  if(Array.isArray(value.history))sessionHistory=value.history.filter(valid).slice(0,20);
} catch { /* Storage failure is disclosed when saving. */ }
window.isSimulationActive=()=>session?.state==='active'&&session.mode==='simulation';

function renderRoute(moveFocus=false){
  const [requested,subpage,questionId]=location.hash.slice(1).split('/');
  const active=session?.state==='active';
  if(active&&location.hash!=='#'+session.kind+'/exams')history.replaceState(null,'','#'+session.kind+'/exams');
  const kind=active?session.kind:(Object.hasOwn(sessionNames,requested)?requested:null);
  const view=active||kind==='combined'?'exams':subpage;
  const detail=view==='question'&&questions.find(q=>q.id===questionId&&(q.category||'Data Manipulation')===sessionNames[kind]);
  const showQuestions=!!kind&&(view==='questions'||view==='question');
  const showExams=!!kind&&view==='exams';
  byId('home-view').hidden=!!kind;
  byId('section-view').hidden=!kind;
  byId('section-choices').hidden=!kind||showQuestions||showExams;
  byId('timed-sessions').hidden=!showExams;
  byId('individual-practice').hidden=!showQuestions;
  byId('question-catalogue').hidden=!!detail;
  byId('practice-progress-panel').hidden=!!detail;
  byId('question-detail').hidden=!detail;
  if(!kind){
    if(moveFocus)byId('home-heading').focus();
    return;
  }
  byId('section-heading').textContent=sessionNames[kind];
  byId('section-eyebrow').textContent=showQuestions?'QUESTION PRACTICE':showExams?'EXAM PRACTICE':'CHOOSE HOW TO PRACTISE';
  byId('section-lede').hidden=!!detail;
  byId('section-lede').textContent=kind==='combined'?'Start a 13-minute exam covering both sections.':showQuestions?'Find an exercise to work through at your own pace.':'Choose individual practice or a timed exam.';
  const back=byId('section-back');
  back.hidden=active||kind==='combined'||(!showQuestions&&!showExams);
  back.href='#'+kind+(detail?'/questions':'');
  back.textContent=detail?'← Question list':'← '+sessionNames[kind]+' overview';
  byId('section-questions-link').href='#'+kind+'/questions';
  byId('section-exams-link').href='#'+kind+'/exams';
  if(showExams){
    byId('session-kind').value=kind;
    updateComposition();
  }
  if(showQuestions){
    const category=sessionNames[kind];
    if(byId('category-filter').value!==category){
      byId('category-filter').value=category;
      clearFilters();
    }
    const currentCategory=questions[currentIndex].category||'Data Manipulation';
    if(detail)showQuestion(questions.indexOf(detail),false,true);
    else if(currentCategory!==category)showQuestion(questions.findIndex(q=>(q.category||'Data Manipulation')===category),false,false);
    renderPracticeSets();
  }
  if(moveFocus)byId(detail?'question-region':'section-heading').focus();
}

function openQuestionSection(q,replace=false){
  const kind=q.category==='Data Interpretation'?'interpretation':'manipulation';
  const hash='#'+kind+'/question/'+q.id;
  if(location.hash!==hash){
    if(replace)history.replaceState(null,'',hash);
    else history.pushState(null,'',hash);
  }
  renderRoute(true);
}

window.addEventListener('hashchange',()=>{
  reviewAttempt=null;
  renderSessionState();
  renderRoute(true);
});
for(const kind of ['manipulation','interpretation']){
  const count=questions.filter(q=>(q.category||'Data Manipulation')===sessionNames[kind]).length;
  byId('home-'+kind+'-count').textContent=count+' practice questions';
}
function sessionNotice(text){byId('session-status').textContent=text;}
function persistSessions(){
  try{localStorage.setItem(SESSION_KEY,JSON.stringify({active:session?.state==='active'?{...session,client_question_index:sessionQuestion}:null,history:sessionHistory.slice(0,20)}));}
  catch{sessionNotice('Browser storage is unavailable or full. Keep this page open; this attempt may not survive a refresh.');}
}
function archiveSession(a){sessionHistory=[JSON.parse(JSON.stringify(a)),...sessionHistory.filter(old=>old.id!==a.id)].slice(0,20);persistSessions();}
function setSessionClock(result){
  clockRemaining=result.attempt?.deadline==null?null:Math.max(0,(result.attempt.deadline-result.server_now)*1000);
  clockBase=performance.now();
}
function updateComposition(){
  const kind=byId('session-kind').value,simulation=byId('session-mode').value==='simulation';
  byId('session-timed').disabled=simulation;
  const exams=connection.exams?.[kind]||[];
  const picker=byId('session-exam'), selected=picker.value;
  picker.replaceChildren(...exams.map(exam=>new Option(exam.title,exam.id)));
  if(exams.some(exam=>exam.id===selected))picker.value=selected;
  byId('session-exam-controls').hidden=!exams.length;
  byId('choose-exam').hidden=exams.length<2;
  byId('session-composition').textContent=kind==='interpretation'?'Four regression-output questions, each with its own model.':kind==='manipulation'?'Six questions: three Excel tasks and three SQL tasks.':'Ten questions: six Excel and SQL tasks followed by four regression-output questions.';
  const files=byId('session-files');files.replaceChildren();
  const selectedFiles=exams.find(exam=>exam.id===picker.value)?.files||['NYC_Film_Permits.xlsx','songs.db'];
  if(kind!=='interpretation'&&connection.public_site){
    files.append(element('p','Open from your course materials: '+selectedFiles.map(name=>connection.course_files?.[name]||name).join(' and '),'helper'));
  }else if(kind!=='interpretation')for(const filename of selectedFiles){if(!Object.hasOwn(examFiles,filename))continue;const link=element('a',examFiles[filename],'download');link.href='files/'+filename;link.download='';files.append(link);}
  else files.append(element('p','All model output is supplied on screen; no dataset download is required.','helper'));
}
function applySessionResult(result,replaceAnswers=true){
  if(!result.attempt)return;
  const incoming=result.attempt;
  if(!replaceAnswers&&session?.id===incoming.id&&incoming.state==='active')incoming.answers=session.answers;
  session=incoming;setSessionClock(result);persistSessions();
  if(session.state!=='active'){
    archiveSession(session);reviewAttempt=session;session=null;renderSessionReview();
  }
  renderSessionState();
}
function renderSessionState(){
  const active=session?.state==='active';
  byId('session-setup').hidden=active||!!reviewAttempt;
  byId('session-active').hidden=!active;
  byId('session-review').hidden=!reviewAttempt||active;
  byId('session-submit-confirm').hidden=true;
  renderRoute();
  if(active){
    byId('session-label').textContent=`${session.exam_title||sessionNames[session.kind]} · ${session.mode==='simulation'?'Exam Simulation':'Practice'}`;
    byId('session-rules').textContent=session.mode==='simulation'?'AI is disabled until submission. The deadline keeps running during navigation and refresh. At expiry, the most recently server-saved answers are submitted automatically.':'AI is available when requested. An optional timer is a practice target; reaching zero does not submit your work.';
    sessionQuestion=Math.min(sessionQuestion,session.question_ids.length-1);renderSessionQuestion();
  }
  updateControls();tickSessionClock();
}
function renderSessionQuestion(){
  const q=attemptQuestion(session,session.question_ids[sessionQuestion]);
  const nav=byId('session-questions');nav.replaceChildren();
  session.question_ids.forEach((id,index)=>{const button=element('button',String(index+1));button.type='button';button.setAttribute('aria-label',`Session question ${index+1}`);if(index===sessionQuestion)button.setAttribute('aria-current','step');button.addEventListener('click',()=>{sessionQuestion=index;persistSessions();renderSessionQuestion();byId('session-question').focus();});nav.append(button);});
  byId('session-q-category').textContent=`${q.category||'Data Manipulation'} · ${q.id}`;
  byId('session-q-title').textContent=q.title;byId('session-q-prompt').textContent=q.prompt;
  byId('session-q-scope').textContent=q.model?'Use this question’s supplied model only. No model fitting is needed.':q.tool==='SQL'?[q.dataset,q.scope_note,q.output_requirement].filter(Boolean).join(' · '):(q.source_index>9?'Use only Shooting Permit records, as required by source question 9.':'Use all Film Permits records. Show how you obtained your answer.');
  renderModel(q,byId('session-model'));
  sessionFields.forEach(field=>{byId(`session-${field}`).value=session.answers[q.id]?.[field]||'';byId(`session-${field}`).disabled=sessionSubmitting;});
  byId('session-help').hidden=session.mode==='simulation';
  updateSessionRevision();
}
function updateSessionRevision(){
  if(!session)return;
  const id=session.question_ids[sessionQuestion],marked=!!progress.revision[id];
  byId('session-revision').textContent=marked?'★ Marked for revision':'☆ Mark for revision';byId('session-revision').setAttribute('aria-pressed',String(marked));
}
async function flushSessionSave(){
  if(sessionSaving)return sessionSaving;
  sessionSaving=(async()=>{
    while(sessionDirty&&session?.state==='active'){
      sessionDirty=false;const id=session.id;const answers=JSON.parse(JSON.stringify(session.answers));
      try{
        const result=await api('/api/attempt/save',{id,answers});
        if(result.attempt?.state!=='active'){applySessionResult(result);break;}
      }catch(error){sessionDirty=true;sessionNotice(`${error.message} Your latest draft is kept in this browser; it is not yet confirmed saved by the server.`);break;}
    }
  })().finally(()=>{sessionSaving=null;});
  return sessionSaving;
}
sessionFields.forEach(field=>byId(`session-${field}`).addEventListener('input',()=>{
  if(!session||sessionSubmitting)return;
  const id=session.question_ids[sessionQuestion];session.answers[id]=Object.fromEntries(sessionFields.map(name=>[name,byId(`session-${name}`).value]));
  sessionDirty=true;persistSessions();flushSessionSave();
}));
async function finishSession(expired=false,confirmed=false){
  if(!session||sessionSubmitting)return;
  if(!expired&&!confirmed){byId('session-submit-confirm').hidden=false;byId('confirm-session-submit').focus();return;}
  byId('session-submit-confirm').hidden=true;
  sessionSubmitting=true;byId('submit-session').disabled=true;sessionFields.forEach(f=>byId(`session-${f}`).disabled=true);
  try{
    await flushSessionSave();if(!session)return;
    const result=await api('/api/attempt/submit',{id:session.id,answers:session.answers});
    applySessionResult(result);sessionNotice(expired?'Time is up. Your server-saved answers are submitted for independent review.':'Submitted. Review your answers before choosing whether to request AI feedback.');
  }catch(error){sessionNotice(`${error.message} Your browser draft remains saved. Retry submission when the server is available.`);}
  finally{sessionSubmitting=false;byId('submit-session').disabled=false;if(session)renderSessionQuestion();}
}
async function syncSession(){
  if(!session||sessionSyncing||sessionSubmitting||sessionSaving)return;
  sessionSyncing=true;
  try{if(sessionDirty)await flushSessionSave();if(!session)return;const result=await api('/api/attempt/status',{id:session.id});if(result.attempt?.state!=='active')applySessionResult(result);else setSessionClock(result);}
  catch(error){sessionNotice(error.message);}
  finally{sessionSyncing=false;}
}
function tickSessionClock(){
  if(!session)return;
  if(clockRemaining===null){byId('session-clock').textContent='Untimed practice';return;}
  const remaining=Math.max(0,clockRemaining-(performance.now()-clockBase)),seconds=Math.ceil(remaining/1000);
  byId('session-clock').textContent=`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;
  if(!seconds){
    if(session.mode==='simulation')finishSession(true);
    else byId('session-clock').textContent='Time target reached · continue practising';
  }
}
function renderSessionReview(){
  if(!reviewAttempt)return;
  byId('session-review').hidden=false;byId('session-setup').hidden=true;
  byId('review-summary').textContent=`${sessionNames[reviewAttempt.kind]} · ${reviewAttempt.mode==='simulation'?'Simulation':'Practice'} · ${reviewAttempt.reason==='time-expired'?'Time expired':reviewAttempt.reason==='interrupted'?'Interrupted — browser recovery copy':'Submitted'} · ${new Date((reviewAttempt.submitted_at||reviewAttempt.started_at)*1000).toLocaleString()}`;
  const select=byId('review-attempt');select.replaceChildren();sessionHistory.forEach(a=>{const option=element('option',`${sessionNames[a.kind]} · ${new Date((a.submitted_at||a.started_at)*1000).toLocaleString()}`);option.value=a.id;select.append(option);});select.value=reviewAttempt.id;
  reviewQuestion=Math.min(reviewQuestion,reviewAttempt.question_ids.length-1);
  const nav=byId('review-questions');nav.replaceChildren();reviewAttempt.question_ids.forEach((id,index)=>{const button=element('button',String(index+1));button.type='button';button.setAttribute('aria-label',`Review question ${index+1}`);if(index===reviewQuestion)button.setAttribute('aria-current','step');button.addEventListener('click',()=>{reviewQuestion=index;renderSessionReview();});nav.append(button);});
  const q=attemptQuestion(reviewAttempt,reviewAttempt.question_ids[reviewQuestion]);byId('review-title').textContent=`${q.id} · ${q.title}`;byId('review-prompt').textContent=q.prompt;renderModel(q,byId('review-model'));
  const answer=reviewAttempt.answers[q.id]||{};byId('review-answer').textContent=sessionFields.map(field=>`${field.toUpperCase()}\n${answer[field]||'(No answer submitted)'}`).join('\n\n');
  byId('show-review-reference').hidden=!questions.find(item=>item.id===q.id)?.has_reference;byId('review-reference').replaceChildren();byId('review-reference-status').textContent='';
  const marked=!!progress.revision[q.id];byId('review-revision').textContent=marked?'★ Marked for revision':'☆ Mark for revision';byId('review-revision').setAttribute('aria-pressed',String(marked));
}
function requestSessionFeedback(a,index){
  if(pending.size){sessionNotice('Wait for the current AI reply before requesting another.');return;}
  const id=a.question_ids[index],q=questions.find(item=>item.id===id),answer=a.answers[id]||{};
  if(a.state==='active'){
    byId('category-filter').value=q.category||'Data Manipulation';
    byId('individual-practice').hidden=false;
    byId('question-catalogue').hidden=true;
    byId('practice-progress-panel').hidden=true;
    byId('question-detail').hidden=false;
  }else{
    openQuestionSection(q);
  }
  clearFilters();showQuestion(questions.indexOf(q),true);
  const text=`Please review my ${a.state==='active'?'practice work':'submitted answer'} for ${q.id}, included as attached work. Give targeted guidance and distinguish reasoning review from executed verification.`;
  feedbackAttachments.set(id,{text,work:Object.fromEntries(sessionFields.map(field=>[field,answer[field]||''])),question_snapshot:attemptQuestion(a,id)});
  byId('tutor-message').value=text;messageDrafts.set(id,text);persist();
  updateControls();
  if(connection.configured)byId('message-form').requestSubmit();
  else if(connection.provider==='cloudflare'){byId('tutor-status').textContent='The tutor is unavailable. Your feedback request is saved as a draft.';}
  else{byId('connection-settings').open=true;byId('tutor-status').textContent='Reconnect Gemini, then send the prepared feedback request.';}
  byId('tutor-message').focus();
}
byId('session-start-form').addEventListener('submit',async event=>{
  event.preventDefault();if(session||pending.size||settingsBusy){sessionNotice('Wait for the current request or submit the active attempt first.');return;}
  byId('start-session').disabled=true;
  try{
    const result=await api('/api/attempt/start',{kind:byId('session-kind').value,exam_id:byId('session-exam').value||undefined,mode:byId('session-mode').value,timer_enabled:byId('session-timed').checked});
    reviewAttempt=null;sessionQuestion=0;sessionDirty=false;applySessionResult(result);sessionNotice('Session started. Your answers are saved locally and sent to this local server, not to AI, as you type.');byId('session-question').focus();
  }catch(error){sessionNotice(error.message);}
  finally{byId('start-session').disabled=false;}
});
byId('submit-session').addEventListener('click',()=>finishSession(false));
byId('confirm-session-submit').addEventListener('click',()=>finishSession(false,true));
byId('cancel-session-submit').addEventListener('click',()=>{byId('session-submit-confirm').hidden=true;byId('submit-session').focus();});
byId('session-revision').addEventListener('click',()=>{const id=session.question_ids[sessionQuestion];changeProgress('revision',id,!progress.revision[id]);updateSessionRevision();});
byId('review-revision').addEventListener('click',()=>{const id=reviewAttempt.question_ids[reviewQuestion];changeProgress('revision',id,!progress.revision[id]);renderSessionReview();});
byId('session-help').addEventListener('click',()=>{if(session?.mode==='practice')requestSessionFeedback(session,sessionQuestion);});
byId('review-ai').addEventListener('click',()=>{if(reviewAttempt&&reviewAttempt.state!=='active')requestSessionFeedback(reviewAttempt,reviewQuestion);});
byId('show-review-reference').addEventListener('click',async()=>{
  if(!reviewAttempt||session)return;
  const attemptId=reviewAttempt.id,id=reviewAttempt.question_ids[reviewQuestion];byId('show-review-reference').disabled=true;
  try{const result=await api('/api/reference',{question_id:id,question_snapshot:attemptQuestion(reviewAttempt,id)});if(reviewAttempt.id===attemptId&&reviewAttempt.question_ids[reviewQuestion]===id){renderReference(result.reference,byId('review-reference'));byId('review-reference-status').textContent='Reference shown at your request. Your submitted answer is unchanged.';}}
  catch(error){byId('review-reference-status').textContent=error.message;}
  finally{byId('show-review-reference').disabled=false;}
});
byId('review-attempt').addEventListener('change',()=>{reviewAttempt=sessionHistory.find(a=>a.id===byId('review-attempt').value);reviewQuestion=0;renderSessionReview();});
byId('new-session').addEventListener('click',()=>{reviewAttempt=null;renderSessionState();sessionNotice('Choose a new session. Previous submissions remain saved in this browser.');});
['session-kind','session-mode','session-exam'].forEach(id=>byId(id).addEventListener('change',updateComposition));
byId('choose-exam').addEventListener('click',()=>{
  const picker=byId('session-exam');
  const alternatives=Array.from(picker.options).filter(option=>option.value!==picker.value);
  if(!alternatives.length)return;
  picker.value=alternatives[Math.floor(Math.random()*alternatives.length)].value;
  updateComposition();
});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)syncSession();});window.addEventListener('focus',syncSession);
setInterval(tickSessionClock,1000);setInterval(syncSession,10000);
async function initialiseSessions(){
  updateComposition();
  try{
    let result;
    if(restoredActive){
      if(Number.isInteger(restoredActive.client_question_index))sessionQuestion=Math.max(0,Math.min(restoredActive.client_question_index,restoredActive.question_ids.length-1));
      try{result=await api('/api/attempt/status',{id:restoredActive.id});if(result.attempt?.state==='active'&&JSON.stringify(restoredActive.answers)!==JSON.stringify(result.attempt.answers)){result.attempt.answers=restoredActive.answers;sessionDirty=true;}}
      catch{archiveSession({...restoredActive,state:'interrupted',reason:'interrupted',submitted_at:Date.now()/1000});sessionNotice('The previous local session was interrupted. Its browser-saved answers are retained as a recovery copy.');}
    }
    if(!result)result=await api('/api/attempt/current',{});
    if(result.attempt){applySessionResult(result);if(sessionDirty)flushSessionSave();}
  }catch(error){sessionNotice(`Timed sessions are unavailable: ${error.message}`);}
}
updateComposition();
renderRoute();
if(connection.token)initialiseSessions();else window.addEventListener('tutor-ready',initialiseSessions,{once:true});

byId('show-saved-sessions').addEventListener('click',()=>{if(!sessionHistory.length){sessionNotice('There are no saved submissions yet.');return;}reviewAttempt=sessionHistory[0];reviewQuestion=0;renderSessionReview();renderSessionState();});
