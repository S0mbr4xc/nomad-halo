import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import random
import math
from .models import Direction, LightColor, TrafficStats, VehicleStatus
from .core_threading import ThreadedController
from .core_processes import ProcessController

class TrafficGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Simulación de Tráfico - Lab 04 (Prioridad Ambulancia)")
        self.root.geometry("1000x850") # Taller for more buttons

        self.controller = None
        self.mode = tk.StringVar(value="Thread")
        self.running = False
        
        self.fps = 60
        self.animation_interval = int(1000/self.fps)
        self.tick_counter = 0 # For blinking effects

        self._init_ui()

    def _init_ui(self):
        # Control Panel
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

        # Standard Vehicles
        ttk.Label(control_frame, text="Añadir Vehículo Normal").pack(pady=5)
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="N", width=4, command=lambda: self.add_vehicle(Direction.NORTH)).grid(row=0, column=1)
        ttk.Button(btn_frame, text="S", width=4, command=lambda: self.add_vehicle(Direction.SOUTH)).grid(row=2, column=1)
        ttk.Button(btn_frame, text="E", width=4, command=lambda: self.add_vehicle(Direction.EAST)).grid(row=1, column=2)
        ttk.Button(btn_frame, text="O", width=4, command=lambda: self.add_vehicle(Direction.WEST)).grid(row=1, column=0)

        ttk.Separator(control_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # Ambulance Controls
        ttk.Label(control_frame, text="🚑 EMERGENCIA (AMBULANCIA)").pack(pady=5)
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
        
        rw = 140 # Road Width
        self.road_width = rw
        
        self.canvas.create_rectangle(0,0, w, h, fill="#5B8C5A")
        self.canvas.create_rectangle(cx - rw/2, 0, cx + rw/2, h, fill="#343837", outline="#888", width=1)
        self.canvas.create_rectangle(0, cy - rw/2, w, cy + rw/2, fill="#343837", outline="#888", width=1)
        self.canvas.create_rectangle(cx - rw/2, cy - rw/2, cx + rw/2, cy + rw/2, fill="#343837", outline="")
        self.canvas.create_line(cx, 0, cx, cy - rw/2, fill="#F1C40F", width=2, dash=(20,20)) 
        self.canvas.create_line(cx, cy + rw/2, cx, h, fill="#F1C40F", width=2, dash=(20,20)) 
        self.canvas.create_line(0, cy, cx - rw/2, cy, fill="#F1C40F", width=2, dash=(20,20)) 
        self.canvas.create_line(cx + rw/2, cy, w, cy, fill="#F1C40F", width=2, dash=(20,20)) 
        self.canvas.create_line(cx - rw/2, cy - rw/2, cx, cy - rw/2, fill="white", width=6)
        self.canvas.create_line(cx, cy + rw/2, cx + rw/2, cy + rw/2, fill="white", width=6)
        self.canvas.create_line(cx - rw/2, cy, cx - rw/2, cy + rw/2, fill="white", width=6)
        self.canvas.create_line(cx + rw/2, cy - rw/2, cx + rw/2, cy, fill="white", width=6)

    def draw_detailed_car(self, x, y, direction, color_body, is_emergency=False):
        s = 0.8
        w, h = 40 * s, 24 * s 
        
        angle = 0
        if direction == Direction.NORTH: angle = 90 
        elif direction == Direction.SOUTH: angle = 270 
        elif direction == Direction.EAST: angle = 180 
        elif direction == Direction.WEST: angle = 0

        # Draw rotated car body
        self._draw_rotated_car(x, y, 40*s, 22*s, angle, color_body, is_emergency)

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
        
        # Windshield
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
            # Draw Red Cross or just Siren
            # Siren Bumper
            blink = (self.tick_counter // 5) % 2 == 0 # Blink every 5 ticks
            siren_color = "red" if blink else "blue"
            
            # Roof light
            lx, ly = -5, 0 # Center roofish
            r = 4
            nx = lx * cos_a - ly * sin_a + cx
            ny = lx * sin_a + ly * cos_a + cy
            self.canvas.create_oval(nx-r, ny-r, nx+r, ny+r, fill=siren_color, outline="white")
            
            # Cross on roof maybe? Too small.
        else:
            # Headlights
            hl_pts = [(w/2, -h/3), (w/2, h/3)]
            for px, py in hl_pts:
                nx = px * cos_a - py * sin_a + cx
                ny = px * sin_a + py * cos_a + cy
                r = 3
                self.canvas.create_oval(nx-r, ny-r, nx+r, ny+r, fill="yellow", outline="orange")

    def update_loop(self):
        if not self.running: return

        try:
            self.tick_counter += 1
            state = self.controller.get_state()
            self.draw_scene()
            
            rw = self.road_width
            cx, cy = self.cx, self.cy
            lane_offset = rw / 4
            
            # Draw Lights
            l_offset = rw/2 + 20
            l_info = [
                (Direction.NORTH, cx - l_offset, cy - l_offset),
                (Direction.SOUTH, cx + l_offset, cy + l_offset),
                (Direction.EAST, cx + l_offset, cy - l_offset),
                (Direction.WEST, cx - l_offset, cy + l_offset)
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

            # Draw Vehicles
            for d_val, info in state.items():
                vehicles = info.get('vehicles', [])
                
                color_map = {
                    Direction.NORTH.value: "#3498DB",
                    Direction.SOUTH.value: "#E74C3C",
                    Direction.EAST.value: "#2ECC71",
                    Direction.WEST.value: "#F39C12"
                }
                
                d_enum = Direction(d_val)
                body_color_std = color_map.get(d_val, "white")
                
                for v in vehicles:
                    pos = v.position
                    body = "white" if v.is_emergency else body_color_std
                    
                    if d_enum == Direction.NORTH:
                        px, py = cx - lane_offset, (cy - rw/2) + pos
                    elif d_enum == Direction.SOUTH:
                        px, py = cx + lane_offset, (cy + rw/2) - pos
                    elif d_enum == Direction.EAST:
                        px, py = (cx + rw/2) - pos, cy - lane_offset
                    elif d_enum == Direction.WEST:
                        px, py = (cx - rw/2) + pos, cy + lane_offset
                    
                    self.draw_detailed_car(px, py, d_enum, body, v.is_emergency)

            # Stats
            if isinstance(self.controller, ProcessController):
                 while not self.controller.stats_queue.empty():
                    val = self.controller.stats_queue.get()
                    if not hasattr(self, 'local_stats_count'):
                        self.local_stats_count = 0
                        self.local_stats_wait = 0.0
                    self.local_stats_count += 1
                    self.local_stats_wait += val
                 if hasattr(self, 'local_stats_count') and self.local_stats_count > 0:
                     avg = self.local_stats_wait / self.local_stats_count 
                     self.lbl_stats.config(text=f"Vehículos Salidos: {self.local_stats_count}\nTiempo en Sistema: {avg:.1f}s")
            else:
                s = self.controller.stats
                if s.total_vehicles > 0:
                    self.lbl_stats.config(text=f"Vehículos Salidos: {s.total_vehicles}\nTiempo en Sistema: {s.average_wait_time:.1f}s")

        except Exception as e:
            print(f"GUI Error: {e}")

        self.root.after(self.animation_interval, self.update_loop)

    def start_simulation(self):
        if self.running: return
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
        if not self.running or not self.auto_traffic_running: return
        d = random.choice(list(Direction))
        # 10% chance of ambulance if none active? Maybe just user controlled.
        # Let's add slight chance of ambulance for fun
        is_amb = random.random() < 0.05
        self.add_vehicle(d, is_amb)
        self.root.after(random.randint(2000, 4000), self.auto_traffic_loop)

    def generate_random_traffic(self):
        for _ in range(4):
             self.add_vehicle(random.choice(list(Direction)))

    def stop_simulation(self):
        if not self.running: return
        self.auto_traffic_running = False
        self.controller.stop()
        self.running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def add_vehicle(self, direction, is_emergency=False):
        if self.running and self.controller:
            self.controller.add_vehicle(direction, is_emergency)
