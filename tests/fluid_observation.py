"""Exercise the real vanilla water scheduler and callback, without extending construction."""
import unittest
from observation import ObservationRuntimeIntegration
from integration import TASK_ID


class FluidObservationIntegration(ObservationRuntimeIntegration):
    async def test_real_mcp_server_contract(self):
        await self._connect()
        try:
            for session in self.sessions:
                self.assert_ok(await self.call(session, "start_attempt", {"task_id": TASK_ID}))
                source = await self.call(session, "__test_water_source")
                self.assert_ok(source)
                queued = source["final"]["state"]["fluid_ticks"]
                self.assertTrue(queued, source)
                self.assertTrue(all({"trigger_tick", "priority", "sub_tick_order", "type"}.issubset(row) for row in queued))
                trace = await self.call(session, "advance", {"ticks": 6, "trace": True})
                self.assert_ok(trace)
                self.assertTrue(trace["continuity"]["complete"], trace)
                events = await self.pages(session, trace["intratick_events"], 256)
                callbacks = [row for row in events if row["kind"] == "scheduled_fluid_tick"]
                self.assertTrue(callbacks, events)
                self.assertTrue(all(row["phase"] == "scheduled_fluid_ticks" for row in callbacks))
                self.assertTrue(any(row["kind"] == "fluid_tick_schedule_requested" for row in events))
                final = await self.snapshot(session, trace["final"])
                self.assertEqual(final[(1037, 79, 1037)]["block"], "minecraft:water")
        finally:
            await self.stack.aclose()


if __name__ == "__main__":
    unittest.main(defaultTest="FluidObservationIntegration", verbosity=2)
