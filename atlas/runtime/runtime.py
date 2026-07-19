"""
Atlas Runtime

Central runtime environment for Atlas.
"""

from __future__ import annotations

import time
from datetime import datetime

from atlas.runtime.health import RuntimeHealth
from atlas.runtime.heartbeat import Heartbeat
from atlas.runtime.metrics import RuntimeMetrics
from atlas.runtime.runtime_events import RuntimeEvents
from atlas.runtime.runtime_state import RuntimeState


class AtlasRuntime:
    """
    Atlas execution runtime.
    """

    def __init__(
        self,
        kernel,
        state_manager=None,
        event_bus=None,
        tick_interval: float = 0.05,
        heartbeat_interval: int = 20,
    ):

        self.kernel = kernel

        self.state_manager = state_manager

        self.event_bus = event_bus

        self.tick_interval = tick_interval

        self.state = RuntimeState()

        self.metrics = RuntimeMetrics(
            self.state
        )

        self.heartbeat = Heartbeat(
            event_bus=event_bus,
            interval=heartbeat_interval,
        )

        self.health = RuntimeHealth(
            self.state
        )


    def start(self):

        if self.state.running:
            return

        self.state.running = True

        self.state.started_at = datetime.now()

        self.state.last_tick = None

        self.state.tick_count = 0

        self.state.healthy = True

        if self.state_manager:
            self.state_manager.update(
                {
                    "runtime": "active",
                }
            )

        if self.event_bus:
            self.event_bus.publish(
                RuntimeEvents.STARTED,
                {
                    "time": self.state.started_at.isoformat(),
                },
            )


    def run(self):

        self.start()

        while self.state.running:

            self.kernel.tick()

            self.state.tick_count += 1

            self.state.last_tick = datetime.now()


            health = self.health.check()


            if self.heartbeat.should_publish(
                self.state.tick_count,
            ):

                self.heartbeat.publish(
                    tick_count=self.state.tick_count,
                    uptime=self.metrics.uptime,
                    tps=self.metrics.ticks_per_second,
                )


            time.sleep(
                self.tick_interval
            )


    def stop(self):

        if not self.state.running:
            return

        self.state.running = False


        if self.state_manager:
            self.state_manager.update(
                {
                    "runtime": "inactive",
                }
            )


        if self.event_bus:
            self.event_bus.publish(
                RuntimeEvents.STOPPED,
                {},
            )


    def status(self):

        return {
            "running": self.state.running,

            "health": self.health.check(),

            "started_at": (
                self.state.started_at.isoformat()
                if self.state.started_at
                else None
            ),

            "last_tick": (
                self.state.last_tick.isoformat()
                if self.state.last_tick
                else None
            ),

            "tick_count": self.state.tick_count,

            **self.metrics.snapshot(),

            "tick_interval": self.tick_interval,

            "heartbeat_interval": self.heartbeat.interval,
        }