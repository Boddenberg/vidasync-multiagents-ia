-- Migration: Add fee fields to pix_receipts
-- Run this in Supabase SQL Editor (Dashboard > SQL Editor)

ALTER TABLE pix_receipts ADD COLUMN IF NOT EXISTS original_amount NUMERIC DEFAULT 0;
ALTER TABLE pix_receipts ADD COLUMN IF NOT EXISTS fee_amount NUMERIC DEFAULT 0;
ALTER TABLE pix_receipts ADD COLUMN IF NOT EXISTS total_amount NUMERIC DEFAULT 0;
