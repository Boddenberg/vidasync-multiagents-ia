create extension if not exists pgcrypto;

create table if not exists public.llm_judge_evaluations (
    evaluation_id text primary key,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    feature text not null,
    judge_status text not null check (judge_status in ('pending', 'completed', 'failed')),
    request_id text null,
    conversation_id text null,
    message_id text null,
    user_id text null,
    idioma text not null default 'pt-BR',
    intencao text null,
    pipeline text null,
    handler text null,
    source_model text not null,
    source_prompt text not null,
    source_response text not null,
    source_duration_ms double precision null,
    source_prompt_chars integer not null default 0,
    source_response_chars integer not null default 0,
    source_prompt_tokens integer null,
    source_completion_tokens integer null,
    source_total_tokens integer null,
    source_metadata jsonb not null default '{}'::jsonb,
    judge_model text null,
    judge_duration_ms double precision null,
    judge_prompt_tokens integer null,
    judge_completion_tokens integer null,
    judge_total_tokens integer null,
    judge_overall_score double precision null,
    judge_decision text null check (judge_decision in ('approved', 'rejected')),
    judge_summary text null,
    judge_scores jsonb not null default '{}'::jsonb,
    judge_improvements jsonb not null default '[]'::jsonb,
    judge_rejection_reasons jsonb not null default '[]'::jsonb,
    judge_result jsonb null,
    judge_error text null
);

create index if not exists idx_llm_judge_evaluations_created_at
    on public.llm_judge_evaluations (created_at desc);

create index if not exists idx_llm_judge_evaluations_feature_created_at
    on public.llm_judge_evaluations (feature, created_at desc);

create index if not exists idx_llm_judge_evaluations_judge_status
    on public.llm_judge_evaluations (judge_status);

create index if not exists idx_llm_judge_evaluations_request_id
    on public.llm_judge_evaluations (request_id);

create index if not exists idx_llm_judge_evaluations_conversation_id
    on public.llm_judge_evaluations (conversation_id);

create index if not exists idx_llm_judge_evaluations_message_id
    on public.llm_judge_evaluations (message_id);

create index if not exists idx_llm_judge_evaluations_pipeline_decision
    on public.llm_judge_evaluations (pipeline, judge_decision);
