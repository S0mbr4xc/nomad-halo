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

        self.base_speed = 8.0
        self.base_car_gap = 40.0
        self.spawn_pos = -200.0  # Ajustado para coincidir con visual
        self.end_pos = 700.0     # Ajustado para que completen toda la calle

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
        
        # Obtener parámetros dinámicos según el ciclo
        # Necesitamos acceder al ciclo desde shared_state
        current_cycle = data.get('current_cycle', 0)
        cycle_mod = (current_cycle % 10) + 1
        
        if cycle_mod >= 8:
            # Ciclos 8-10: HORA PICO
            speed = self.base_speed * 1.5
            car_gap = self.base_car_gap * 0.6
        else:
            speed = self.base_speed
            car_gap = self.base_car_gap

        active = []
        last_pos = self.end_pos + 1000
        has_emergency = False

        for v in vehicles:
            limit = last_pos - car_gap

            # LÓGICA DE CRUCE CORREGIDA:
            already_crossed = v.position >= 0
            at_manzana_edge = v.position >= 200
            perpendicular_traffic = self._check_perpendicular_traffic()
            
            if v.position < 0 and color != LightColor.GREEN.value:
                # CASO 1: Antes de cruzar con luz roja → DETENER
                limit = min(limit, -5)
            elif already_crossed and not at_manzana_edge and perpendicular_traffic:
                # CASO 2: Ya cruzó pero no llegó al borde → avanzar hasta 200
                limit = max(min(limit, 200), v.position)
            elif at_manzana_edge and perpendicular_traffic:
                # CASO 3: Ya en el borde → DETENER ahí
                limit = min(limit, v.position)

            current_speed = speed * (1.5 if v.is_emergency else 1.0)
            next_pos = min(v.position + current_speed, limit)
            v.position = next_pos

            if v.position >= self.end_pos:
                # Incrementar contador de vueltas
                if not hasattr(v, 'laps_completed'):
                    v.laps_completed = 0
                v.laps_completed += 1
                
                # Eliminar después de 4 vueltas
                if v.laps_completed >= 4:
                    # Completó - incrementar contador en shared_state
                    completed_count = self.shared_state.get('completed_vehicles', 0)
                    self.shared_state['completed_vehicles'] = completed_count + 1
                    # No continuar (se elimina)
                    continue
                
                # Continuar a siguiente dirección
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
    
    def _check_perpendicular_traffic(self):
        """Verificar si hay tráfico perpendicular con luz verde"""
        if self.direction in [Direction.NORTH, Direction.SOUTH]:
            perpendicular = [Direction.EAST, Direction.WEST]
        else:
            perpendicular = [Direction.NORTH, Direction.SOUTH]
        
        for perp_dir in perpendicular:
            perp_data = self.shared_state.get(perp_dir.value, {})
            if perp_data.get('color') == LightColor.GREEN.value:
                return True
        return False


class ProcessController:
    def __init__(self):
        self.manager = Manager()
        self.shared_state = self.manager.dict()
        self.stats_queue = self.manager.Queue()

        for d in Direction:
            self.shared_state[d.value] = {
                'color': LightColor.RED.value,
                'vehicles': [],
                'has_emergency': False,
                'current_cycle': 0
            }
        
        # Contador global de vehículos completados
        self.shared_state['completed_vehicles'] = 0

        self.pipes = {}
        self.processes = {}

        for d in Direction:
            parent, child = Pipe()
            self.pipes[d] = parent
            self.processes[d] = ProcessTrafficLight(d, child, self.shared_state, self.stats_queue)

        self.running = True
        self.green_duration = 6  # Aumentado
        self.yellow_duration = 2
        self.all_red_duration = 1  # Reducido
        self.current_cycle_number = 0  # Contador de ciclos completos

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
                # SINCRONIZACIÓN: NORTE+SUR (horizontal) vs ESTE+OESTE (vertical)
                if target in [Direction.NORTH, Direction.SOUTH]:
                    compatible = [Direction.NORTH, Direction.SOUTH]
                else:
                    compatible = [Direction.EAST, Direction.WEST]
                
                others = [d for d in Direction if d not in compatible]

                self._send(compatible, LightColor.GREEN)
                self._send(others, LightColor.RED)
                time.sleep(0.5)
                continue

            # Normal Cycle - NORTE+SUR vs ESTE+OESTE
            if cycle == 0:
                # Horizontal en VERDE
                self._send([Direction.NORTH, Direction.SOUTH], LightColor.GREEN)
                self._send([Direction.EAST, Direction.WEST], LightColor.RED)
                time.sleep(self.green_duration)
                cycle = 1
                
            elif cycle == 1:
                # Horizontal en AMARILLO
                self._send([Direction.NORTH, Direction.SOUTH], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle = 2
                
            elif cycle == 2:
                # TODOS EN ROJO - Tiempo de despeje
                self._send([Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST], LightColor.RED)
                time.sleep(self.all_red_duration)
                cycle = 3
                
            elif cycle == 3:
                # Vertical en VERDE
                self._send([Direction.EAST, Direction.WEST], LightColor.GREEN)
                self._send([Direction.NORTH, Direction.SOUTH], LightColor.RED)
                time.sleep(self.green_duration)
                cycle = 4
                
            elif cycle == 4:
                # Vertical en AMARILLO
                self._send([Direction.EAST, Direction.WEST], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle = 5
                
            elif cycle == 5:
                # TODOS EN ROJO - Tiempo de despeje
                self._send([Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST], LightColor.RED)
                time.sleep(self.all_red_duration)
                cycle = 0
                # Incrementar contador de ciclos completos
                self.current_cycle_number += 1
                # Actualizar en shared_state para que los procesos lo vean
                for d in Direction:
                    data = self.shared_state[d.value]
                    data['current_cycle'] = self.current_cycle_number
                    self.shared_state[d.value] = data

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
        v.position = -200  # Ajustado para coincidir con spawn_pos
        vehicles.append(v)
        data['vehicles'] = vehicles
        self.shared_state[direction.value] = data

    def get_current_cycle(self):
        return self.current_cycle_number
    
    def get_completed_vehicles(self):
        return self.shared_state.get('completed_vehicles', 0)

    def get_state(self):
        return {
            k: {
                'color': v['color'],
                'vehicles': list(v.get('vehicles', []))
            }
            for k, v in self.shared_state.items()
        }
