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
        
        self.base_speed = 8.0
        self.base_car_gap = 40.0
        self.spawn_pos = -200.0  # Ajustado para coincidir con visual
        self.end_pos = 700.0     # Ajustado para que completen toda la calle
    
    def get_dynamic_params(self, controller):
        """Obtener velocidad y gap dinámicos según el ciclo"""
        cycle_num = controller.get_current_cycle()
        cycle_mod = (cycle_num % 10) + 1
        
        if cycle_mod >= 8:
            # Ciclos 8-10: HORA PICO - más rápido y más juntos
            speed = self.base_speed * 1.5  # 50% más rápido
            gap = self.base_car_gap * 0.6  # 40% menos espacio
        else:
            # Ciclos normales
            speed = self.base_speed
            gap = self.base_car_gap
        
        return speed, gap

    def add_vehicle(self, vehicle: Vehicle):
        with self.lock:
            vehicle.position = self.spawn_pos
            vehicle.arrival_time = time.time()
            if not hasattr(vehicle, 'laps_completed'):
                vehicle.laps_completed = 0  # Contador de vueltas
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
                # Obtener parámetros dinámicos según el ciclo
                if hasattr(self, 'controller'):
                    speed, car_gap = self.get_dynamic_params(self.controller)
                else:
                    speed = self.base_speed
                    car_gap = self.base_car_gap
                
                active = []
                last_pos = self.end_pos + 1000
                self.has_emergency = False

                for v in self.vehicles:
                    limit = last_pos - car_gap

                    # LÓGICA DE CRUCE CORREGIDA:
                    # Si el vehículo está ANTES de la línea blanca (pos < 0)
                    # y la luz es roja → DETENER
                    # Si el vehículo YA CRUZÓ (pos >= 0) y hay tráfico perpendicular
                    # → Puede avanzar SOLO hasta el borde de la manzana (200) y DETENER
                    
                    already_crossed = v.position >= 0
                    at_manzana_edge = v.position >= 200
                    perpendicular_traffic = self._check_perpendicular_traffic()
                    
                    if v.position < 0 and self.color != LightColor.GREEN:
                        # CASO 1: Antes de cruzar con luz roja → DETENER
                        limit = min(limit, -5)
                    elif already_crossed and not at_manzana_edge and perpendicular_traffic:
                        # CASO 2: Ya cruzó pero no llegó al borde → puede avanzar hasta 200
                        limit = max(min(limit, 200), v.position)
                    elif at_manzana_edge and perpendicular_traffic:
                        # CASO 3: Ya llegó al borde de la manzana → DETENER ahí
                        limit = min(limit, v.position)

                    # Aplicar velocidad (emergencias más rápidas)
                    current_speed = speed * (1.5 if v.is_emergency else 1.0)
                    next_pos = min(v.position + current_speed, limit)
                    v.position = next_pos

                    if v.position >= self.end_pos:
                        # Incrementar contador de vueltas
                        if not hasattr(v, 'laps_completed'):
                            v.laps_completed = 0
                        v.laps_completed += 1
                        
                        # Eliminar después de 4 vueltas completas
                        if v.laps_completed >= 4:
                            # Vehículo completó su recorrido - registrar estadística
                            if hasattr(self, 'controller') and self.controller:
                                with self.controller.completed_lock:
                                    self.controller.completed_vehicles += 1
                            # No agregarlo a la siguiente dirección (se elimina)
                            continue
                        
                        # Continuar a la siguiente dirección
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
    
    def _check_perpendicular_traffic(self):
        """Verificar si hay tráfico activo en direcciones perpendiculares"""
        # Determinar direcciones perpendiculares
        if self.direction in [Direction.NORTH, Direction.SOUTH]:
            perpendicular = [Direction.EAST, Direction.WEST]
        else:
            perpendicular = [Direction.NORTH, Direction.SOUTH]
        
        # Verificar si alguna dirección perpendicular tiene luz verde
        for perp_dir in perpendicular:
            perp_light = self.shared_lights.get(perp_dir)
            if perp_light and perp_light.color == LightColor.GREEN:
                return True
        return False

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
            # Agregar referencia al controller para obtener el ciclo
            self.lights[direction].controller = self
        
        self.running = True
        self.green_duration = 6  # Aumentado para que pasen más vehículos
        self.yellow_duration = 2
        self.all_red_duration = 1  # Reducido para ciclos más rápidos
        self.emergency_mode = False
        self.current_cycle_number = 0  # Contador de ciclos completos
        self.cycle_lock = threading.Lock()  # Para acceso seguro al contador
        self.completed_vehicles = 0  # Vehículos que completaron 4 vueltas
        self.completed_lock = threading.Lock()

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
                # Horizontal en VERDE
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.GREEN)
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.RED)
                time.sleep(self.green_duration)
                cycle = 1
                
            elif cycle == 1:
                # Horizontal en AMARILLO
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle = 2
                
            elif cycle == 2:
                # TODOS EN ROJO - Tiempo de despeje
                self._set_lights([Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST], LightColor.RED)
                time.sleep(self.all_red_duration)
                cycle = 3
                
            elif cycle == 3:
                # Vertical en VERDE
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.GREEN)
                self._set_lights([Direction.NORTH, Direction.SOUTH], LightColor.RED)
                time.sleep(self.green_duration)
                cycle = 4
                
            elif cycle == 4:
                # Vertical en AMARILLO
                self._set_lights([Direction.EAST, Direction.WEST], LightColor.YELLOW)
                time.sleep(self.yellow_duration)
                cycle = 5
                
            elif cycle == 5:
                # TODOS EN ROJO - Tiempo de despeje
                self._set_lights([Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST], LightColor.RED)
                time.sleep(self.all_red_duration)
                cycle = 0
                # Incrementar contador de ciclos completos
                with self.cycle_lock:
                    self.current_cycle_number += 1

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

    def get_current_cycle(self):
        with self.cycle_lock:
            return self.current_cycle_number
    
    def get_completed_vehicles(self):
        with self.completed_lock:
            return self.completed_vehicles

    def get_state(self):
        state = {}
        for d, light in self.lights.items():
            with light.lock:
                state[d.value] = {
                    'color': light.color.value,
                    'vehicles': list(light.vehicles)
                }
        return state
