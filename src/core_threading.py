import threading
import time
import random
from collections import deque
from .models import Direction, LightColor, Vehicle, VehicleStatus, TrafficStats

class ThreadedTrafficLight(threading.Thread):
    def __init__(self, direction: Direction, stats: TrafficStats):
        super().__init__()
        self.direction = direction
        self.stats = stats
        self.color = LightColor.RED
        self.vehicles = [] 
        self.running = True
        self.lock = threading.Lock()
        
        self.stop_line_pos = 0.0
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
            for v in self.vehicles:
                if v.is_emergency and v.status != VehicleStatus.COMPLETED:
                    # If it's already past the stop line significantly, maybe we don't need to hold green?
                    # But safer to hold until completed or far enough.
                    if v.position < self.end_pos: 
                        return True
        return False

    def run(self):
        while self.running:
            with self.lock:
                active = []
                last_vehicle_pos = self.end_pos + 1000 
                
                for v in self.vehicles:
                    limit = last_vehicle_pos - self.car_gap
                    
                    if v.position < 0 and self.color != LightColor.GREEN:
                        # Allow emergency vehicles to creep closer or run red? No, safety first -> force Controller to Green.
                        limit = min(limit, 0.0 - 10)
                    
                    # Logic: Emergency vehicles might move faster?
                    current_speed = self.speed * 1.5 if v.is_emergency else self.speed
                    
                    next_pos = v.position + current_speed
                    
                    if next_pos > limit:
                        next_pos = limit
                    
                    v.position = next_pos
                    
                    if v.position > self.end_pos:
                        v.status = VehicleStatus.COMPLETED
                        self.stats.add_vehicle(v)
                    else:
                        active.append(v)
                    
                    last_vehicle_pos = v.position
                
                self.vehicles = active

            time.sleep(0.05)

    def stop(self):
        self.running = False

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
        cycle_state = 0 
        
        while self.running:
            # 1. Check Emergency Override
            emergency_dirs = []
            for d, l in self.lights.items():
                if l.has_emergency_waiting():
                    emergency_dirs.append(d)
            
            if emergency_dirs:
                self.emergency_mode = True
                # Prioritize the first one found or all compatible?
                # Simplify: Give Green to the direction of the first emergency found.
                target_d = emergency_dirs[0]
                
                # Check compatible (Opposite is safe usually in real life, but here intersections cross)
                # Standard: N & S are compatible. E & W are compatible.
                compatible = []
                if target_d in [Direction.NORTH, Direction.SOUTH]:
                    compatible = [Direction.NORTH, Direction.SOUTH]
                else:
                    compatible = [Direction.EAST, Direction.WEST]
                
                # Force Green for compatible
                others = [d for d in self.lights if d not in compatible]
                
                # Switch to Yellow then Red for others first if they are Green?
                # For responsiveness, we force Red immediately on others and Green on Target.
                # Or do safety transition? Prompt says "not stay stopped". Responsiveness > Realism here.
                
                self._set_lights(compatible, LightColor.GREEN)
                self._set_lights(others, LightColor.RED)
                
                time.sleep(0.5) # Fast check loop during emergency
                continue
            
            self.emergency_mode = False

            # Normal Cycle
            if cycle_state == 0: # NS Green
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.GREEN)
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.RED)
                self._sleep_interruptible(self.green_duration)
                cycle_state = 1
            elif cycle_state == 1: # NS Yellow
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.YELLOW)
                self._sleep_interruptible(self.yellow_duration)
                cycle_state = 2
            elif cycle_state == 2: # EW Green
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.RED)
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.GREEN)
                self._sleep_interruptible(self.green_duration)
                cycle_state = 3
            elif cycle_state == 3: # EW Yellow
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.YELLOW)
                self._sleep_interruptible(self.yellow_duration)
                cycle_state = 0

    def _sleep_interruptible(self, duration):
        # Sleep in small chunks to react to emergency
        elapsed = 0
        step = 0.5
        while elapsed < duration and self.running:
            # Check emergency
            for l in self.lights.values():
                if l.has_emergency_waiting():
                    return # Exit sleep early to handle emergency loop
            time.sleep(step)
            elapsed += step

    def _set_lights(self, directions: list, color: LightColor):
        for d in directions:
            self.lights[d].set_color(color)

    def add_vehicle(self, direction: Direction, is_emergency: bool = False):
        v = Vehicle(id=str(random.randint(1000, 9999)), direction=direction, arrival_time=time.time(), is_emergency=is_emergency)
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
