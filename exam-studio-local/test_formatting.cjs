const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
class Node {
  constructor(name,text=''){this.localName=name;this.childNodes=[];this.attributes={};this.value=text;}
  append(...nodes){this.childNodes.push(...nodes.map(n=>typeof n==='string'?new Node(null,n):n));}
  replaceChildren(...nodes){this.childNodes=[];this.value='';this.append(...nodes);}
  setAttribute(name,value){this.attributes[name]=value;}
  set textContent(value){this.value=String(value);this.childNodes=[];}
  get textContent(){return this.value+this.childNodes.map(n=>n.textContent).join('');}
  set innerHTML(value){throw new Error('Raw HTML is forbidden');}
}
const htmlTags=new Set(['code','strong','em','p','ol','ul','li','pre']);
const document={createTextNode:text=>new Node(null,text),createElement:name=>{assert.ok(htmlTags.has(name));return new Node(name);},createElementNS:(namespace,name)=>{assert.equal(namespace,'http://www.w3.org/1998/Math/MathML');return new Node(name);}};
const source=fs.readFileSync(path.join(__dirname,'../exam-studio-preview/app.js'),'utf8').split('// BEGIN SAFE_FORMATTING')[1].split('// END SAFE_FORMATTING')[0];
const context=vm.createContext({document});vm.runInContext(source,context);
function find(node,name){return (node.localName===name?[node]:[]).concat(...node.childNodes.map(n=>find(n,name)));}
function render(text){const node=new Node('div');context.renderTutorContent(node,text);return node;}
test('real tutor equation renders as MathML and preserves the currency unit',()=>{
  const node=render('$$\\text{Predicted sales ($)} = b_0 + b_1 \\times 60$$');
  assert.equal(find(node,'math').length,1);assert.equal(find(node,'msub').length,2);assert.ok(node.textContent.includes('Predicted sales ($)'));assert.ok(node.textContent.includes('×60'));assert.ok(!node.textContent.includes('$$'));
});
test('fraction, square root and combined scripts keep mathematical structure',()=>{
  const math=context.renderTutorMath('\\frac{\\beta_1^2}{\\sqrt{x}}');
  assert.equal(find(math,'mfrac').length,1);assert.equal(find(math,'msqrt').length,1);assert.equal(find(math,'msubsup').length,1);assert.ok(math.textContent.includes('β12'));
});
test('currency and bold text are preserved without inventing math delimiters',()=>{
  const node=render('The answer is **$3,123.34**.');assert.equal(find(node,'strong').length,1);assert.equal(find(node,'math').length,0);assert.equal(node.textContent,'The answer is $3,123.34.');
});
test('SQL code is literal and not reformatted as maths or HTML',()=>{
  const node=render('```sql\nSELECT name, energy FROM songs WHERE energy > 0.6;\n```');
  assert.equal(find(node,'pre').length,1);assert.equal(find(node,'math').length,0);assert.ok(node.textContent.includes('WHERE energy > 0.6;'));
});
test('HTML and unsupported TeX cannot create executable elements',()=>{
  const node=render('<img src=x onerror=alert(1)> $$\\href{javascript:alert(1)}{click}$$');
  assert.equal(find(node,'img').length,0);assert.equal(find(node,'script').length,0);assert.ok(node.textContent.includes('<img'));assert.ok(node.textContent.includes('\\href'));
});
test('ordered and unordered lists are readable',()=>{assert.equal(find(render('1. First\n2. Second'),'ol').length,1);assert.equal(find(render('- First\n- Second'),'ul').length,1);});
test('malformed and excessive formulas fall back to visible literal text',()=>{
  const node=render('$$\\frac{1}$$');assert.ok(node.textContent.includes('\\frac{1}'));assert.throws(()=>context.renderTutorMath('{'.repeat(100)+'x'+'}'.repeat(100)));assert.throws(()=>context.renderTutorMath('x'.repeat(2001)));
});
