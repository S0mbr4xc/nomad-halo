import threading
import time
import random
from collections import deque
from .models import Direction, LightColor, Vehicle, VehicleStatus, TrafficStats

NEXT_DIRECTION = {
    Direction.NORTH: Direction.EAST,
    Direction.EAST: Direction.SOUTH,
    Direction.SOUTH: Direction.WEST,
    Direction.WEST: Direction.NORTH,
}

class ThreadedTrafficLight(threading.Thread):
    def __init__(self, direction: Direction, stats: TrafficStats, shared_lights):
        super().__init__()
        self.direction = direction
        self.stats = stats
        self.shared_lights = shared_lights
        self.color = LightColor.RED
        self.vehicles = [] 
        self.running = True
        self.lock = threading.Lock()
        self.has_emergency = False
        
        self.speed = 8.0
        self.car_gap = 40.0
        self.spawn_pos = -400.0
        self.end_pos = 400.0

    def add_vehicle(self, vehicle: Vehicle):
        with self.lock:
            vehicle.position = self.spawn_pos
            vehicle.arrival_time = time.time()
            self.vehicles.append(vehicle)

    def set_color(self, color: LightColor):
        with self.lock:
            self.color = color

    def has_emergency_waiting(self):
        with self.lock:
            return self.has_emergency

    def run(self):
        while self.running:
            with self.lock:
                active = []
                last_pos = self.end_pos + 1000
                self.has_emergency = False

                for v in self.vehicles:
                    limit = last_pos - self.car_gap

                    if v.position < 0 and self.color != LightColor.GREEN:
                        limit = min(limit, -5)

                    speed = self.speed * (1.5 if v.is_emergency else 1.0)
                    next_pos = min(v.position + speed, limit)
                    v.position = next_pos

                    if v.position >= self.end_pos:
                        next_dir = NEXT_DIRECTION[self.direction]
                        v.direction = next_dir
                        v.position = self.spawn_pos
                        
                        next_light = self.shared_lights[next_dir]
                        with next_light.lock:
                            next_light.vehicles.append(v)
                    else:
                        active.append(v)
                        last_pos = v.position
                        if v.is_emergency:
                            self.has_emergency = True

                self.vehicles = active

            time.sleep(0.05)

    def stop(self):
        self.running = False


class ThreadedController(threading.Thread):
    def __init__(self, stats: TrafficStats):
        super().__init__()
        self.stats = stats
        self.lights = {
            Direction.NORTH: None,
            Direction.SOUTH: None,
            Direction.EAST: None,
            Direction.WEST: None,
        }
        
        for direction in Direction:
            self.lights[direction] = ThreadedTrafficLight(direction, stats, self.lights)
        
        self.running = True
        self.green_duration = 4
        self.yellow_duration = 2
        self.emergency_mode = False

    def start_lights(self):
        for light in self.lights.values():
            light.start()

    def stop(self):
        self.running = False
        for light in self.lights.values():
            light.stop()

    def run(self):
        self.start_lights()
        cycle = 0
        
        while self.running:
            emergency = [d for d, l in self.lights.items() if l.has_emergency_waiting()]
            
            if emergency:
                self.emergency_mode = True
                target = emergency[0]
                
                # SINCRONIZACIÓN: NORTE+SUR (horizontal) vs ESTE+OESTE (vertical)
                if target in [Direction.NORTH, Direction.SOUTH]:
                    compatible = [Direction.NORTH, Direction.SOUTH]
                else:
                    compatible = [Direction.EAST, Direction.WEST]
                
                others = [d for d in self.lights if d not in compatible]
                
                self._set_lights(compatible, LightColor.GREEN)
                self._set_lights(others, LightColor.RED)
                
                time.sleep(0.5)
                continue
            
            self.emergency_mode = False

            # Normal Cycle
            if cycle == 0:
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.GREEN)
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.RED)
                time.sleep(self.green_duration)
                cycle = 1
                
            elif cycle == 1:
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle = 2
                
            elif cycle == 2:
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.GREEN)
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.RED)
                time.sleep(self.green_duration)
                cycle = 3
                
            elif cycle == 3:
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle = 0

    def _set_lights(self, directions: list, color: LightColor):
        for d in directions:
            self.lights[d].set_color(color)

    def add_vehicle(self, direction: Direction, is_emergency: bool = False):
        v = Vehicle(
            id=str(random.randint(1000, 9999)),
            direction=direction,
            arrival_time=time.time(),
            is_emergency=is_emergency
        )
        self.lights[direction].add_vehicle(v)

    def get_state(self):
        state = {}
        for d, light in self.lights.items():
            with light.lock:
                state[d.value] = {
                    'color': light.color.value,
                    'vehicles': list(light.vehicles)
                }
        return state