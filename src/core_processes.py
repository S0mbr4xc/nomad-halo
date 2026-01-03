import multiprocessing
import time
import random
from multiprocessing import Process, Pipe, Manager, Value
from .models import Direction, LightColor, Vehicle, VehicleStatus, TrafficStats

class ProcessTrafficLight(Process):
    def __init__(self, direction: Direction, pipe_conn, shared_state, stats_queue):
        super().__init__()
        self.direction = direction
        self.pipe_conn = pipe_conn
        self.shared_state = shared_state 
        self.stats_queue = stats_queue
        self.running = Value('b', True)
        
        # Sim params
        self.stop_line_pos = 0.0
        self.speed = 8.0 
        self.car_gap = 40.0
        self.spawn_pos = -400.0 
        self.end_pos = 400.0 

    def run(self):
        try:
            while self.running.value:
                try:
                    if self.pipe_conn.poll():
                        msg = self.pipe_conn.recv()
                        if msg == "STOP":
                            break
                        elif msg in [c.value for c in LightColor]:
                            self._update_color(msg)
                except (EOFError, OSError, BrokenPipeError):
                    break
                
                self._update_traffic()
                time.sleep(0.05)
        except Exception:
            pass

    def _update_color(self, color_str):
        try:
            data = self.shared_state[self.direction.value]
            data['color'] = color_str
            self.shared_state[self.direction.value] = data
        except Exception:
            pass

    def _update_traffic(self):
        try:
            data = self.shared_state[self.direction.value]
            color = data['color']
            vehicles = list(data.get('vehicles', []))
            
            active = []
            last_vehicle_pos = self.end_pos + 1000
            
            state_changed = False
            has_emergency = False
            
            for v in vehicles:
                limit = last_vehicle_pos - self.car_gap
                
                if v.position < 0 and color != LightColor.GREEN.value:
                     limit = min(limit, 0.0 - 10)
                
                curr_speed = self.speed * 1.5 if v.is_emergency else self.speed
                next_pos = v.position + curr_speed
                if next_pos > limit:
                    next_pos = limit
                
                if next_pos != v.position:
                    v.position = next_pos
                    state_changed = True
                
                if v.position > self.end_pos:
                    self.stats_queue.put(time.time() - v.arrival_time)
                else:
                    active.append(v)
                    if v.is_emergency and v.status != VehicleStatus.COMPLETED:
                        has_emergency = True
                
                last_vehicle_pos = v.position

            if state_changed or len(active) != len(vehicles):
                data['vehicles'] = active
                data['has_emergency'] = has_emergency # Sync this flag for Controller
                self.shared_state[self.direction.value] = data
        except Exception:
            pass

class ProcessController:
    def __init__(self):
        self.manager = Manager()
        self.shared_state = self.manager.dict()
        self.stats_queue = self.manager.Queue()
        
        for d in Direction:
            self.shared_state[d.value] = {
                'color': LightColor.RED.value,
                'vehicles': [],
                'has_emergency': False
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
        
        import threading
        self.cycle_thread = threading.Thread(target=self._cycle_loop)
        self.cycle_thread.start()

    def _cycle_loop(self):
        cycle_state = 0
        while self.running:
             # Check Emergency
            emergency_dirs = []
            try:
                for d_val, data in self.shared_state.items():
                    if data.get('has_emergency', False):
                        emergency_dirs.append(Direction(d_val))
            except:
                pass

            if emergency_dirs:
                target_d = emergency_dirs[0]
                compatible = [Direction.NORTH, Direction.SOUTH] if target_d in [Direction.NORTH, Direction.SOUTH] else [Direction.EAST, Direction.WEST]
                others = [d for d in Direction if d not in compatible]
                
                self._send_color_batch(compatible, LightColor.GREEN)
                self._send_color_batch(others, LightColor.RED)
                time.sleep(0.5)
                continue

            # Normal Cycle
            if cycle_state == 0: 
                self._send_color_batch([Direction.NORTH, Direction.SOUTH], LightColor.GREEN)
                self._send_color_batch([Direction.EAST, Direction.WEST], LightColor.RED)
                self._sleep_interruptible(self.green_duration)
                cycle_state = 1
            elif cycle_state == 1: 
                self._send_color_batch([Direction.NORTH, Direction.SOUTH], LightColor.YELLOW)
                self._sleep_interruptible(self.yellow_duration)
                cycle_state = 2
            elif cycle_state == 2: 
                self._send_color_batch([Direction.NORTH, Direction.SOUTH], LightColor.RED)
                self._send_color_batch([Direction.EAST, Direction.WEST], LightColor.GREEN)
                self._sleep_interruptible(self.green_duration)
                cycle_state = 3
            elif cycle_state == 3: 
                self._send_color_batch([Direction.EAST, Direction.WEST], LightColor.YELLOW)
                self._sleep_interruptible(self.yellow_duration)
                cycle_state = 0

    def _sleep_interruptible(self, duration):
        elapsed = 0
        step = 0.5
        while elapsed < duration and self.running:
            try:
                for data in self.shared_state.values():
                    if data.get('has_emergency', False):
                        return
            except:
                pass
            time.sleep(step)
            elapsed += step

    def _send_color_batch(self, directions, color):
        for d in directions:
            try:
                self.pipes[d].send(color.value)
            except OSError:
                pass

    def stop(self):
        self.running = False
        for d in self.pipes:
            try:
                self.pipes[d].send("STOP")
            except OSError:
                pass
        for p in self.processes.values():
            p.join()

    def add_vehicle(self, direction: Direction, is_emergency: bool = False):
        try:
            current_data = self.shared_state[direction.value]
            vehicles = list(current_data.get('vehicles', []))
            v = Vehicle(id=str(random.randint(1000, 9999)), direction=direction, arrival_time=time.time(), is_emergency=is_emergency)
            v.position = -400 # Spawn pos
            vehicles.append(v)
            current_data['vehicles'] = vehicles
            self.shared_state[direction.value] = current_data
        except Exception:
            pass

    def get_state(self):
        try:
            raw = self.shared_state
            res = {}
            for k, v in raw.items():
                res[k] = {
                    'color': v['color'],
                    'vehicles': list(v.get('vehicles', []))
                }
            return res
        except Exception:
            return {}
