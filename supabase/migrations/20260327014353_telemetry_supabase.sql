create extension if not exists pgcrypto;

create table if not exists public.telemetry_agent_runs (
    run_id text primary key,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    request_id text not null,
    trace_id text not null,
    conversation_id text null,
    agent text null,
    entrypoint text null,
    flow text null,
    engine text null,
    contexto text null,
    idioma text null,
    intencao text null,
    pipeline text null,
    handler text null,
    status text null,
    http_method text null,
    http_path text null,
    http_status_code integer null,
    client_ip text null,
    query_json jsonb not null default '{}'::jsonb,
    started_at timestamptz not null default timezone('utc', now()),
    finished_at timestamptz null,
    duration_ms double precision null,
    timeout boolean not null default false,
    warnings_count integer not null default 0,
    precisa_revisao boolean not null default false,
    fallback_count integer not null default 0,
    rag_used boolean not null default false,
    rag_docs_count integer not null default 0,
    llm_calls_count integer not null default 0,
    tool_calls_count integer not null default 0,
    stage_events_count integer not null default 0,
    total_input_tokens integer not null default 0,
    total_output_tokens integer not null default 0,
    total_tokens integer not null default 0,
    total_cost_usd numeric(18,10) null,
    error_type text null,
    error_message text null,
    metadata_json jsonb not null default '{}'::jsonb
);

create index if not exists idx_telemetry_agent_runs_created_at
    on public.telemetry_agent_runs (created_at desc);

create index if not exists idx_telemetry_agent_runs_request_id
    on public.telemetry_agent_runs (request_id);

create index if not exists idx_telemetry_agent_runs_trace_id
    on public.telemetry_agent_runs (trace_id);

create index if not exists idx_telemetry_agent_runs_conversation_id
    on public.telemetry_agent_runs (conversation_id);

create index if not exists idx_telemetry_agent_runs_agent_created_at
    on public.telemetry_agent_runs (agent, created_at desc);

create index if not exists idx_telemetry_agent_runs_status_created_at
    on public.telemetry_agent_runs (status, created_at desc);

create table if not exists public.telemetry_llm_calls (
    call_id text primary key,
    run_id text not null references public.telemetry_agent_runs(run_id) on delete cascade,
    request_id text not null,
    trace_id text not null,
    created_at timestamptz not null default timezone('utc', now()),
    provider text not null,
    operation text not null,
    model text not null,
    provider_response_id text null,
    status text not null,
    timeout boolean not null default false,
    duration_ms double precision null,
    input_tokens integer null,
    output_tokens integer null,
    total_tokens integer null,
    cost_usd numeric(18,10) null,
    prompt_chars integer null,
    output_chars integer null,
    error_type text null,
    error_message text null,
    prompt_preview_masked text null,
    response_preview_masked text null,
    metadata_json jsonb not null default '{}'::jsonb
);

create index if not exists idx_telemetry_llm_calls_run_id
    on public.telemetry_llm_calls (run_id);

create index if not exists idx_telemetry_llm_calls_created_at
    on public.telemetry_llm_calls (created_at desc);

create index if not exists idx_telemetry_llm_calls_provider_model
    on public.telemetry_llm_calls (provider, model, created_at desc);

create index if not exists idx_telemetry_llm_calls_status
    on public.telemetry_llm_calls (status, created_at desc);

create table if not exists public.telemetry_tool_calls (
    tool_call_id text primary key,
    run_id text not null references public.telemetry_agent_runs(run_id) on delete cascade,
    request_id text not null,
    trace_id text not null,
    created_at timestamptz not null default timezone('utc', now()),
    tool_name text not null,
    status text not null,
    duration_ms double precision null,
    timeout boolean not null default false,
    error_type text null,
    warnings_count integer null,
    precisa_revisao boolean not null default false,
    metadata_json jsonb not null default '{}'::jsonb
);

create index if not exists idx_telemetry_tool_calls_run_id
    on public.telemetry_tool_calls (run_id);

create index if not exists idx_telemetry_tool_calls_tool_name
    on public.telemetry_tool_calls (tool_name, created_at desc);

create index if not exists idx_telemetry_tool_calls_status
    on public.telemetry_tool_calls (status, created_at desc);

create table if not exists public.telemetry_stage_events (
    event_id text primary key,
    run_id text not null references public.telemetry_agent_runs(run_id) on delete cascade,
    request_id text not null,
    trace_id text not null,
    created_at timestamptz not null default timezone('utc', now()),
    event_type text not null,
    name text not null,
    status text null,
    duration_ms double precision null,
    timeout boolean not null default false,
    flow text null,
    engine text null,
    reason text null,
    used boolean null,
    documents_count integer null,
    metadata_json jsonb not null default '{}'::jsonb
);

create index if not exists idx_telemetry_stage_events_run_id
    on public.telemetry_stage_events (run_id);

create index if not exists idx_telemetry_stage_events_created_at
    on public.telemetry_stage_events (created_at desc);

create index if not exists idx_telemetry_stage_events_type
    on public.telemetry_stage_events (event_type, created_at desc);

create index if not exists idx_telemetry_stage_events_flow
    on public.telemetry_stage_events (flow, created_at desc);

create or replace view public.telemetry_agent_runs_daily as
select
    date_trunc('day', started_at) as day_utc,
    coalesce(agent, entrypoint, 'desconhecido') as agent,
    coalesce(status, 'desconhecido') as status,
    count(*) as runs_count,
    sum(llm_calls_count) as llm_calls_count,
    sum(tool_calls_count) as tool_calls_count,
    sum(stage_events_count) as stage_events_count,
    sum(total_input_tokens) as total_input_tokens,
    sum(total_output_tokens) as total_output_tokens,
    sum(total_tokens) as total_tokens,
    sum(coalesce(total_cost_usd, 0)) as total_cost_usd,
    avg(duration_ms) as avg_duration_ms,
    avg(case when precisa_revisao then 1 else 0 end) as review_rate
from public.telemetry_agent_runs
group by 1, 2, 3;

create or replace view public.telemetry_llm_models_daily as
select
    date_trunc('day', created_at) as day_utc,
    provider,
    model,
    operation,
    status,
    count(*) as calls_count,
    sum(coalesce(input_tokens, 0)) as input_tokens,
    sum(coalesce(output_tokens, 0)) as output_tokens,
    sum(coalesce(total_tokens, 0)) as total_tokens,
    sum(coalesce(cost_usd, 0)) as total_cost_usd,
    avg(duration_ms) as avg_duration_ms
from public.telemetry_llm_calls
group by 1, 2, 3, 4, 5;

create or replace function public.telemetry_cleanup(retention_days integer default 30)
returns void
language plpgsql
as $$
declare
    cutoff timestamptz := timezone('utc', now()) - make_interval(days => retention_days);
begin
    delete from public.telemetry_stage_events where created_at < cutoff;
    delete from public.telemetry_tool_calls where created_at < cutoff;
    delete from public.telemetry_llm_calls where created_at < cutoff;
    delete from public.telemetry_agent_runs where created_at < cutoff;
end;
$$;
