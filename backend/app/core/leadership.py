"""
Distributed Leadership Election & Monotonic Fencing — Section 13
Ensures only one execution authority actively submits orders for a given trading scope.
Implements lease duration (3s), renewal interval (1s), expiry, and monotonic fencing tokens.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional


logger = logging.getLogger("app.core.leadership")


class LeaderLease:
    """
    Represents an active execution leadership lease with a monotonic fencing token.
    """

    def __init__(
        self,
        scope: str,
        leader_id: str,
        fencing_token: int,
        expires_at_monotonic: float,
        lease_duration_seconds: float = 3.0,
    ) -> None:
        self.scope = scope
        self.leader_id = leader_id
        self.fencing_token = fencing_token
        self.expires_at_monotonic = expires_at_monotonic
        self.lease_duration_seconds = lease_duration_seconds
        self.acquired_at_utc = int(time.time() * 1000)

    @property
    def is_valid(self) -> bool:
        """Returns True if the lease has not expired locally."""
        return time.monotonic() < self.expires_at_monotonic

    def time_remaining_seconds(self) -> float:
        return max(0.0, self.expires_at_monotonic - time.monotonic())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "leader_id": self.leader_id,
            "fencing_token": self.fencing_token,
            "is_valid": self.is_valid,
            "time_remaining_seconds": round(self.time_remaining_seconds(), 3),
            "acquired_at_utc": self.acquired_at_utc,
        }


class LeaderElection:
    """
    Distributed Leader Election coordinator with monotonic fencing tokens.
    """

    def __init__(
        self,
        lease_duration_seconds: float = 3.0,
        renewal_interval_seconds: float = 1.0,
    ) -> None:
        self.lease_duration_seconds = lease_duration_seconds
        self.renewal_interval_seconds = renewal_interval_seconds
        self._in_memory_leases: Dict[str, LeaderLease] = {}
        self._highest_fencing_tokens: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._renewal_tasks: Dict[str, asyncio.Task] = {}
        self._active_leases: Dict[str, LeaderLease] = {}

    async def acquire_lease(self, scope: str, leader_id: Optional[str] = None) -> Optional[LeaderLease]:
        """
        Attempt to acquire or steal an expired leadership lease for a given trading scope.
        Increments the monotonic fencing token upon election.
        """
        lid = leader_id or f"worker_{uuid.uuid4().hex[:8]}"
        async with self._lock:
            current = self._in_memory_leases.get(scope)
            now_mono = time.monotonic()

            if current is not None and current.is_valid:
                if current.leader_id == lid:
                    # Self renewal
                    current.expires_at_monotonic = now_mono + self.lease_duration_seconds
                    return current
                # Scope has an active unexpired leader
                logger.debug("Lease for scope '%s' held by '%s' (expires in %.2fs)", scope, current.leader_id, current.time_remaining_seconds())
                return None

            # Leader expired or new election -> issue higher monotonic fencing token
            token = self._highest_fencing_tokens.get(scope, 0) + 1
            self._highest_fencing_tokens[scope] = token

            lease = LeaderLease(
                scope=scope,
                leader_id=lid,
                fencing_token=token,
                expires_at_monotonic=now_mono + self.lease_duration_seconds,
                lease_duration_seconds=self.lease_duration_seconds,
            )
            self._in_memory_leases[scope] = lease
            self._active_leases[scope] = lease
            logger.info("Leadership lease ACQUIRED for scope '%s' by '%s' with fencing_token=%d", scope, lid, token)
            return lease

    async def renew_lease(self, scope: str, leader_id: str, fencing_token: int) -> bool:
        """
        Renew an active lease before expiry.
        """
        async with self._lock:
            current = self._in_memory_leases.get(scope)
            if (
                current is not None
                and current.leader_id == leader_id
                and current.fencing_token == fencing_token
                and current.is_valid
            ):
                current.expires_at_monotonic = time.monotonic() + self.lease_duration_seconds
                return True
            logger.warning("Failed to renew lease for scope '%s' by '%s' (fencing_token=%d)", scope, leader_id, fencing_token)
            return False

    async def step_down(self, scope: str, leader_id: str) -> None:
        """
        Voluntarily step down from leadership.
        """
        async with self._lock:
            current = self._in_memory_leases.get(scope)
            if current is not None and current.leader_id == leader_id:
                current.expires_at_monotonic = 0
                logger.info("Leader '%s' STEPPED DOWN for scope '%s'", leader_id, scope)
            if scope in self._renewal_tasks:
                self._renewal_tasks[scope].cancel()
                del self._renewal_tasks[scope]
            if scope in self._active_leases:
                del self._active_leases[scope]

    def verify_authority(self, scope: str, leader_id: str, fencing_token: int) -> bool:
        """
        Verifies if the given authority currently holds a valid unexpired lease with the expected fencing token.
        """
        current = self._in_memory_leases.get(scope)
        if current is None:
            return False
        return (
            current.is_valid
            and current.leader_id == leader_id
            and current.fencing_token == fencing_token
        )

    def get_current_lease(self, scope: str) -> Optional[LeaderLease]:
        current = self._in_memory_leases.get(scope)
        if current is not None and current.is_valid:
            return current
        return None

    def start_heartbeat_loop(self, scope: str, leader_id: str, fencing_token: int) -> asyncio.Task:
        """Starts background periodic lease renewal."""
        async def _loop():
            while True:
                await asyncio.sleep(self.renewal_interval_seconds)
                success = await self.renew_lease(scope, leader_id, fencing_token)
                if not success:
                    logger.critical("Lost leadership heartbeat for scope '%s'! Halting execution authority.", scope)
                    break

        task = asyncio.create_task(_loop())
        self._renewal_tasks[scope] = task
        return task


# Global Singleton
global_leader_election = LeaderElection()
