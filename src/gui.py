import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import random
import math
import psutil
import os
from .models import Direction, LightColor, TrafficStats, VehicleStatus
from .core_threading import ThreadedController
from .core_processes import ProcessController

class TrafficGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Simulación de Tráfico - Cuenca, Ecuador")
        self.root.geometry("1000x850")

        self.controller = None
        self.mode = tk.StringVar(value="Thread")
        self.running = False
        
        self.fps = 60
        self.animation_interval = int(1000/self.fps)
        self.tick_counter = 0

        self._init_ui()

    def _init_ui(self):
        control_frame = ttk.LabelFrame(self.root, text="Configuración")
        control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        ttk.Label(control_frame, text="Modo:").pack(pady=5)
        ttk.Radiobutton(control_frame, text="Hilos (Threading)", variable=self.mode, value="Thread").pack(anchor=tk.W)
        ttk.Radiobutton(control_frame, text="Procesos (Multiprocessing)", variable=self.mode, value="Process").pack(anchor=tk.W)

        self.btn_start = ttk.Button(control_frame, text="Iniciar Simulación", command=self.start_simulation)
        self.btn_start.pack(pady=10, fill=tk.X)

        self.btn_stop = ttk.Button(control_frame, text="Detener", command=self.stop_simulation, state=tk.DISABLED)
        self.btn_stop.pack(pady=5, fill=tk.X)

        ttk.Separator(control_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Label(control_frame, text="Añadir Vehículo Normal").pack(pady=5)
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="N", width=4, command=lambda: self.add_vehicle(Direction.NORTH)).grid(row=0, column=1)
        ttk.Button(btn_frame, text="S", width=4, command=lambda: self.add_vehicle(Direction.SOUTH)).grid(row=2, column=1)
        ttk.Button(btn_frame, text="E", width=4, command=lambda: self.add_vehicle(Direction.EAST)).grid(row=1, column=2)
        ttk.Button(btn_frame, text="O", width=4, command=lambda: self.add_vehicle(Direction.WEST)).grid(row=1, column=0)

        ttk.Separator(control_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Label(control_frame, text="🚑 EMERGENCIA").pack(pady=5)
        amb_frame = ttk.Frame(control_frame)
        amb_frame.pack(fill=tk.X)
        ttk.Button(amb_frame, text="N", width=4, command=lambda: self.add_vehicle(Direction.NORTH, True)).grid(row=0, column=1)
        ttk.Button(amb_frame, text="S", width=4, command=lambda: self.add_vehicle(Direction.SOUTH, True)).grid(row=2, column=1)
        ttk.Button(amb_frame, text="E", width=4, command=lambda: self.add_vehicle(Direction.EAST, True)).grid(row=1, column=2)
        ttk.Button(amb_frame, text="O", width=4, command=lambda: self.add_vehicle(Direction.WEST, True)).grid(row=1, column=0)

        ttk.Separator(control_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        ttk.Button(control_frame, text="Tráfico Aleatorio", command=self.generate_random_traffic).pack(fill=tk.X, pady=5)

        self.lbl_stats = ttk.Label(control_frame, text="Estadísticas:\nEsperando...")
        self.lbl_stats.pack(pady=5)

        self.canvas_frame = ttk.Frame(self.root)
        self.canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="#2E3436") 
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def draw_scene(self):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        cx, cy = w // 2, h // 2
        self.cx, self.cy = cx, cy
        
        rw = 100
        self.road_width = rw
        
        mw = 400
        mh = 300
        self.manzana_width = mw
        self.manzana_height = mh
        
        # Distancia de la línea de pare desde el borde de la manzana
        self.stop_distance = 100
        
        self.canvas.create_rectangle(0, 0, w, h, fill="#5B8C5A")
        
        # Calles
        self.canvas.create_rectangle(0, cy + mh // 2, w, cy + mh // 2 + rw, fill="#343837", outline="")
        self.canvas.create_rectangle(0, cy - mh // 2 - rw, w, cy - mh // 2, fill="#343837", outline="")
        self.canvas.create_rectangle(cx + mw // 2, 0, cx + mw // 2 + rw, h, fill="#343837", outline="")
        self.canvas.create_rectangle(cx - mw // 2 - rw, 0, cx - mw // 2, h, fill="#343837", outline="")
        
        # Manzana
        self.canvas.create_rectangle(cx - mw // 2, cy - mh // 2, cx + mw // 2, cy + mh // 2, fill="#475569", outline="#cbd5e1", width=3)
        
        # === LÍNEAS BLANCAS DE PARE (alejadas de la manzana) ===
        # Cada línea está a stop_distance píxeles del borde de la manzana
        # TODAS LAS LÍNEAS SON VERTICALES (perpendiculares al flujo)
        
        # NORTE (María Arizaga) - línea VERTICAL en calle superior
        stop_x_north = cx + mw // 2 + self.stop_distance
        self.canvas.create_line(
            stop_x_north, cy - mh // 2 - rw // 2 - 30,
            stop_x_north, cy - mh // 2 - rw // 2 + 30,
            fill="white", width=6
        )
        
        # SUR (Pío Bravo) - línea VERTICAL en calle inferior
        stop_x_south = cx - mw // 2 - self.stop_distance
        self.canvas.create_line(
            stop_x_south, cy + mh // 2 + rw // 2 - 30,
            stop_x_south, cy + mh // 2 + rw // 2 + 30,
            fill="white", width=6
        )
        
        # ESTE (Tarqui) - línea HORIZONTAL en calle derecha
        stop_y_east = cy + mh // 2 + self.stop_distance
        self.canvas.create_line(
            cx + mw // 2 + rw // 2 - 30, stop_y_east,
            cx + mw // 2 + rw // 2 + 30, stop_y_east,
            fill="white", width=6
        )
        
        # OESTE (Juan Montalvo) - línea HORIZONTAL en calle izquierda
        stop_y_west = cy - mh // 2 - self.stop_distance
        self.canvas.create_line(
            cx - mw // 2 - rw // 2 - 30, stop_y_west,
            cx - mw // 2 - rw // 2 + 30, stop_y_west,
            fill="white", width=6
        )
        
        # Líneas amarillas
        self.canvas.create_line(0, cy + mh // 2 + rw // 2, w, cy + mh // 2 + rw // 2, fill="#F1C40F", width=2, dash=(20, 10))
        self.canvas.create_line(0, cy - mh // 2 - rw // 2, w, cy - mh // 2 - rw // 2, fill="#F1C40F", width=2, dash=(20, 10))
        self.canvas.create_line(cx + mw // 2 + rw // 2, 0, cx + mw // 2 + rw // 2, h, fill="#F1C40F", width=2, dash=(20, 10))
        self.canvas.create_line(cx - mw // 2 - rw // 2, 0, cx - mw // 2 - rw // 2, h, fill="#F1C40F", width=2, dash=(20, 10))
        
        # Nombres
        self.canvas.create_text(cx, cy + mh // 2 + rw + 15, text="Pío Bravo (S)", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(cx, cy - mh // 2 - rw - 15, text="María Arizaga (N)", fill="white", font=("Arial", 12, "bold"))
        self.canvas.create_text(cx + mw // 2 + rw + 50, cy, text="Tarqui (E)", fill="white", font=("Arial", 12, "bold"), angle=90)
        self.canvas.create_text(cx - mw // 2 - rw - 60, cy, text="Juan Montalvo (O)", fill="white", font=("Arial", 12, "bold"), angle=90)

    def draw_detailed_car(self, x, y, direction, color_body, is_emergency=False):
        s = 0.7
        w, h = 40 * s, 24 * s 
        
        angle = 0
        if direction == Direction.NORTH: angle = 180
        elif direction == Direction.SOUTH: angle = 0
        elif direction == Direction.EAST: angle = 270
        elif direction == Direction.WEST: angle = 90

        self._draw_rotated_car(x, y, w, h, angle, color_body, is_emergency)

    def _draw_rotated_car(self, cx, cy, w, h, angle, color, is_emergency):
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        pts = [(w/2, -h/2), (w/2, h/2), (-w/2, h/2), (-w/2, -h/2)]
        transformed = []
        for px, py in pts:
            nx = px * cos_a - py * sin_a + cx
            ny = px * sin_a + py * cos_a + cy
            transformed.append(nx)
            transformed.append(ny)
        self.canvas.create_polygon(transformed, fill=color, outline="black")
        
        wx, wy = w * 0.2, h * 0.7
        sx = w * 0.1
        w_pts = [(sx + wx/2, -wy/2), (sx + wx/2, wy/2), (sx - wx/2, wy/2), (sx - wx/2, -wy/2)]
        t_w = []
        for px, py in w_pts:
            nx = px * cos_a - py * sin_a + cx
            ny = px * sin_a + py * cos_a + cy
            t_w.append(nx)
            t_w.append(ny)
        self.canvas.create_polygon(t_w, fill="#87CEEB", outline="#555")

        if is_emergency:
            blink = (self.tick_counter // 5) % 2 == 0
            siren_color = "red" if blink else "blue"
            lx, ly = -5, 0
            r = 4
            nx = lx * cos_a - ly * sin_a + cx
            ny = lx * sin_a + ly * cos_a + cy
            self.canvas.create_oval(nx-r, ny-r, nx+r, ny+r, fill=siren_color, outline="white")
        else:
            hl_pts = [(w/2, -h/3), (w/2, h/3)]
            for px, py in hl_pts:
                nx = px * cos_a - py * sin_a + cx
                ny = px * sin_a + py * cos_a + cy
                r = 2
                self.canvas.create_oval(nx-r, ny-r, nx+r, ny+r, fill="yellow", outline="orange")

    def update_loop(self):
        if not self.running: 
            return

        try:
            self.tick_counter += 1
            state = self.controller.get_state()
            self.draw_scene()
            
            cx, cy = self.cx, self.cy
            rw = self.road_width
            mw, mh = self.manzana_width, self.manzana_height
            stop_dist = self.stop_distance
            
            # Semáforos
            l_info = [
                (Direction.NORTH, cx + mw // 2 + stop_dist + 30, cy - mh // 2 - 20),
                (Direction.SOUTH, cx - mw // 2 - stop_dist - 30, cy + mh // 2 + 20),
                (Direction.EAST, cx + mw // 2 + 20, cy + mh // 2 + stop_dist + 30),
                (Direction.WEST, cx - mw // 2 - 20, cy - mh // 2 - stop_dist - 30)
            ]
            
            for d_enum, lx, ly in l_info:
                info = state.get(d_enum.value, {})
                c = info.get('color', 'Red')
                
                self.canvas.create_rectangle(lx-10, ly-30, lx+10, ly+30, fill="#222", outline="white")
                colors = {"Red": "#500", "Yellow": "#550", "Green": "#050"}
                active_colors = {"Red": "#F00", "Yellow": "#FF0", "Green": "#0F0"}
                
                curr_r = active_colors["Red"] if c == "Red" else colors["Red"]
                curr_y = active_colors["Yellow"] if c == "Yellow" else colors["Yellow"]
                curr_g = active_colors["Green"] if c == "Green" else colors["Green"]
                
                self.canvas.create_oval(lx-6, ly-25, lx+6, ly-13, fill=curr_r)
                self.canvas.create_oval(lx-6, ly-6, lx+6, ly+6, fill=curr_y)
                self.canvas.create_oval(lx-6, ly+13, lx+6, ly+25, fill=curr_g)

            # VEHÍCULOS - Mapeo corregido para que position=0 esté en la línea blanca
            for d_val, info in state.items():
                vehicles = info.get('vehicles', [])
                
                color_map = {
                    Direction.NORTH.value: "#FF9800",
                    Direction.SOUTH.value: "#E74C3C",
                    Direction.EAST.value: "#9B59B6",
                    Direction.WEST.value: "#FFEB3B"
                }
                
                d_enum = Direction(d_val)
                body_color_std = color_map.get(d_val, "white")
                
                for v in vehicles:
                    pos = v.position
                    body = "white" if v.is_emergency else body_color_std
                    
                    if d_enum == Direction.NORTH:
                        # María Arizaga (arriba, derecha → izquierda)
                        py = cy - mh // 2 - rw // 2
                        # position=0 debe estar en stop_x = cx + mw//2 + stop_dist
                        # position=-400 debe estar a la derecha (spawn)
                        # position=400 debe estar a la izquierda (exit)
                        px = (cx + mw // 2 + stop_dist) - pos
                        
                    elif d_enum == Direction.SOUTH:
                        # Pío Bravo (abajo, izquierda → derecha)
                        py = cy + mh // 2 + rw // 2
                        # position=0 debe estar en stop_x = cx - mw//2 - stop_dist
                        px = (cx - mw // 2 - stop_dist) + pos
                        
                    elif d_enum == Direction.EAST:
                        # Tarqui (derecha, abajo ↑ arriba)
                        px = cx + mw // 2 + rw // 2
                        # position=0 debe estar en stop_y = cy + mh//2 + stop_dist
                        py = (cy + mh // 2 + stop_dist) - pos
                        
                    elif d_enum == Direction.WEST:
                        # Juan Montalvo (izquierda, arriba ↓ abajo)
                        px = cx - mw // 2 - rw // 2
                        # position=0 debe estar en stop_y = cy - mh//2 - stop_dist
                        py = (cy - mh // 2 - stop_dist) + pos
                    
                    self.draw_detailed_car(px, py, d_enum, body, v.is_emergency)

            # Stats - Información del sistema y vehículos completados
            import psutil
            import os
            
            # Información del sistema
            cpu_percent = psutil.cpu_percent(interval=0)
            memory = psutil.virtual_memory()
            memory_used = memory.percent
            
            # Obtener ciclo actual
            current_cycle = self.controller.get_current_cycle()
            cycle_mod = (current_cycle % 10) + 1  # Ciclo 1-10
            
            # Obtener vehículos completados
            completed = self.controller.get_completed_vehicles()
            
            # Contar vehículos activos POR DIRECCIÓN
            total_active = 0
            vehicles_by_dir = {}
            
            if isinstance(self.controller, ProcessController):
                for d_val, info in state.items():
                    # Filtrar solo direcciones válidas (ignorar 'completed_vehicles')
                    if d_val in ['North', 'South', 'East', 'West']:
                        count = len(info.get('vehicles', []))
                        vehicles_by_dir[d_val] = count
                        total_active += count
                
                # Contar procesos hijos
                current_process = psutil.Process(os.getpid())
                num_processes = len(current_process.children(recursive=True))
                
                stats_text = (
                    f"=== MULTIPROCESSING ===\n"
                    f"Ciclo: {cycle_mod}/10\n"
                    f"✅ Completados: {completed}\n"
                    f"🚗 En Sistema: {total_active}\n"
                    f"N:{vehicles_by_dir.get('North',0)} S:{vehicles_by_dir.get('South',0)} "
                    f"E:{vehicles_by_dir.get('East',0)} O:{vehicles_by_dir.get('West',0)}\n"
                    f"Procesos: {num_processes}\n"
                    f"CPU: {cpu_percent:.1f}% RAM: {memory_used:.1f}%"
                )
            else:
                # Para threading
                for d, light in self.controller.lights.items():
                    with light.lock:
                        count = len(light.vehicles)
                        vehicles_by_dir[d.value] = count
                        total_active += count
                
                # Contar hilos activos
                num_threads = threading.active_count()
                
                stats_text = (
                    f"=== THREADING ===\n"
                    f"Ciclo: {cycle_mod}/10\n"
                    f"✅ Completados: {completed}\n"
                    f"🚗 En Sistema: {total_active}\n"
                    f"N:{vehicles_by_dir.get('North',0)} S:{vehicles_by_dir.get('South',0)} "
                    f"E:{vehicles_by_dir.get('East',0)} O:{vehicles_by_dir.get('West',0)}\n"
                    f"Hilos: {num_threads}\n"
                    f"CPU: {cpu_percent:.1f}% RAM: {memory_used:.1f}%"
                )
            
            self.lbl_stats.config(text=stats_text)

        except Exception as e:
            print(f"GUI Error: {e}")

        self.root.after(self.animation_interval, self.update_loop)

    def start_simulation(self):
        if self.running: 
            return
        mode = self.mode.get()
        self.stats = TrafficStats()
        if mode == "Thread":
            self.controller = ThreadedController(self.stats)
        else:
            self.controller = ProcessController()
        
        self.controller.start()
        self.running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.root.after(100, self.update_loop)
        
        self.auto_traffic_running = True
        self.root.after(1000, self.auto_traffic_loop)

    def auto_traffic_loop(self):
        if not self.running or not self.auto_traffic_running: 
            return
        
        # Obtener ciclo actual (1-10)
        current_cycle = self.controller.get_current_cycle()
        cycle_mod = (current_cycle % 10) + 1
        
        # REDUCIDO: Menos vehículos para evitar atascos
        if cycle_mod <= 3:
            # Ciclos 1-3: Tráfico ligero (1 vehículo)
            num_vehicles = 1
            interval = random.randint(4000, 6000)  # Más tiempo entre generaciones
        elif cycle_mod <= 6:
            # Ciclos 4-6: Tráfico medio (1-2 vehículos)
            num_vehicles = random.randint(1, 2)
            interval = random.randint(3000, 5000)
        elif cycle_mod <= 8:
            # Ciclos 7-8: Tráfico moderado (2 vehículos)
            num_vehicles = 2
            interval = random.randint(2500, 4000)
        else:
            # Ciclos 9-10: HORA PICO (2-3 vehículos)
            num_vehicles = random.randint(2, 3)
            interval = random.randint(2000, 3000)
        
        # Agregar vehículos
        for _ in range(num_vehicles):
            d = random.choice(list(Direction))
            is_amb = random.random() < 0.03  # 3% ambulancias
            self.add_vehicle(d, is_amb)
        
        self.root.after(interval, self.auto_traffic_loop)

    def generate_random_traffic(self):
        for _ in range(4):
            self.add_vehicle(random.choice(list(Direction)))

    def stop_simulation(self):
        if not self.running: 
            return
        self.auto_traffic_running = False
        self.controller.stop()
        self.running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def add_vehicle(self, direction, is_emergency=False):
        if self.running and self.controller:
            self.controller.add_vehicle(direction, is_emergency)
