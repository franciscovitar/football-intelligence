\set ON_ERROR_STOP on

begin;

do $$
begin
    if to_regclass('analytics.model_validation_runs') is null then
        raise exception 'model_validation_runs table is missing';
    end if;

    insert into analytics.model_validation_runs (
        model_version, hard_status, calibration_status, summary, report, calculated_at
    )
    values (
        'validation-v1.0', 'pass', 'insufficient_data',
        '{"elo_sample_size":10}'::jsonb, '{"elo":{"sample_size":10}}'::jsonb, now()
    );

    begin
        insert into analytics.model_validation_runs (
            model_version, hard_status, calibration_status, summary, report, calculated_at
        )
        values (
            'validation-v1.0', 'unknown', 'insufficient_data',
            '{}'::jsonb, '{}'::jsonb, now()
        );
        raise exception 'expected invalid hard_status to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.model_validation_runs (
            model_version, hard_status, calibration_status, summary, report, calculated_at
        )
        values (
            'validation-v1.0', 'pass', 'unknown',
            '{}'::jsonb, '{}'::jsonb, now()
        );
        raise exception 'expected invalid calibration_status to be rejected';
    exception
        when check_violation then null;
    end;
end;
$$;

rollback;
