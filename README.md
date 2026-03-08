# VidaSync Multiagents IA

Backend FastAPI para orquestracao de agentes de IA focados em:
- alimentos e macros (TBCA / TACO Online)
- transcricao (audio, imagem, PDF)
- normalizacao semantica de documentos
- estruturacao de plano alimentar

## Status Atual
- API funcional com rotas por dominio (`agentes`, `tbca`, `taco-online`, `system`).
- Observabilidade completa: logs estruturados JSON/texto, request/response middleware, metricas.
- Suite de testes automatizados cobrindo rotas, servicos e parsers.

## Contrato Alvo App-BFF-Agentes
- Documento oficial de contrato e arquitetura alvo: `docs/CONTRATOS_ARQUITETURA_ALVO.md`.

## Stack
- Python 3.11+
- FastAPI + Uvicorn
- OpenAI SDK
- LangGraph / LangChain (base para orquestracao e evolucoes de pipeline)
- RAG base in-memory (loader/chunker/indexacao vetorial) com embeddings hash/OpenAI
- Pytest + Ruff

## Como Rodar
1. Criar ambiente virtual:
```bash
python -m venv .venv
.venv\Scripts\activate
```

2. Instalar dependencias:
```bash
pip install -e .[dev]
```

3. Configurar ambiente:
```bash
copy .env.example .env
```

4. Subir API:
```bash
uvicorn vidasync_multiagents_ia.main:app --reload
```

## Variaveis De Ambiente
| Variavel | Default | Descricao |
|---|---|---|
| `OPENAI_API_KEY` | `""` | Chave da OpenAI |
| `OPENAI_MODEL` | `gpt-4o-mini` | Modelo base de texto/imagem |
| `OPENAI_AUDIO_MODEL` | `gpt-4o-mini-transcribe` | Modelo de transcricao de audio |
| `OPENAI_TIMEOUT_SECONDS` | `60` | Timeout de chamadas OpenAI |
| `AUDIO_MAX_UPLOAD_BYTES` | `8388608` | Limite upload audio (8MB) |
| `AUDIO_RECOMMENDED_MAX_SECONDS` | `45` | Referencia para front |
| `PDF_MAX_UPLOAD_BYTES` | `20971520` | Limite upload PDF (20MB) |
| `VIDASYNC_DOCS_DIR` | `knowledge` | Diretorio base dos documentos da base nutricional |
| `RAG_CHUNK_SIZE` | `800` | Tamanho maximo de chunk textual |
| `RAG_CHUNK_OVERLAP` | `120` | Sobreposicao entre chunks consecutivos |
| `RAG_TOP_K` | `4` | Quantidade padrao de documentos retornados |
| `RAG_MIN_SCORE` | `0.12` | Score minimo de similaridade para considerar um hit |
| `RAG_CONTEXT_MAX_CHARS` | `4000` | Limite de caracteres do contexto enviado ao LLM |
| `RAG_EMBEDDING_PROVIDER` | `auto` | `auto`, `openai` ou `hash` |
| `RAG_EMBEDDING_MODEL` | `text-embedding-3-small` | Modelo de embedding quando provider = `openai` |
| `LOG_LEVEL` | `INFO` | Nivel de log |
| `LOG_FORMAT` | `json` | `json` ou `text` |
| `LOG_JSON_PRETTY` | `false` | JSON identado no console |
| `LOG_HTTP_HEADERS` | `false` | Logar headers de request/response |
| `LOG_HTTP_MAX_BODY_BYTES` | `32768` | Limite de captura de body |
| `LOG_HTTP_MAX_BODY_CHARS` | `4000` | Limite de preview textual |
| `METRICS_ENABLED` | `true` | Liga metricas em memoria |
| `RESPONSE_EXCLUDE_NONE` | `false` | Remove campos `null` globalmente |
| `PLANO_ALIMENTAR_REFEICOES_SECOND_PASS_ENABLED` | `false` | Segundo passe LLM para refeicoes |
| `PLANO_PIPELINE_ORCHESTRATOR_ENGINE` | `langgraph` | Engine do pipeline de plano: `langgraph` ou `legacy` |
| `CHAT_ORCHESTRATOR_ENGINE` | `langgraph` | Engine do chat conversacional: `langgraph` ou `legacy` |
| `CHAT_MEMORY_ENABLED` | `true` | Liga memoria conversacional controlada |
| `CHAT_MEMORY_MAX_TURNS_SHORT_TERM` | `8` | Janela de turnos recentes mantida sem resumo |
| `CHAT_MEMORY_SUMMARY_MAX_CHARS` | `1800` | Limite do resumo acumulado da conversa |
| `CHAT_MEMORY_CONTEXT_MAX_CHARS` | `2200` | Limite do contexto de memoria injetado no prompt |
| `CHAT_MEMORY_MAX_TURN_CHARS` | `320` | Limite de caracteres por turno no contexto |
| `DEBUG_LOCAL_ROUTES_ENABLED` | `true` | Liga rotas temporarias de debug |

## Catalogo De Endpoints
### System
- `GET /health`
- `GET /metrics`

### Orquestracao/Base
- `POST /orchestrate`
- `POST /v1/openai/chat` (inclui `intencao_detectada` + `roteamento` por pipeline)
- `POST /ai/router` (interno, roteamento por `contexto`)

### Agentes De Texto/Plano
- `POST /agentes/texto/extrair-porcoes`
- `POST /agentes/texto/estruturar-plano-alimentar`

### Agentes De Imagem/Foto
- `POST /agentes/imagens/transcrever-texto`
- `POST /agentes/fotos/identificar-comida`
- `POST /agentes/fotos/estimar-porcoes`

### Agentes De Documento
- `POST /agentes/documentos/transcrever-pdf` (multipart/form-data)
- `POST /agentes/documentos/normalizar-texto-imagens`
- `POST /agentes/documentos/normalizar-texto-pdf` (multipart/form-data)

### Integracoes Nutricionais
- `POST /tbca/search`
- `POST /taco-online/food`

### Rota Temporaria De Debug Local
- `POST /agentes/debug-local/pipeline-plano-imagem`
- `POST /agentes/debug-local/pipeline-plano-e2e-temporario`
- Habilitada apenas quando `DEBUG_LOCAL_ROUTES_ENABLED=true`.

## Exemplos Rapidos (curl)
### Health
```bash
curl --request GET "http://127.0.0.1:8000/health"
```

### TBCA (body)
```bash
curl --request POST "http://127.0.0.1:8000/tbca/search" \
  --header "Content-Type: application/json" \
  --data "{\"consulta\":\"arroz\",\"gramas\":150}"
```

### TACO Online (body)
```bash
curl --request POST "http://127.0.0.1:8000/taco-online/food" \
  --header "Content-Type: application/json" \
  --data "{\"consulta\":\"feijao carioca cru\",\"gramas\":100}"
```

### OCR De Imagens
```bash
curl --request POST "http://127.0.0.1:8000/agentes/imagens/transcrever-texto" \
  --header "Content-Type: application/json" \
  --data "{\"contexto\":\"transcrever_texto_imagem\",\"imagem_urls\":[\"https://i.imgur.com/39gMaUj.png\"],\"idioma\":\"pt-BR\"}"
```

### AI Router Interno (chat)
```bash
curl --request POST "http://127.0.0.1:8000/ai/router" \
  --header "Content-Type: application/json" \
  --data "{\"trace_id\":\"trace-local-001\",\"contexto\":\"chat\",\"idioma\":\"pt-BR\",\"payload\":{\"prompt\":\"Oi, tudo bem?\"}}"
```

### Chat Com Refeicao Por Foto (via BFF/AI Router)
```bash
curl --request POST "http://127.0.0.1:8000/v1/openai/chat" \
  --header "Content-Type: application/json" \
  --data "{\"prompt\":\"Registrar refeicao por foto\",\"refeicao_anexo\":{\"tipo_fonte\":\"imagem\",\"imagem_url\":\"https://example.com/prato.jpg\"}}"
```

## Deteccao e roteamento de intencao no chat (novo)
- Toda chamada em `POST /v1/openai/chat` executa deteccao de intencao antes da resposta de texto.
- A resposta inclui:
  - `intencao_detectada.intencao`
  - `intencao_detectada.confianca`
  - `intencao_detectada.contexto_roteamento`
  - `intencao_detectada.requer_fluxo_estruturado`
  - `intencao_detectada.candidatos` (top candidatos para auditoria/roteamento)
  - `roteamento.pipeline` (ex.: `tool_calculo`, `rag_conhecimento_nutricional`)
  - `roteamento.handler` (handler interno usado)
  - `roteamento.status`, `roteamento.warnings`, `roteamento.precisa_revisao`
  - `roteamento.metadados` (payload tecnico do pipeline acionado)
- Intencoes iniciais suportadas:
  - `enviar_plano_nutri`
  - `pedir_receitas`
  - `pedir_substituicoes`
  - `pedir_dicas`
  - `perguntar_calorias`
  - `cadastrar_pratos`
  - `calcular_imc`
  - `registrar_refeicao_foto`
  - `registrar_refeicao_audio`
  - `conversa_geral`
- Grafo base do chat (LangGraph): `entrada -> detectar_intencao -> rotear_intencao -> executar_pipeline -> compor_resposta -> saida_final`
- Suporte multimodal no proprio chat:
  - `plano_anexo`: pipeline de plano alimentar por imagem/PDF.
  - `refeicao_anexo`:
    - `tipo_fonte=imagem` -> fluxo de registro por foto (identificacao + estimativa de porcoes).
    - `tipo_fonte=audio` -> fluxo de registro por audio (transcricao + interpretacao de porcoes).
  - Regras de prioridade de anexo no roteador:
    - `plano_anexo` tem prioridade maxima.
    - depois `refeicao_anexo`.
- Fluxo dedicado de receitas:
  - `pedir_receitas` usa `handler_fluxo_receitas_personalizadas`.
  - O fluxo combina entendimento de perfil do pedido + contexto da conversa + suporte RAG.
  - Saida inclui sugestoes praticas e organizadas em `roteamento.metadados`.
- Fluxo dedicado de substituicoes:
  - `pedir_substituicoes` usa `handler_fluxo_substituicoes_personalizadas`.
  - O fluxo combina regra deterministica de equivalencia + tool de apoio + contexto conversacional.
  - Saida inclui alimento original, objetivo da troca e opcoes coerentes em `roteamento.metadados`.
- Fluxo dedicado de cadastro de pratos/refeicoes:
  - `cadastrar_pratos` usa `handler_fluxo_cadastro_refeicoes`.
  - O fluxo interpreta mensagem livre, extrai itens e quantidades quando disponiveis e gera perguntas de confirmacao em casos ambiguos.
  - Quando houver baixa confianca, retorna `precisa_revisao=true`.
  - O contrato de saida ja fica preparado para reuso futuro com `audio_transcrito` e `foto_ocr`.
- Fluxo dedicado de calorias/macros:
  - `perguntar_calorias` usa `handler_fluxo_calorias_macros`.
  - O fluxo decide entre:
    - `apoio_contextual` (tool de conhecimento nutricional) para perguntas conceituais.
    - `base_estruturada_tbca` ou `base_estruturada_taco` para alimento unico.
    - `tool_calcular_calorias` ou `tool_calcular_macros` para refeicoes/combinacoes ou fallback.
  - Nao duplica regra de negocio: reaproveita services de TBCA/TACO e tools existentes do chat.

### Memoria conversacional controlada (novo)
- Entrada em `POST /v1/openai/chat`:
  - `conversation_id` (opcional): identifica a conversa.
  - `usar_memoria` (default `true`): habilita/desabilita memoria por chamada.
  - `metadados_conversa` (opcional): metadados de rastreio.
- Estrategia:
  - curto prazo: mantem os ultimos turnos.
  - resumo acumulado: compacta turnos antigos para evitar historico baguncado.
  - limite de contexto: controla o tamanho maximo injetado no prompt.
- Saida:
  - `conversation_id`
  - `memoria.total_turnos`, `turnos_curto_prazo`, `turnos_resumidos`, `limite_aplicado`, `metadados`.

## Tools iniciais do chat (dominio nutricao)
- As tools ficam em `src/vidasync_multiagents_ia/services/chat_tools/`.
- Contrato interno padrao:
  - entrada: `ChatToolExecutionInput` (`tool_name`, `prompt`, `idioma`, `intencao`, `metadados`)
  - saida: `ChatToolExecutionOutput` (`tool_name`, `status`, `resposta`, `warnings`, `precisa_revisao`, `metadados`)
- Executor unico: `ChatToolExecutor` (registry + logs + tratamento de erro).
- Tools implementadas:
  - `calcular_calorias`
  - `calcular_macros`
  - `calcular_imc`
  - `buscar_receitas`
  - `sugerir_substituicoes`
  - `cadastrar_prato`
  - `consultar_conhecimento_nutricional`
- Observacao:
  - `pedir_receitas` no roteador do chat usa fluxo dedicado (`ChatReceitasFlowService`) para personalizacao.
  - `pedir_substituicoes` no roteador do chat usa fluxo dedicado (`ChatSubstituicoesFlowService`) para coerencia da troca.
  - A tool `buscar_receitas` permanece disponivel para reutilizacao/fallback.
- Integracao com o LangGraph:
  - o no `rotear_intencao` decide pipeline/handler
  - o no `executar_pipeline` delega ao `ChatConversacionalRouterService`
  - o router chama o `ChatToolExecutor` quando a intencao pertence a tools

## Base RAG Do Chat Nutricional (novo)
### Objetivo
- Fornecer contexto para intencoes conversacionais de conhecimento, dicas e explicacoes.
- Reforcar respostas de receitas/substituicoes com base textual rastreavel.

### Pipeline Base
1. `NutritionKnowledgeLoader`: carrega fontes em `knowledge/` (`.md`, `.txt`, `.json`).
2. `SlidingWindowChunker`: quebra em chunks com overlap configuravel.
3. `TextEmbedder`: gera embeddings (`hash` local ou OpenAI).
4. `InMemoryVectorIndex`: indexa vetores e recupera por similaridade cosseno.
5. `RagContextBuilder`: monta contexto final + lista de documentos para auditoria.
6. `NutritionRagService`: orquestra ingestao, retrieval e montagem de contexto.
7. `rag.vector_store`: fachada estavel para consumo das tools e do roteador.

### Regra De Uso (RAG vs Tool)
- RAG:
  - duvidas de conhecimento nutricional
  - dicas gerais e explicacoes textuais
  - apoio contextual para respostas generativas
- Tools deterministicas:
  - calculos reproduziveis e regras fechadas (IMC, calorias/macros, validacoes)
- Decisao:
  - se precisa de formula/regra fixa, fica em tool
  - se precisa de base textual contextual, usa RAG

### AI Router Interno (audio em base64)
```bash
curl --request POST "http://127.0.0.1:8000/ai/router" \
  --header "Content-Type: application/json" \
  --data "{\"contexto\":\"transcrever_audio_usuario\",\"idioma\":\"pt-BR\",\"payload\":{\"nome_arquivo\":\"audio.webm\",\"audio_base64\":\"<BASE64_AQUI>\"}}"
```

### Transcrever PDF
```bash
curl --request POST "http://127.0.0.1:8000/agentes/documentos/transcrever-pdf" \
  --form "pdf_file=@C:/caminho/arquivo.pdf;type=application/pdf" \
  --form "contexto=transcrever_texto_pdf" \
  --form "idioma=pt-BR"
```

### Normalizar Plano A Partir De Imagem
```bash
curl --request POST "http://127.0.0.1:8000/agentes/documentos/normalizar-texto-imagens" \
  --header "Content-Type: application/json" \
  --data "{\"contexto\":\"normalizar_texto_plano_alimentar\",\"idioma\":\"pt-BR\",\"imagem_url\":\"https://i.imgur.com/39gMaUj.png\"}"
```

### Estruturar Plano Alimentar
```bash
curl --request POST "http://127.0.0.1:8000/agentes/texto/estruturar-plano-alimentar" \
  --header "Content-Type: application/json" \
  --data "{\"contexto\":\"estruturar_plano_alimentar\",\"idioma\":\"pt-BR\",\"textos_fonte\":[\"[Desjejum]\\nQTD: 1 unidade | ALIMENTO: Ovo\"]}"
```

### Pipeline Temporario (3 Etapas)
```bash
curl --request POST "http://127.0.0.1:8000/agentes/debug-local/pipeline-plano-imagem" \
  --header "Content-Type: application/json" \
  --data "{\"contexto\":\"pipeline_teste_plano_imagem\",\"idioma\":\"pt-BR\",\"imagem_url\":\"https://i.imgur.com/39gMaUj.png\",\"executar_ocr_literal\":true}"
```

### Pipeline E2E Temporario (imagem ou PDF)
```bash
curl --request POST "http://127.0.0.1:8000/agentes/debug-local/pipeline-plano-e2e-temporario" \
  --header "Content-Type: application/json" \
  --data "{\"contexto\":\"pipeline_teste_plano_e2e\",\"idioma\":\"pt-BR\",\"imagem_url\":\"https://i.imgur.com/39gMaUj.png\",\"executar_ocr_literal\":true}"
```

## Observabilidade
### Logging
- Middleware global registra:
  - `http.request.received`
  - `http.response.sent`
  - `http.request.failed`
- Todos os responses carregam `X-Request-ID`.
- Logs de integracao externa:
  - `openai.request` / `openai.response` / `openai.error`
  - `tbca.http.*`
  - `taco_online.http.*`
- Dados sensiveis sao mascarados no preview.

### Metricas
- Endpoint `GET /metrics`.
- Contadores e latencias de HTTP e chamadas externas.
- Coleta pode ser desligada com `METRICS_ENABLED=false`.

## Arquitetura
### Camadas
1. `api/routes`:
   - entrada HTTP, validacao de payload, injeção de dependencia
2. `services`:
   - regra de negocio/orquestracao de cada agente
3. `clients`:
   - adaptadores de integracao externa (OpenAI, TBCA, TACO)
4. `schemas`:
   - contratos de request/response e DTOs internos
5. `observability`:
   - middleware HTTP, logging setup, metricas, contexto de request id
6. `core`:
   - erros e contratos base da aplicacao

### Fluxo Geral
```mermaid
flowchart LR
    A["Cliente (Front/BFF)"] --> B["FastAPI Routes"]
    B --> C["Service Layer"]
    C --> D["External Clients"]
    D --> E["OpenAI / TBCA / TACO"]
    C --> F["Schemas (normalizacao e resposta)"]
    B --> G["HTTP Logging Middleware"]
    G --> H["Logs estruturados + Metrics"]
```

### Pipeline De Plano Alimentar (imagem -> plano)
```mermaid
flowchart TD
    I["Imagem/PDF"] --> O["OCR (agente transcrever_texto_imagem ou PDF)"]
    O --> N["Normalizacao semantica (normalizar_texto_plano_alimentar)"]
    N --> P["Estruturacao (estruturar_plano_alimentar)"]
    P --> Q["Resposta JSON estruturada + diagnostico"]
```

### Orquestracao Do Pipeline De Plano (piloto)
- Interface estavel: `AiOrchestrator`
- Engines disponiveis:
  - `langgraph` (piloto atual)
  - `legacy` (fallback sem grafo)
- Troca de engine sem quebrar API via `PLANO_PIPELINE_ORCHESTRATOR_ENGINE`.

### Estrutura De Pastas
```text
src/vidasync_multiagents_ia/
  api/
    routes/
    dependencies.py
    router.py
  clients/
  core/
  observability/
  schemas/
  services/
    plano_alimentar_pipeline/
  agents/
  rag/
  main.py
  config.py
```

## Qualidade E Testes
### Executar testes
```bash
pytest -q
```

### Lint
```bash
ruff check src tests
```

### Cobertura atual
- testes de rotas (HTTP)
- testes de servicos (regras de negocio)
- testes de parsers/preprocessamento (plano alimentar)
- teste de seguranca de logging (`extra` sem campos reservados)

## Auditoria Tecnica (resultado)
### Pontos aprovados
- Estrutura em camadas esta coerente e escalavel.
- Logs HTTP e de integracao estao estruturados e rastreaveis por `request_id`.
- Erros de servico seguem padrao unificado (`ServiceError`).
- Contratos de schema padronizados com Pydantic.
- Suites de teste e lint passando.

### Ajustes aplicados na auditoria
- Refino do merge de refeicoes para evitar ruido heuristico duplicado quando ja existe secao valida.
- Sanitizacao extra para remover labels invalidos em itens de refeicao.
- Melhor robustez de normalizacao de heading com tratamento de mojibake.
- Padronizacao de logs estruturados em TBCA/TACO service.
- Flag de rota temporaria (`DEBUG_LOCAL_ROUTES_ENABLED`) documentada e aplicada.
- Teste automatizado para impedir regressao de chaves reservadas em `logging extra`.

## Proximos Passos Recomendados
1. Introduzir persistencia de execucoes (request_id, payload resumido, status) para auditoria historica.
2. Adicionar testes de regressao com corpus real de planos alimentares variados.
3. Evoluir pipeline de plano para grafo dedicado (LangGraph) com judges/guardrails.
4. Consolidar base de conversao de medidas caseiras para gramas (RAG/tool) para reduzir revisao manual.
