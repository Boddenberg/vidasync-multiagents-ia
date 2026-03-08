# Contratos E Arquitetura Alvo (App -> BFF -> Camada De Agentes)

## Objetivo
Congelar o contrato de integracao entre BFF e camada de agentes, mantendo o app desacoplado da complexidade de IA.

## Arquitetura Alvo
1. App chama apenas endpoints de dominio no BFF (`/nutrition/calories`, `/analysis/photo`, `/analysis/audio`, `/chat`).
2. BFF valida auth, limites e payload, gera `trace_id`, e encaminha para a camada de agentes.
3. Camada de agentes roteia por `contexto` e executa pipeline simples ou multi-etapas.
4. BFF adapta resposta tecnica para DTO estavel do app.

## Contrato Canonico (BFF -> Agentes)
Implementado no endpoint interno `POST /ai/router`.

### Request
```json
{
  "trace_id": "2f89d8ab5ab94f7c8d29b8f7f970cf16",
  "contexto": "estruturar_plano_alimentar",
  "idioma": "pt-BR",
  "payload": {},
  "metadados": {
    "origem": "vidasync-bff",
    "versao_contrato": "v1",
    "usuario_id": "opcional",
    "request_at": "2026-03-07T10:00:00Z"
  }
}
```

### Response
```json
{
  "trace_id": "2f89d8ab5ab94f7c8d29b8f7f970cf16",
  "contexto": "estruturar_plano_alimentar",
  "status": "sucesso",
  "warnings": [],
  "precisa_revisao": false,
  "resultado": {},
  "erro": null,
  "extraido_em": "2026-03-07T10:00:05Z"
}
```

## Semantica Dos Campos
1. `trace_id`: obrigatorio, propagado ponta a ponta (log/metricas/troubleshooting).
2. `warnings`: avisos nao bloqueantes (ex.: cobertura parcial, campo ambiguo).
3. `precisa_revisao`: `true` quando resultado deve passar por confirmacao humana.
4. `status`:
   - `sucesso`: pipeline concluido.
   - `parcial`: concluiu com degradacao/ausencias.
   - `erro`: falhou.
5. `erro`: objeto ou string com causa principal quando `status=erro`.

## Contexts Suportados (V1)

| Contexto | Payload minimo | Resultado esperado |
|---|---|---|
| `calcular_calorias_texto` | `{"texto":"1 banana e 1 iogurte"}` | calorias/macros totais e itens interpretados |
| `consultar_tbca` | `{"consulta":"arroz","gramas":150}` | alimento selecionado + macros `por_100g` e `ajustado` |
| `consultar_taco_online` | `{"consulta":"feijao carioca cru","gramas":100}` | nutrientes publicos `por_100g` e `ajustado` |
| `transcrever_audio_usuario` | multipart audio ou `audio_url` | `texto_transcrito` |
| `transcrever_texto_imagem` | `{"imagem_urls":[...],"idioma":"pt-BR"}` | OCR por imagem |
| `transcrever_texto_pdf` | multipart pdf | texto transcrito do documento |
| `normalizar_texto_plano_alimentar` | texto OCR bruto (imagem/pdf) | secoes textuais consistentes para parser |
| `estruturar_plano_alimentar` | `{"textos_fonte":[...]}` | plano alimentar estruturado em JSON |
| `interpretar_porcoes_texto` | `{"texto_transcrito":"..."}` | itens alimentares + porcoes em gramas/faixa |
| `identificar_fotos` | `{"imagem_url":"..."}` | classificacao `eh_comida` + qualidade |
| `estimar_porcoes_do_prato` | `{"imagem_url":"..."}` | lista de alimentos e gramas estimados |

## Intencao No Chat Conversacional (V1)
Antes da resposta principal do chat, a camada detecta intencao e retorna bloco padronizado com confianca.

### Campos adicionados em `/v1/openai/chat`
```json
{
  "model": "gpt-4o-mini",
  "response": "texto da resposta",
  "conversation_id": "conv_abc123",
  "memoria": {
    "conversation_id": "conv_abc123",
    "total_turnos": 12,
    "turnos_curto_prazo": 8,
    "turnos_resumidos": 4,
    "resumo_presente": true,
    "contexto_chars": 1370,
    "limite_aplicado": true,
    "ultima_intencao": "pedir_dicas",
    "ultimo_pipeline": "rag_conhecimento_nutricional",
    "metadados": {"canal": "mobile"},
    "atualizada_em": "2026-03-07T10:00:08Z"
  },
  "intencao_detectada": {
    "intencao": "perguntar_calorias",
    "confianca": 0.87,
    "contexto_roteamento": "calcular_calorias_texto",
    "requer_fluxo_estruturado": true,
    "metodo": "heuristico_keywords_v1",
    "candidatos": [
      {"intencao": "perguntar_calorias", "confianca": 0.87},
      {"intencao": "pedir_dicas", "confianca": 0.52}
    ]
  },
  "roteamento": {
    "pipeline": "tool_calculo",
    "handler": "handler_calorias_texto",
    "status": "sucesso",
    "warnings": [],
    "precisa_revisao": false,
    "metadados": {}
  }
}
```

### Campos de request recomendados em `/v1/openai/chat`
```json
{
  "prompt": "texto do usuario",
  "conversation_id": "conv_abc123",
  "usar_memoria": true,
  "metadados_conversa": {"user_id": "u-1", "canal": "mobile"},
  "plano_anexo": {
    "tipo_fonte": "imagem",
    "imagem_url": "https://example.com/plano.png"
  },
  "refeicao_anexo": {
    "tipo_fonte": "audio",
    "audio_base64": "<BASE64>",
    "nome_arquivo": "refeicao.webm",
    "inferir_quando_ausente": true
  }
}
```

### Prioridade de anexos no roteador do chat
1. `plano_anexo` (pipeline de plano alimentar)
2. `refeicao_anexo` (`imagem` ou `audio`)
3. deteccao de intencao apenas por texto (`prompt`)

### Intencoes iniciais
`enviar_plano_nutri`, `pedir_receitas`, `pedir_substituicoes`, `pedir_dicas`,
`perguntar_calorias`, `cadastrar_pratos`, `calcular_imc`, `registrar_refeicao_foto`,
`registrar_refeicao_audio`, `conversa_geral`.

### Pipelines do roteamento conversacional
`rag_conhecimento_nutricional`, `tool_calculo`, `pipeline_plano_alimentar`,
`cadastro_refeicoes`, `cadastro_pratos`, `resposta_conversacional_geral`.

### Fluxo especifico de receitas (novo)
- Intencao: `pedir_receitas`
- Handler: `handler_fluxo_receitas_personalizadas`
- Estrategia:
  - extracao de perfil do pedido (preferencias, restricoes, objetivo, contexto)
  - recuperacao de contexto nutricional via RAG
  - geracao de sugestoes praticas de receitas em formato organizado
- Resultado tecnico em `roteamento.metadados`:
  - `flow`
  - `perfil`
  - `receitas`
  - `documentos_rag`

### Fluxo especifico de substituicoes (novo)
- Intencao: `pedir_substituicoes`
- Handler: `handler_fluxo_substituicoes_personalizadas`
- Estrategia:
  - identifica alimento original e objetivo da troca
  - aplica regras de equivalencia alimentar (deterministico)
  - aciona tool de substituicoes quando contexto estiver incompleto
- Resultado tecnico em `roteamento.metadados`:
  - `flow`
  - `perfil`
  - `substituicoes_regra`
  - `tool_fallback_utilizada`
  - `tool_fallback`

### Fluxo especifico de calorias/macros (novo)
- Intencao: `perguntar_calorias`
- Handler principal: `handler_fluxo_calorias_macros`
- Estrategia:
  - perguntas conceituais -> `consultar_conhecimento_nutricional` (apoio contextual)
  - alimento unico -> tenta base estruturada (`TBCA`, fallback `TACO Online`)
  - combinacao/refeicao ou erro de base -> tools deterministicas (`calcular_calorias` / `calcular_macros`)
- Resultado tecnico em `roteamento.metadados`:
  - `flow`
  - `route` (`apoio_contextual`, `base_estruturada_tbca`, `base_estruturada_taco`, `tool_*`)
  - `analysis` (classificacao da consulta e gramas detectado)
  - `tool_name` e `tool_metadados` quando houver tool
  - `structured_result` quando usar base estruturada

### Fluxo especifico de cadastro de pratos/refeicoes (novo)
- Intencao: `cadastrar_pratos`
- Handler principal: `handler_fluxo_cadastro_refeicoes`
- Estrategia:
  - interpreta mensagem livre do usuario para extrair `tipo_registro`, `nome_registro`, `itens` e `quantidades`
  - quando a extracao for ambigua, gera perguntas de confirmacao para validar antes de salvar
  - aplica fallback para tool de cadastro existente quando a extracao principal vier incompleta
- Regra de qualidade:
  - baixa confianca ou ambiguidade -> `precisa_revisao=true`
- Resultado tecnico em `roteamento.metadados`:
  - `flow` (`cadastro_refeicoes_texto_v1`)
  - `confianca_media`
  - `cadastro_extraido`
  - `perguntas_confirmacao`
  - `tool_fallback` (quando aplicado)
  - `contrato_multimodal` (base pronta para `audio_transcrito` e `foto_ocr`)

### Fluxo especifico de registro de refeicao por foto/audio (novo)
- Intencoes: `registrar_refeicao_foto`, `registrar_refeicao_audio`
- Handlers:
  - `handler_cadastro_refeicao_foto`
  - `handler_cadastro_refeicao_audio`
- Estrategia:
  - foto: identificacao da imagem + estimativa de porcoes
  - audio: transcricao + interpretacao de porcoes
- Regra de qualidade:
  - sinais de baixa confianca/ambiguidade -> `precisa_revisao=true`
- Resultado tecnico em `roteamento.metadados`:
  - `flow` (`registro_refeicao_foto_v1` ou `registro_refeicao_audio_v1`)
  - `origem_entrada` (`foto` ou `audio`)
  - `cadastro_extraido` (itens e quantidades para confirmacao no app)

## Base RAG Conversacional (nutricao)
### Escopo
RAG e acionado quando a intencao detectada for de consulta de conhecimento, dicas,
explicacoes ou apoio contextual (ex.: receitas/substituicoes).

### Componentes
1. `NutritionKnowledgeLoader`: ingestao de `knowledge/` (`.md`, `.txt`, `.json`).
2. `SlidingWindowChunker`: fragmentacao configuravel por tamanho e overlap.
3. `TextEmbedder`: provider `hash` (local) ou `openai` (producao).
4. `InMemoryVectorIndex`: index vetorial inicial para busca por similaridade.
5. `RagContextBuilder`: montagem de contexto textual + metadados de fonte.
6. `NutritionRagService`: orquestracao de ingestao/retrieval/contexto.
7. `rag.vector_store`: fachada para consumo das tools e do roteador.

### Fronteira de responsabilidade
- RAG:
  - respostas baseadas em conhecimento textual contextual.
- Tools deterministicas:
  - calculos e regras fixas (ex.: IMC, macros, calorias, validacoes).
- Regra:
  - nao mover logica deterministica para RAG.

### Orquestracao interna de chat (engine)
- Interface publica estavel: `AiOrchestrator.orchestrate_chat` (alias legado `execute_chat` mantido).
- Engine configuravel via `CHAT_ORCHESTRATOR_ENGINE`:
  - `langgraph`: grafo `entrada -> detectar_intencao -> rotear_intencao -> executar_pipeline -> compor_resposta -> saida_final`
  - `legacy`: fluxo sequencial equivalente (fallback).

## Contrato interno das tools de chat (nutricao)
As tools ficam desacopladas do grafo e do endpoint, com contrato unico de execucao.

### Entrada
```json
{
  "tool_name": "calcular_calorias",
  "prompt": "quantas calorias tem 1 banana",
  "idioma": "pt-BR",
  "intencao": {
    "intencao": "perguntar_calorias",
    "confianca": 0.89,
    "contexto_roteamento": "calcular_calorias_texto",
    "requer_fluxo_estruturado": true
  },
  "metadados": {}
}
```

### Saida
```json
{
  "tool_name": "calcular_calorias",
  "status": "sucesso",
  "resposta": "Estimativa total: 89.0 kcal.",
  "warnings": [],
  "precisa_revisao": false,
  "metadados": {}
}
```

### Tools iniciais
- `calcular_calorias`
- `calcular_macros`
- `calcular_imc`
- `buscar_receitas`
- `sugerir_substituicoes`
- `cadastrar_prato`
- `consultar_conhecimento_nutricional`

## Regras De Governanca
1. O app nao chama agentes diretamente.
2. Todo contexto novo precisa:
   - schema de request/response,
   - teste de contrato,
   - mapeamento no BFF.
3. Mudanca breaking exige nova versao de contrato (`v2`) e rollout por feature flag.

## Mapeamento De Responsabilidade
1. App: UX, captura de entrada, revisao humana, exibicao.
2. BFF: auth, rate limit, retry/timeout, observabilidade, contrato estavel para app.
3. Camada de agentes: inferencia, scraping, OCR, normalizacao, estruturacao.
