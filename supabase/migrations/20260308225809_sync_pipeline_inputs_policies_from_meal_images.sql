DO $$
DECLARE
    source_policy RECORD;
    source_count integer := 0;
    target_count integer := 0;
    target_policy_name text;
    create_sql text;
    roles_sql text;
BEGIN
    SELECT count(*)
    INTO source_count
    FROM pg_policies
    WHERE schemaname = 'storage'
      AND tablename = 'objects'
      AND (
          coalesce(policyname, '') ILIKE '%meal-images%'
          OR coalesce(qual, '') ILIKE '%meal-images%'
          OR coalesce(with_check, '') ILIKE '%meal-images%'
      );

    IF source_count = 0 THEN
        RAISE EXCEPTION 'No source policies found for bucket "meal-images" on storage.objects';
    END IF;

    FOR source_policy IN
        SELECT policyname
        FROM pg_policies
        WHERE schemaname = 'storage'
          AND tablename = 'objects'
          AND (
              coalesce(policyname, '') ILIKE '%pipeline-inputs%'
              OR coalesce(qual, '') ILIKE '%pipeline-inputs%'
              OR coalesce(with_check, '') ILIKE '%pipeline-inputs%'
          )
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON storage.objects', source_policy.policyname);
    END LOOP;

    FOR source_policy IN
        SELECT *
        FROM pg_policies
        WHERE schemaname = 'storage'
          AND tablename = 'objects'
          AND (
              coalesce(policyname, '') ILIKE '%meal-images%'
              OR coalesce(qual, '') ILIKE '%meal-images%'
              OR coalesce(with_check, '') ILIKE '%meal-images%'
          )
        ORDER BY policyname
    LOOP
        target_policy_name := replace(source_policy.policyname, 'meal-images', 'pipeline-inputs');
        target_policy_name := replace(target_policy_name, 'meal_images', 'pipeline_inputs');

        IF target_policy_name = source_policy.policyname THEN
            target_policy_name := source_policy.policyname || ' pipeline-inputs';
        END IF;

        SELECT string_agg(format('%I', role_name), ', ')
        INTO roles_sql
        FROM unnest(source_policy.roles) AS role_name;

        IF roles_sql IS NULL OR roles_sql = '' THEN
            roles_sql := 'public';
        END IF;

        create_sql := format(
            'CREATE POLICY %I ON storage.objects AS %s FOR %s TO %s',
            target_policy_name,
            source_policy.permissive,
            source_policy.cmd,
            roles_sql
        );

        IF source_policy.qual IS NOT NULL THEN
            create_sql := create_sql || format(
                ' USING (%s)',
                replace(source_policy.qual, 'meal-images', 'pipeline-inputs')
            );
        END IF;

        IF source_policy.with_check IS NOT NULL THEN
            create_sql := create_sql || format(
                ' WITH CHECK (%s)',
                replace(source_policy.with_check, 'meal-images', 'pipeline-inputs')
            );
        END IF;

        EXECUTE create_sql;
    END LOOP;

    SELECT count(*)
    INTO target_count
    FROM pg_policies
    WHERE schemaname = 'storage'
      AND tablename = 'objects'
      AND (
          coalesce(policyname, '') ILIKE '%pipeline-inputs%'
          OR coalesce(qual, '') ILIKE '%pipeline-inputs%'
          OR coalesce(with_check, '') ILIKE '%pipeline-inputs%'
      );

    IF target_count <> source_count THEN
        RAISE EXCEPTION 'Policy copy check failed. source_count=%, target_count=%', source_count, target_count;
    END IF;
END $$;
