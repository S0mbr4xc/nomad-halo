import multiprocessing
import time
import random
from multiprocessing import Process, Pipe, Manager, Value
from .models import Direction, LightColor, Vehicle, TrafficStats

class ProcessTrafficLight(Process):
    def __init__(self, direction: Direction, pipe_conn, shared_state, stats_queue):
        super().__init__()
        self.direction = direction
        self.pipe_conn = pipe_conn
        self.shared_state = shared_state # Manager list/dict
        self.stats_queue = stats_queue
        self.running = Value('b', True)
        self.local_vehicles = [] # We'll sync this to shared_state for GUI

    def run(self):
        while self.running.value:
            # Check for messages from Controller
            if self.pipe_conn.poll():
                msg = self.pipe_conn.recv()
                if msg == "STOP":
                    break
                elif msg in [c.value for c in LightColor]:
                    # Update local state and shared state
                    self._update_color(msg)
            
            # Logic based on current color
            current_color = self._get_color()
            
            if current_color == LightColor.GREEN.value:
                self._process_vehicles()
            
            # Sync vehicles to shared state for GUI visualization
            self._sync_shared_vehicles()
            
            time.sleep(0.1)

    def _update_color(self, color_str):
        # Update shared state dictionary
        # We need to copy, modify, and reassign to trigger Manager update if it's a nested dict?
        # A manager list of dicts is easier.
        # Let's assume shared_state is a DictProxy where keys are Directions.
        # But DictProxy properties are mutable? 
        # Safer to just update the entry.
        data = self.shared_state[self.direction.value]
        data['color'] = color_str
        self.shared_state[self.direction.value] = data

    def _get_color(self):
        return self.shared_state[self.direction.value]['color']

    def _process_vehicles(self):
        # We need to read vehicles from shared state, because "add_vehicle" might happen from main process?
        # Actually, if we spawn vehicles from main process, they should be added to shared_state.
        # So we should read from shared_state, process one, and write back.
        
        data = self.shared_state[self.direction.value]
        vehicles = list(data['vehicles']) # Copy
        
        if vehicles:
            v_data = vehicles.pop(0) # Pop first (Queue)
            # data['vehicles'] = vehicles # Atomic update? No.
            # But only this process consumes.
            # Who produces? The Controller (Main Process) produces.
            # So we have a producer-consumer on 'vehicles' list.
            # Manager list is process-safe? Yes.
            
            # Recalculate wait time
            # v_data is likely a dict or object. if it's a Vehicle object, it needs to be picklable.
            arrival = v_data.arrival_time
            now = time.time()
            wait = now - arrival
            
            # Send stats
            self.stats_queue.put(wait)
            
            # Update shared state
            data['vehicles'] = vehicles # Reassign list to notify manager
            self.shared_state[self.direction.value] = data
            
            time.sleep(0.5) # Simulate passing time

    def _sync_shared_vehicles(self):
        # If we had local generation, we would sync up. 
        # Since we use shared_state as the source of truth, we don't need to do much here
        # unless we were caching.
        pass

    def stop_process(self):
        self.running.value = False

class ProcessController:
    def __init__(self):
        self.manager = Manager()
        self.shared_state = self.manager.dict()
        self.stats_queue = self.manager.Queue()
        
        # Initialize Shared State
        for d in Direction:
            self.shared_state[d.value] = {
                'color': LightColor.RED.value,
                'vehicles': []
            }
        
        self.pipes = {}
        self.processes = {}
        
        for d in Direction:
            parent_conn, child_conn = Pipe()
            self.pipes[d] = parent_conn
            p = ProcessTrafficLight(d, child_conn, self.shared_state, self.stats_queue)
            self.processes[d] = p

        self.running = True
        self.green_duration = 5
        self.yellow_duration = 2

    def start(self):
        for p in self.processes.values():
            p.start()
            
        # Run cycle logic in a separate thread or just here if main loop?
        # The GUI will be the main loop. So this Controller needs to run in a background thread OR be a Process itself.
        # The prompt says "El controlador central coordina los procesos".
        # If I run logic here, it blocks GUI.
        # So I will run the cycle logic in a background THREAD of the Main Process (since it just sends messages via Pipe).
        self.cycle_thread = threading.Thread(target=self._cycle_loop)
        self.cycle_thread.start()

    def _cycle_loop(self):
        cycle_state = 0
        while self.running:
            if cycle_state == 0: # NS Green
                self._send_color([Direction.NORTH, Direction.SOUTH], LightColor.GREEN)
                self._send_color([Direction.EAST, Direction.WEST], LightColor.RED)
                time.sleep(self.green_duration)
                cycle_state = 1
            elif cycle_state == 1: # NS Yellow
                self._send_color([Direction.NORTH, Direction.SOUTH], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle_state = 2
            elif cycle_state == 2: # EW Green
                self._send_color([Direction.NORTH, Direction.SOUTH], LightColor.RED)
                self._send_color([Direction.EAST, Direction.WEST], LightColor.GREEN)
                time.sleep(self.green_duration)
                cycle_state = 3
            elif cycle_state == 3: # EW Yellow
                self._send_color([Direction.EAST, Direction.WEST], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle_state = 0

    def _send_color(self, directions, color):
        for d in directions:
            self.pipes[d].send(color.value)

    def stop(self):
        self.running = False
        for d in self.pipes:
            self.pipes[d].send("STOP")
        for p in self.processes.values():
            p.join()

    def add_vehicle(self, direction: Direction):
        # Add to shared state
        data = self.shared_state[direction.value]
        # We store simple objects (Vehicle is dataclass, picklable)
        v = Vehicle(id=str(random.randint(1000, 9999)), direction=direction, arrival_time=time.time())
        # Manager list proxy needs reassignment to trigger update usually, but append might work on proxy.
        # But data['vehicles'] is a standard list copy if we did data=...
        # Wait, 'vehicles': [] inside the dict.
        # To update:
        current_data = self.shared_state[direction.value] # Copy of dict?
        # Actually Manager.dict() returns a DictProxy. 
        # But the value inside is a standard dict unless we made it a Manager.list/dict too.
        # `self.shared_state[d.value] = {'color':..., 'vehicles': []}` -> The inner dict is standard.
        # So retrieving it gives a copy.
        vehicle_list = list(current_data['vehicles'])
        vehicle_list.append(v)
        current_data['vehicles'] = vehicle_list
        self.shared_state[direction.value] = current_data

    def get_state(self):
        # Helper for GUI
        return self.shared_state

import threading # Needed for cycle_thread
