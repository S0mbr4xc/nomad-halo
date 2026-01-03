import enum
import time
import random
from dataclasses import dataclass, field
from typing import List, Deque
from collections import deque

class Direction(enum.Enum):
    NORTH = "North"
    SOUTH = "South"
    EAST = "East"
    WEST = "West"

class LightColor(enum.Enum):
    RED = "Red"
    YELLOW = "Yellow"
    GREEN = "Green"

@dataclass
class Vehicle:
    id: str
    direction: Direction
    arrival_time: float
    start_waiting_time: float = 0.0
    end_waiting_time: float = 0.0
    
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
