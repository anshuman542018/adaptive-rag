import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const html = readFileSync('sourcemind/browser_binding/index.html','utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const messages=[];
let listener;
let cookie='unrelated=private';
const parent={postMessage:(message,origin)=>messages.push({message,origin})};
const document={referrer:'https://app.streamlit.app/~/+/'};
Object.defineProperty(document,'cookie',{get:()=>cookie,set:value=>{cookie='unrelated=private; '+value.split(';')[0];}});
vm.runInNewContext(script,{URL,document,location:{href:'https://app.streamlit.app/component/oauth/',protocol:'https:'},parent,
  window:{addEventListener:(_event,fn)=>listener=fn}});
const nonce='a'.repeat(43);
const render=(args,origin='https://app.streamlit.app',source=parent)=>listener({source,origin,data:{type:'streamlit:render',args}});
render({mode:'write',nonce},'https://attacker.example');
assert.equal(cookie,'unrelated=private');
render({mode:'write',nonce});
assert.equal(messages.findLast(x=>x.message.type==='streamlit:setComponentValue').message.value.ready,true);
render({mode:'read'});
assert.deepEqual(JSON.parse(JSON.stringify(messages.findLast(x=>x.message.type==='streamlit:setComponentValue').message.value)),{nonce});
assert(!JSON.stringify(messages).includes('private'));
cookie='unrelated=private';
render({mode:'read'});
assert.equal(messages.findLast(x=>x.message.type==='streamlit:setComponentValue').message.value.nonce,'');
console.log('Browser binding: same-origin messages, write readiness, scoped nonce read, missing cookie passed');
