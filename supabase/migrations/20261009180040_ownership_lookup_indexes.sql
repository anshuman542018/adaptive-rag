-- Cover composite ownership references used by cascades and FK validation.
CREATE INDEX IF NOT EXISTS messages_conversation_owner_idx ON public.chat_messages(conversation_id,user_id);
CREATE INDEX IF NOT EXISTS chunks_document_owner_idx ON public.document_chunks(document_id,user_id);
