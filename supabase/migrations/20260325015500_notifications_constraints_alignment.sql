-- Align notifications constraints with the app backend contract.

ALTER TABLE notifications
    DROP CONSTRAINT IF EXISTS notifications_type_check;
ALTER TABLE notifications
    DROP CONSTRAINT IF EXISTS notifications_user_id_fkey;
ALTER TABLE notifications
    ADD CONSTRAINT notifications_user_id_fkey
    FOREIGN KEY (user_id)
    REFERENCES user_profiles(user_id)
    NOT VALID;
