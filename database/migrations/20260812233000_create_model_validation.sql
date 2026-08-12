\set ON_ERROR_STOP on

begin;

create table analytics.model_validation_runs (
    id bigint generated always as identity primary key,
    model_version text not null,
    hard_status text not null,
    calibration_status text not null,
    summary jsonb not null default '{}'::jsonb,
    report jsonb not null default '{}'::jsonb,
    calculated_at timestamptz not null,
    constraint model_validation_runs_model_version_not_blank_check
        check (btrim(model_version) <> ''),
    constraint model_validation_runs_hard_status_check
        check (hard_status in ('pass', 'fail')),
    constraint model_validation_runs_calibration_status_check
        check (calibration_status in ('pass', 'warn', 'insufficient_data')),
    constraint model_validation_runs_summary_object_check
        check (jsonb_typeof(summary) = 'object'),
    constraint model_validation_runs_report_object_check
        check (jsonb_typeof(report) = 'object')
);

create index model_validation_runs_calculated_idx
    on analytics.model_validation_runs (calculated_at desc);

revoke all on analytics.model_validation_runs from public;

commit;
