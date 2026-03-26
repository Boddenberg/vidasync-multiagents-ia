CREATE TABLE IF NOT EXISTS chat_judge_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    request_id TEXT,
    conversation_id TEXT,
    message_id TEXT,
    idioma TEXT NOT NULL,
    intencao TEXT,
    pipeline TEXT,
    handler TEXT,
    summary TEXT NOT NULL,
    improvements_json TEXT NOT NULL,
    overall_score REAL NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    approved INTEGER NOT NULL CHECK (approved IN (0, 1)),
    rejection_reasons_json TEXT NOT NULL,
    coherence_score INTEGER NOT NULL,
    context_score INTEGER NOT NULL,
    correctness_score INTEGER NOT NULL,
    efficiency_score INTEGER NOT NULL,
    fidelity_score INTEGER NOT NULL,
    quality_score INTEGER NOT NULL,
    usefulness_score INTEGER NOT NULL,
    safety_score INTEGER NOT NULL,
    tone_of_voice_score INTEGER NOT NULL,
    weighted_contributions_json TEXT NOT NULL,
    result_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_judge_evaluations_created_at
ON chat_judge_evaluations (created_at);

CREATE INDEX IF NOT EXISTS idx_chat_judge_evaluations_request_id
ON chat_judge_evaluations (request_id);

CREATE INDEX IF NOT EXISTS idx_chat_judge_evaluations_conversation_id
ON chat_judge_evaluations (conversation_id);

CREATE INDEX IF NOT EXISTS idx_chat_judge_evaluations_message_id
ON chat_judge_evaluations (message_id);

CREATE INDEX IF NOT EXISTS idx_chat_judge_evaluations_pipeline_decision
ON chat_judge_evaluations (pipeline, decision);
