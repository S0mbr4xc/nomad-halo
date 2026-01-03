import os
import sys
import time
import unittest

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from src.models import Direction, TrafficStats, LightColor
from src.core_threading import ThreadedController
from src.core_processes import ProcessController

class TestTrafficSimulation(unittest.TestCase):
    def test_threaded_controller(self):
        print("Testing Threaded Controller...")
        stats = TrafficStats()
        controller = ThreadedController(stats)
        controller.start()
        
        # Add vehicles
        controller.add_vehicle(Direction.NORTH)
        controller.add_vehicle(Direction.EAST)
        
        # Run for a bit (cover a cycle transition)
        # Cycle is 5s Green + 2s Yellow = 7s per phase.
        # Total cycle ~14s.
        # We'll run for 2s just to check it doesn't crash and threads are alive.
        time.sleep(2)
        
        state = controller.get_state()
        self.assertTrue(state)
        self.assertIn(Direction.NORTH.value, state)
        print(f"Thread State Sample: {state[Direction.NORTH.value]}")
        
        controller.stop()
        print("Threaded Controller OK.")

    def test_process_controller(self):
        print("Testing Process Controller...")
        controller = ProcessController()
        controller.start()
        
        controller.add_vehicle(Direction.NORTH)
        
        time.sleep(2)
        
        state = controller.get_state()
        self.assertTrue(state)
        self.assertIn(Direction.NORTH.value, state)
        
        # Check if color is set (Red or Green)
        color = state[Direction.NORTH.value]['color']
        print(f"Process State Sample: {state[Direction.NORTH.value]}")
        self.assertTrue(color in [c.value for c in LightColor])
        
        controller.stop()
        print("Process Controller OK.")

if __name__ == '__main__':
    unittest.main()
