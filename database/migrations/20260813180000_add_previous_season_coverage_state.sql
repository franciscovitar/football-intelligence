\set ON_ERROR_STOP on

begin;

-- Block 15 corrective pass: a `current`-role provider's probe can verify
-- real data from the latest *completed* season (e.g. a season file that has
-- not been published yet, so the job fell back to the prior one) without
-- that data ever being the true current period. `current_available` must
-- never be claimed from that evidence -- but it must not be discarded
-- either, so a new state reports it honestly and separately.
alter table ingestion.coverage_snapshots
    drop constraint coverage_snapshots_state_check;

alter table ingestion.coverage_snapshots
    add constraint coverage_snapshots_state_check
    check (
        state in (
            'current_available',
            'historical_only',
            'previous_season',
            'partial',
            'token_required',
            'not_probed',
            'missing',
            'unsupported'
        )
    );

commit;
