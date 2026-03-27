-- water daily intake + nutrition goals

CREATE OR REPLACE FUNCTION public.set_updated_at_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TABLE IF NOT EXISTS public.water_daily_intake (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    date TEXT NOT NULL,
    goal_ml INTEGER,
    consumed_ml INTEGER NOT NULL DEFAULT 0 CHECK (consumed_ml >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_water_daily_intake_user_date UNIQUE (user_id, date),
    CONSTRAINT ck_water_daily_intake_goal_non_negative CHECK (goal_ml IS NULL OR goal_ml >= 0)
);
CREATE INDEX IF NOT EXISTS idx_water_daily_intake_user_id ON public.water_daily_intake(user_id);
CREATE INDEX IF NOT EXISTS idx_water_daily_intake_user_date ON public.water_daily_intake(user_id, date DESC);
DROP TRIGGER IF EXISTS trg_water_daily_intake_updated_at ON public.water_daily_intake;
CREATE TRIGGER trg_water_daily_intake_updated_at
BEFORE UPDATE ON public.water_daily_intake
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at_timestamp();
ALTER TABLE public.water_daily_intake DISABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS public.daily_nutrition_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    date TEXT NOT NULL,
    calories_goal INTEGER,
    protein_goal INTEGER,
    carbs_goal INTEGER,
    fat_goal INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_daily_nutrition_goals_user_date UNIQUE (user_id, date),
    CONSTRAINT ck_daily_nutrition_goals_calories_non_negative CHECK (calories_goal IS NULL OR calories_goal >= 0),
    CONSTRAINT ck_daily_nutrition_goals_protein_non_negative CHECK (protein_goal IS NULL OR protein_goal >= 0),
    CONSTRAINT ck_daily_nutrition_goals_carbs_non_negative CHECK (carbs_goal IS NULL OR carbs_goal >= 0),
    CONSTRAINT ck_daily_nutrition_goals_fat_non_negative CHECK (fat_goal IS NULL OR fat_goal >= 0)
);
CREATE INDEX IF NOT EXISTS idx_daily_nutrition_goals_user_id ON public.daily_nutrition_goals(user_id);
CREATE INDEX IF NOT EXISTS idx_daily_nutrition_goals_user_date ON public.daily_nutrition_goals(user_id, date DESC);
DROP TRIGGER IF EXISTS trg_daily_nutrition_goals_updated_at ON public.daily_nutrition_goals;
CREATE TRIGGER trg_daily_nutrition_goals_updated_at
BEFORE UPDATE ON public.daily_nutrition_goals
FOR EACH ROW
EXECUTE FUNCTION public.set_updated_at_timestamp();
ALTER TABLE public.daily_nutrition_goals DISABLE ROW LEVEL SECURITY;
