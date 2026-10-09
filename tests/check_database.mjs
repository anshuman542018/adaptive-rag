// Actual PostgreSQL semantics via PGlite; isolated disposable database only.
// npm install --prefix .test-tools @electric-sql/pglite
import { PGlite } from '../.test-tools/node_modules/@electric-sql/pglite/dist/index.js';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
const db = new PGlite();
await db.exec(`
CREATE ROLE anon; CREATE ROLE authenticated;
CREATE SCHEMA auth;
CREATE TABLE auth.users(id uuid PRIMARY KEY);
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
 $$ SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
GRANT USAGE ON SCHEMA auth,public TO authenticated,anon;
GRANT EXECUTE ON FUNCTION auth.uid() TO authenticated,anon;
INSERT INTO auth.users VALUES ('11111111-1111-1111-1111-111111111111'),('22222222-2222-2222-2222-222222222222');
`);
const migrations=await fs.readdir(new URL('../supabase/migrations/',import.meta.url));
const sql=(await Promise.all(migrations.filter(f=>f.endsWith('.sql')).sort().map(f=>fs.readFile(new URL(`../supabase/migrations/${f}`,import.meta.url),'utf8')))).join('\n');
await db.exec(sql);
await db.exec(sql); // idempotence
async function identity(id){
 await db.exec(`RESET ROLE; SET ROLE authenticated; SELECT set_config('request.jwt.claim.sub','${id}',false);`);
}
const alice='11111111-1111-1111-1111-111111111111',bob='22222222-2222-2222-2222-222222222222';
const doc={name:'private.pdf',source_type:'pdf',fingerprint:'a'.repeat(64),page_count:1};
const chunks=[{ordinal:0,page:1,content:'The confidential engineering baseline value is 12 volts.',embedding:Array(384).fill(0.1),embedding_model:'all-MiniLM-L6-v2'}];
await identity(alice);
const insert=await db.query('select public.ingest_document($1,$2) as result',[doc,chunks]);
assert.equal(insert.rows[0].result.status,'success');
assert.equal((await db.query('select public.ingest_document($1,$2) as result',[doc,chunks])).rows[0].result.status,'duplicate');
assert.equal((await db.query('select * from public.document_chunks')).rows.length,1);
const conversation=(await db.query('insert into public.conversations(user_id,title) values ($1,$2) returning id',[alice,'Private'])).rows[0].id;
await assert.rejects(db.query('update public.documents set user_id=$1',[bob]),/row-level security/);
await identity(bob);
assert.equal((await db.query('select * from public.documents')).rows.length,0);
assert.equal((await db.query('select * from public.document_chunks')).rows.length,0);
assert.equal((await db.query('select * from public.conversations')).rows.length,0);
await assert.rejects(db.query('insert into public.chat_messages(user_id,conversation_id,role,content) values ($1,$2,$3,$4)',[bob,conversation,'user','intrusion']),/foreign key/);
await assert.rejects(db.query('insert into public.document_chunks(user_id,document_id,ordinal,page,content,embedding) values ($1,$2,2,1,$3,$4)',[bob,insert.rows[0].result.id,chunks[0].content,chunks[0].embedding]),/foreign key/);
const invalid={...doc,fingerprint:'b'.repeat(64)};
await assert.rejects(db.query('select public.ingest_document($1,$2)',[invalid,[{...chunks[0],embedding:[1]}]]),/check constraint/);
assert.equal((await db.query('select * from public.documents')).rows.length,0); // atomic rollback
await db.exec('RESET ROLE; SET ROLE anon;');
await assert.rejects(db.query('select * from public.documents'),/permission denied/);
await assert.rejects(db.query('select public.ingest_document($1,$2)',[doc,chunks]),/permission denied/);
await identity(alice);
await db.query('delete from public.documents where id=$1',[insert.rows[0].result.id]);
assert.equal((await db.query('select * from public.document_chunks')).rows.length,0);
await db.close();
console.log('Database checks passed: repeatable migration, authenticated isolation, ownership FKs, atomic ingestion, deduplication, anon denial and delete cascade.');
