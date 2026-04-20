# Supabase como substrato de persistencia

Status: aceito
Data: 2026-04
Escopo: persistencia de memoria conversacional, historico de execucoes de
pipelines, referencias de artefatos multimodais (imagens, audio, PDFs) e
qualquer vetorizacao persistente fora do indice em memoria.

## Contexto

O backend hoje mantem todo estado operacional em memoria: `ChatMemoryStore`
default (`InMemoryChatMemoryStore`), `ExecutionStore` default
(`InMemoryExecutionStore`), `TTLCache` nos clientes HTTP externos,
`VectorIndex` default (`InMemoryVectorIndex`) e `CachingTextEmbedder`.
Esse desenho serviu a validacao rapida, mas nao suporta horizontal scale
nem sobrevive a reinicios. Um substrato compartilhado e inevitavel
quando sairmos do setup single-process.

Supabase ja e o fornecedor de Storage para artefatos multimodais (bucket
configurado em `supabase_storage_public_bucket`). Promove-lo para
substrato de dados relacional e vetorial mantem um unico contrato
operacional (chaves, auditoria, RLS) ao inves de introduzir um segundo
provedor para Postgres/pgvector/Redis.

## Decisao

Adotamos Supabase como substrato padrao de persistencia:

- Postgres gerenciado como store relacional para `ChatMemoryStore`
  (tabela `chat_conversation_state`), `ExecutionStore`
  (tabela `pipeline_execution`) e auditoria de roteamento
  (`ai_router_event`).
- `pgvector` como backend para `VectorIndex` quando a base de
  conhecimento crescer alem do limite viavel em memoria. O contrato
  `VectorIndex` ja introduzido em `rag/vector_index.py` cobre o
  acoplamento minimo com a implementacao atual.
- Supabase Storage continua responsavel por payloads multimodais; links
  assinados populam campos dos stores acima.
- Auth integrado via JWT emitido pelo Supabase Auth; middleware HTTP
  (onda 4.1) valida token e propaga `user_id` no request scope.

## Alternativas consideradas

| Opcao                    | Por que nao | 
| ------------------------ | ----------- |
| Postgres bare + Redis    | Adiciona superficie de ops (dois produtos, dois deployments, RLS manual). |
| DynamoDB + OpenSearch    | Custo de aprendizado + data plane distinto do Storage ja em uso. |
| Manter tudo in-memory    | Inviavel em multi-replica; perde memoria em deploys. |
| Somente pgvector externo | Fragmenta auth e billing; nao elimina a necessidade de store relacional. |

## Implicacoes operacionais

- Novos stores precisarao de migrations versionadas (supabase/migrations).
- O default in-memory permanece para testes e ambiente local sem
  credenciais. A selecao do backend real deve seguir
  `get_settings().supabase_*` ja existente mais chaves
  `SUPABASE_DB_URL` / `SUPABASE_SERVICE_ROLE_KEY`.
- Tests de integracao contra Supabase devem ficar atras de um marker
  `integration` e rodar opcional no CI.
- O circuit breaker/retry que envolvem chamadas externas devem ser
  reusados para chamadas Postgres (connection-pool aware).

## Proximos passos

1. Esquema relacional incremental (`supabase/migrations/*.sql`) com
   tabelas acima.
2. Implementar `SupabaseChatMemoryStore` e `SupabaseExecutionStore`
   respeitando os protocolos existentes.
3. Adicionar `PgVectorIndex` cobrindo o contrato `VectorIndex`.
4. Middleware de autenticacao consumindo JWT Supabase.
5. Runbook de migracao/backfill para os stores persistentes.
