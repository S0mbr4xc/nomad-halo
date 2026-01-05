import multiprocessing
import time
import random
from multiprocessing import Process, Pipe, Manager, Value
from .models import Direction, LightColor, Vehicle, VehicleStatus

NEXT_DIRECTION = {
    Direction.NORTH: Direction.EAST,
    Direction.EAST: Direction.SOUTH,
    Direction.SOUTH: Direction.WEST,
    Direction.WEST: Direction.NORTH,
}

class ProcessTrafficLight(Process):
    def __init__(self, direction: Direction, pipe_conn, shared_state, stats_queue):
        super().__init__()
        self.direction = direction
        self.pipe_conn = pipe_conn
        self.shared_state = shared_state
        self.stats_queue = stats_queue
        self.running = Value('b', True)

        self.speed = 8.0
        self.car_gap = 40.0
        self.spawn_pos = -400.0
        self.end_pos = 400.0

    def run(self):
        while self.running.value:
            if self.pipe_conn.poll():
                msg = self.pipe_conn.recv()
                if msg == "STOP":
                    break
                elif msg in [c.value for c in LightColor]:
                    self._update_color(msg)

            self._update_traffic()
            time.sleep(0.05)

    def _update_color(self, color_str):
        data = self.shared_state[self.direction.value]
        data['color'] = color_str
        self.shared_state[self.direction.value] = data

    def _update_traffic(self):
        data = self.shared_state[self.direction.value]
        color = data['color']
        vehicles = list(data.get('vehicles', []))

        active = []
        last_pos = self.end_pos + 1000
        has_emergency = False

        for v in vehicles:
            limit = last_pos - self.car_gap

            if v.position < 0 and color != LightColor.GREEN.value:
                limit = min(limit, -5)

            speed = self.speed * (1.5 if v.is_emergency else 1.0)
            next_pos = min(v.position + speed, limit)
            v.position = next_pos

            if v.position >= self.end_pos:
                # 🔁 MOVER A LA SIGUIENTE CALLE
                next_dir = NEXT_DIRECTION[self.direction]
                v.direction = next_dir
                v.position = self.spawn_pos

                next_data = self.shared_state[next_dir.value]
                next_vehicles = list(next_data.get('vehicles', []))
                next_vehicles.append(v)
                next_data['vehicles'] = next_vehicles
                self.shared_state[next_dir.value] = next_data
            else:
                active.append(v)
                last_pos = v.position
                if v.is_emergency:
                    has_emergency = True

        data['vehicles'] = active
        data['has_emergency'] = has_emergency
        self.shared_state[self.direction.value] = data


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
            parent, child = Pipe()
            self.pipes[d] = parent
            self.processes[d] = ProcessTrafficLight(d, child, self.shared_state, self.stats_queue)

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
        cycle = 0
        while self.running:
            emergency = [
                Direction(k) for k, v in self.shared_state.items()
                if v.get('has_emergency', False)
            ]

            if emergency:
                target = emergency[0]
                compatible = [Direction.NORTH, Direction.SOUTH] if target in [Direction.NORTH, Direction.SOUTH] else [Direction.EAST, Direction.WEST]
                others = [d for d in Direction if d not in compatible]

                self._send(compatible, LightColor.GREEN)
                self._send(others, LightColor.RED)
                time.sleep(0.5)
                continue

            if cycle == 0:
                self._send([Direction.NORTH, Direction.SOUTH], LightColor.GREEN)
                self._send([Direction.EAST, Direction.WEST], LightColor.RED)
                time.sleep(self.green_duration)
                cycle = 1
            elif cycle == 1:
                self._send([Direction.NORTH, Direction.SOUTH], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle = 2
            elif cycle == 2:
                self._send([Direction.EAST, Direction.WEST], LightColor.GREEN)
                self._send([Direction.NORTH, Direction.SOUTH], LightColor.RED)
                time.sleep(self.green_duration)
                cycle = 3
            elif cycle == 3:
                self._send([Direction.EAST, Direction.WEST], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle = 0

    def _send(self, dirs, color):
        for d in dirs:
            self.pipes[d].send(color.value)

    def stop(self):
        self.running = False
        for d in self.pipes:
            self.pipes[d].send("STOP")
        for p in self.processes.values():
            p.join()

    def add_vehicle(self, direction: Direction, is_emergency=False):
        data = self.shared_state[direction.value]
        vehicles = list(data.get('vehicles', []))
        v = Vehicle(
            id=str(random.randint(1000, 9999)),
            direction=direction,
            arrival_time=time.time(),
            is_emergency=is_emergency
        )
        v.position = -400
        vehicles.append(v)
        data['vehicles'] = vehicles
        self.shared_state[direction.value] = data

    def get_state(self):
        return {
            k: {
                'color': v['color'],
                'vehicles': list(v.get('vehicles', []))
            }
            for k, v in self.shared_state.items()
        }
