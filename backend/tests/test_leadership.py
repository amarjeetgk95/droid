"""
Distributed Leadership Election & Fencing Tests — Section 13
"""
from __future__ import annotations

import asyncio
import time
import pytest
from app.core.leadership import LeaderElection


@pytest.mark.asyncio
async def test_leader_lease_acquisition_and_renewal():
    le = LeaderElection(lease_duration_seconds=1.0, renewal_interval_seconds=0.3)
    # Acquire
    lease = await le.acquire_lease("SCOPED_ENGINE", "worker_1")
    assert lease is not None
    assert lease.is_valid is True
    assert lease.fencing_token == 1

    # Renew
    renewed = await le.renew_lease("SCOPED_ENGINE", "worker_1", fencing_token=1)
    assert renewed is True

    # Standby cannot steal while valid
    standby = await le.acquire_lease("SCOPED_ENGINE", "worker_2")
    assert standby is None

    # Step down
    await le.step_down("SCOPED_ENGINE", "worker_1")
    assert lease.is_valid is False

    # Now standby can acquire with higher monotonic fencing token (token=2)
    lease2 = await le.acquire_lease("SCOPED_ENGINE", "worker_2")
    assert lease2 is not None
    assert lease2.fencing_token == 2
    assert lease2.leader_id == "worker_2"
