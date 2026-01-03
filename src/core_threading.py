import threading
import time
import random
from collections import deque
from .models import Direction, LightColor, Vehicle, TrafficStats

class ThreadedTrafficLight(threading.Thread):
    def __init__(self, direction: Direction, stats: TrafficStats):
        super().__init__()
        self.direction = direction
        self.stats = stats
        self.color = LightColor.RED
        self.vehicles = deque()
        self.running = True
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)

    def add_vehicle(self, vehicle: Vehicle):
        with self.lock:
            vehicle.start_waiting_time = time.time()
            self.vehicles.append(vehicle)

    def set_color(self, color: LightColor):
        with self.lock:
            self.color = color
            self.condition.notify_all()

    def run(self):
        while self.running:
            with self.lock:
                while self.color != LightColor.GREEN and self.running:
                    # Wait until green or stopped
                    self.condition.wait(timeout=0.1)
                
                if not self.running:
                    break

                # We are Green
                if self.vehicles:
                    vehicle = self.vehicles.popleft()
                    # Simulate passing
                    vehicle.end_waiting_time = time.time()
                    self.stats.add_vehicle(vehicle)
                    # Time to pass intersection
                    time.sleep(0.5) 
                else:
                    # No vehicles, just wait a bit to avoid busy spin
                    time.sleep(0.1)

    def stop(self):
        with self.lock:
            self.running = False
            self.condition.notify_all()

class ThreadedController(threading.Thread):
    def __init__(self, stats: TrafficStats):
        super().__init__()
        self.stats = stats
        self.lights = {
            Direction.NORTH: ThreadedTrafficLight(Direction.NORTH, stats),
            Direction.SOUTH: ThreadedTrafficLight(Direction.SOUTH, stats),
            Direction.EAST: ThreadedTrafficLight(Direction.EAST, stats),
            Direction.WEST: ThreadedTrafficLight(Direction.WEST, stats),
        }
        self.running = True
        # Cycle configuration
        self.green_duration = 5
        self.yellow_duration = 2

    def start_lights(self):
        for light in self.lights.values():
            light.start()

    def stop(self):
        self.running = False
        for light in self.lights.values():
            light.stop()

    def run(self):
        self.start_lights()
        # Initial State: NS Green, EW Red
        cycle_state = 0 # 0: NS Green, 1: NS Yellow, 2: EW Green, 3: EW Yellow
        
        while self.running:
            if cycle_state == 0: # NS Green
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.GREEN)
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.RED)
                time.sleep(self.green_duration)
                cycle_state = 1
            elif cycle_state == 1: # NS Yellow
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle_state = 2
            elif cycle_state == 2: # EW Green
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.RED)
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.GREEN)
                time.sleep(self.green_duration)
                cycle_state = 3
            elif cycle_state == 3: # EW Yellow
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle_state = 0

    def _set_lights(self, directions: list, color: LightColor):
        for d in directions:
            self.lights[d].set_color(color)

    def add_vehicle(self, direction: Direction):
        # Create a new vehicle and add to the specific light
        v = Vehicle(id=str(random.randint(1000, 9999)), direction=direction, arrival_time=time.time())
        self.lights[direction].add_vehicle(v)

    def get_state(self):
        # Return state in a format compatible with GUI (similar to ProcessController)
        # return {Direction.VALUE: {'color': 'Red', 'vehicles': [v, ...]}, ...}
        state = {}
        for d, light in self.lights.items():
            with light.lock:
                state[d.value] = {
                    'color': light.color.value,
                    'vehicles': list(light.vehicles)
                }
        return state
