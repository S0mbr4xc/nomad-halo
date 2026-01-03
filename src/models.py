import enum
import time
from dataclasses import dataclass

class Direction(enum.Enum):
    NORTH = "North"
    SOUTH = "South"
    EAST = "East"
    WEST = "West"

class LightColor(enum.Enum):
    RED = "Red"
    YELLOW = "Yellow"
    GREEN = "Green"

class VehicleStatus(enum.Enum):
    WAITING = "Waiting"
    CROSSING = "Crossing"
    COMPLETED = "Completed"

@dataclass
class Vehicle:
    id: str
    direction: Direction
    arrival_time: float
    start_waiting_time: float = 0.0
    end_waiting_time: float = 0.0
    status: VehicleStatus = VehicleStatus.WAITING
    position: float = 0.0 # 0.0 is stop line, >0 is crossing, <0 is in queue (visual logic will handle queue)
    speed: float = 5.0 # pixels per update tick? Or relative units.
    is_emergency: bool = False

    @property
    def wait_time(self):
        if self.end_waiting_time > 0:
            return self.end_waiting_time - self.start_waiting_time
        return 0.0

@dataclass
class TrafficStats:
    total_vehicles: int = 0
    total_wait_time: float = 0.0
    
    def add_vehicle(self, vehicle: Vehicle):
        self.total_vehicles += 1
        self.total_wait_time += vehicle.wait_time

    @property
    def average_wait_time(self):
        if self.total_vehicles == 0:
            return 0.0
        return self.total_wait_time / self.total_vehicles
