-- Additive upgrade. Existing documents and chat history remain intact.
CREATE TABLE IF NOT EXISTS public.user_profiles (
 id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
 email text, name text, avatar_url text, last_login timestamptz DEFAULT now(), created_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.conversations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 title text NOT NULL DEFAULT 'New Chat', created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.documents (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 name text NOT NULL, chunks integer DEFAULT 0, summary text, fingerprint text, source_type text DEFAULT 'unknown', added_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.chat_messages (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 conversation_id uuid REFERENCES public.conversations(id) ON DELETE CASCADE,
 role text NOT NULL CHECK(role IN ('user','assistant')), content text NOT NULL,
 sources jsonb DEFAULT '[]', confidence double precision DEFAULT 0, conflicts jsonb DEFAULT '[]', created_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.conflicts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 source_a text, source_b text, topic text, claim_a text, claim_b text, severity text DEFAULT 'medium', detected_at timestamptz DEFAULT now()
);
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS page_count integer;
ALTER TABLE public.chat_messages ADD COLUMN IF NOT EXISTS evidence_report jsonb NOT NULL DEFAULT '{}';
ALTER TABLE public.conflicts ADD COLUMN IF NOT EXISTS finding jsonb NOT NULL DEFAULT '{}';
ALTER TABLE public.conflicts ADD COLUMN IF NOT EXISTS pair_key text;
CREATE UNIQUE INDEX IF NOT EXISTS documents_owner_fingerprint ON public.documents(user_id,fingerprint);
CREATE UNIQUE INDEX IF NOT EXISTS documents_id_owner ON public.documents(id,user_id);
CREATE UNIQUE INDEX IF NOT EXISTS conversations_id_owner ON public.conversations(id,user_id);
CREATE UNIQUE INDEX IF NOT EXISTS conflicts_owner_pair ON public.conflicts(user_id,pair_key);
CREATE TABLE IF NOT EXISTS public.document_chunks (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
 document_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal >= 0),
 page integer CHECK(page IS NULL OR page > 0), content text NOT NULL CHECK(length(content) BETWEEN 30 AND 1200),
 embedding jsonb NOT NULL CHECK(jsonb_typeof(embedding)='array' AND jsonb_array_length(embedding)=384),
 embedding_model text NOT NULL DEFAULT 'all-MiniLM-L6-v2' CHECK(embedding_model='all-MiniLM-L6-v2'),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(document_id,user_id) REFERENCES public.documents(id,user_id) ON DELETE CASCADE,
 UNIQUE(document_id,ordinal)
);
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='messages_conversation_owner') THEN
  ALTER TABLE public.chat_messages ADD CONSTRAINT messages_conversation_owner
   FOREIGN KEY(conversation_id,user_id) REFERENCES public.conversations(id,user_id) ON DELETE CASCADE;
 END IF;
END $$;
CREATE INDEX IF NOT EXISTS chunks_owner ON public.document_chunks(user_id);
CREATE INDEX IF NOT EXISTS messages_owner_conversation ON public.chat_messages(user_id,conversation_id,created_at);
CREATE INDEX IF NOT EXISTS conversations_owner_updated ON public.conversations(user_id,updated_at DESC);

DO $$ DECLARE t text; owner_column text; BEGIN
 FOREACH t IN ARRAY ARRAY['user_profiles','conversations','documents','chat_messages','conflicts','document_chunks'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  owner_column := CASE WHEN t='user_profiles' THEN 'id' ELSE 'user_id' END;
  EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I',
   CASE t WHEN 'user_profiles' THEN 'Users manage own profile'
    WHEN 'conversations' THEN 'Users manage own conversations' WHEN 'documents' THEN 'Users manage own documents'
    WHEN 'chat_messages' THEN 'Users manage own messages' WHEN 'conflicts' THEN 'Users manage own conflicts'
    ELSE 'owner_access' END,t);
  EXECUTE format('DROP POLICY IF EXISTS owner_access ON public.%I',t);
  EXECUTE format('CREATE POLICY owner_access ON public.%I FOR ALL TO authenticated USING ((select auth.uid())=%I) WITH CHECK ((select auth.uid())=%I)', t,owner_column,owner_column);
  EXECUTE format('REVOKE ALL ON public.%I FROM anon',t);
  EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON public.%I TO authenticated',t);
 END LOOP;
END $$;

CREATE OR REPLACE FUNCTION public.ingest_document(p_document jsonb,p_chunks jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
DECLARE uid uuid := auth.uid(); did uuid; existing_id uuid; chunk_count integer;
BEGIN
 IF uid IS NULL THEN RAISE EXCEPTION 'Authentication required'; END IF;
 IF jsonb_typeof(p_chunks) IS DISTINCT FROM 'array' THEN RAISE EXCEPTION 'Invalid passages'; END IF;
 chunk_count := jsonb_array_length(p_chunks);
 IF chunk_count < 1 OR chunk_count > 500 THEN RAISE EXCEPTION 'Passage limit exceeded'; END IF;
 IF coalesce(length(p_document->>'name'),0) NOT BETWEEN 1 AND 500
  OR coalesce(p_document->>'fingerprint','') !~ '^[a-f0-9]{64}$'
  OR coalesce(p_document->>'source_type','') NOT IN ('pdf','url') THEN RAISE EXCEPTION 'Invalid document'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(uid::text,0));
 SELECT id INTO existing_id FROM public.documents WHERE user_id=uid AND fingerprint=p_document->>'fingerprint';
 IF existing_id IS NOT NULL THEN RETURN jsonb_build_object('status','duplicate','id',existing_id); END IF;
 IF (SELECT count(*) FROM public.document_chunks WHERE user_id=uid)+chunk_count > 3000 THEN
  RAISE EXCEPTION 'Knowledge base limit: 3000 passages. Remove a source before adding more.';
 END IF;
 INSERT INTO public.documents(user_id,name,chunks,summary,fingerprint,source_type,page_count)
 VALUES(uid,p_document->>'name',chunk_count,left(p_document->>'summary',1000),p_document->>'fingerprint',p_document->>'source_type',(p_document->>'page_count')::integer)
 RETURNING id INTO did;
 INSERT INTO public.document_chunks(user_id,document_id,ordinal,page,content,embedding,embedding_model)
 SELECT uid,did,(c->>'ordinal')::integer,(c->>'page')::integer,c->>'content',c->'embedding',c->>'embedding_model'
 FROM jsonb_array_elements(p_chunks) c;
 RETURN jsonb_build_object('status','success','id',did,'chunks',chunk_count);
END $$;
REVOKE ALL ON FUNCTION public.ingest_document(jsonb,jsonb) FROM PUBLIC,anon;
GRANT EXECUTE ON FUNCTION public.ingest_document(jsonb,jsonb) TO authenticated;

-- Cover composite ownership references used by cascades and FK validation.
CREATE INDEX IF NOT EXISTS messages_conversation_owner_idx ON public.chat_messages(conversation_id,user_id);
CREATE INDEX IF NOT EXISTS chunks_document_owner_idx ON public.document_chunks(document_id,user_id);

