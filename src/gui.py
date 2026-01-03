import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import random
from .models import Direction, LightColor, TrafficStats
from .core_threading import ThreadedController
from .core_processes import ProcessController

class TrafficGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Simulación de Tráfico - Lab 04")
        self.root.geometry("800x600")

        self.controller = None
        self.mode = tk.StringVar(value="Thread")
        self.running = False

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

        ttk.Label(control_frame, text="Añadir Vehículo").pack(pady=5)
        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X)
        
        ttk.Button(btn_frame, text="Norte", command=lambda: self.add_vehicle(Direction.NORTH)).grid(row=0, column=1)
        ttk.Button(btn_frame, text="Sur", command=lambda: self.add_vehicle(Direction.SOUTH)).grid(row=2, column=1)
        ttk.Button(btn_frame, text="Este", command=lambda: self.add_vehicle(Direction.EAST)).grid(row=1, column=2)
        ttk.Button(btn_frame, text="Oeste", command=lambda: self.add_vehicle(Direction.WEST)).grid(row=1, column=0)

        ttk.Separator(control_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        self.lbl_stats = ttk.Label(control_frame, text="Estadísticas:\nEsperando...")
        self.lbl_stats.pack(pady=5)

        # Visualization Canvas
        self.canvas_frame = ttk.Frame(self.root)
        self.canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Draw background implementation
        self.canvas.bind("<Configure>", self.draw_intersection)

    def draw_intersection(self, event=None):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        cx, cy = w // 2, h // 2
        road_width = 100

        # Clear
        self.canvas.delete("all")

        # Roads (Gray)
        self.canvas.create_rectangle(cx - road_width/2, 0, cx + road_width/2, h, fill="#444", outline="")
        self.canvas.create_rectangle(0, cy - road_width/2, w, cy + road_width/2, fill="#444", outline="")
        
        # Dashed lines
        self.canvas.create_line(cx, 0, cx, h, fill="white", dash=(20, 20))
        self.canvas.create_line(0, cy, w, cy, fill="white", dash=(20, 20))

        # Store coords for lights
        self.light_coords = {
            Direction.NORTH: (cx - road_width/2 - 20, cy - road_width/2 - 20), # Top-Left of center? No, lights face incoming.
            # North Light controls traffic coming from North (going South). Should be on the Right side of the road or overhead?
            # Standard: Top-Right corner of intersection for North-bound? No, for South-bound traffic coming from North.
            # Let's place them visually at the stop lines.
            
            # Vehicles from North (going South) stop at (cx - width/2, cy - width/2).
            # Light for them is at (cx - width/2 - 20, cy - width/2).
             Direction.NORTH: (cx + road_width/2 + 20, cy - road_width/2 - 20), # Actually let's just put them in corners
             Direction.SOUTH: (cx - road_width/2 - 20, cy + road_width/2 + 20),
             Direction.EAST: (cx + road_width/2 + 20, cy + road_width/2 + 20),
             Direction.WEST: (cx - road_width/2 - 20, cy - road_width/2 - 20)
        }
        
        # Draw placeholders
        for d, (lx, ly) in self.light_coords.items():
            self.draw_light(lx, ly, "gray", d.value)

    def draw_light(self, x, y, color, label):
        color_map = {"Red": "red", "Yellow": "yellow", "Green": "#00FF00", "gray": "gray"}
        c = color_map.get(color, "gray")
        radius = 15
        self.canvas.create_oval(x-radius, y-radius, x+radius, y+radius, fill=c, outline="black")
        self.canvas.create_text(x, y-25, text=label, fill="black")

    def draw_vehicles(self, state):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        cx, cy = w // 2, h // 2
        road_width = 100
        lane_offset = road_width / 4

        # Map directions to start points and vector
        # North: From Top to Center. (x = cx - lane_offset, y increases)
        # South: From Bottom to Center. (x = cx + lane_offset, y decreases)
        # East: From Right to Center. (y = cy - lane_offset, x decreases)
        # West: From Left to Center. (y = cy + lane_offset, x increases)
        
        for d_name, info in state.items():
            vehicles = info['vehicles']
            count = len(vehicles)
            
            # Simple visualization: Dots stacked behind the stop line
            # Max 10 dots to avoid clutter
            
            for i in range(min(count, 10)):
                gap = 30
                
                if d_name == Direction.NORTH.value:
                    x = cx - lane_offset
                    y = (cy - road_width/2) - (i * gap) - 20
                elif d_name == Direction.SOUTH.value:
                    x = cx + lane_offset
                    y = (cy + road_width/2) + (i * gap) + 20
                elif d_name == Direction.EAST.value:
                    x = (cx + road_width/2) + (i * gap) + 20
                    y = cy - lane_offset
                elif d_name == Direction.WEST.value:
                    x = (cx - road_width/2) - (i * gap) - 20
                    y = cy + lane_offset
                
                # Draw vehicle
                self.canvas.create_rectangle(x-10, y-10, x+10, y+10, fill="blue", outline="white")

    def start_simulation(self):
        if self.running: return
        
        mode = self.mode.get()
        self.stats = TrafficStats()
        
        if mode == "Thread":
            self.controller = ThreadedController(self.stats)
        else:
            self.controller = ProcessController() # Stats are handled via queue in process mode
        
        self.controller.start()
        self.running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        
        self.root.after(100, self.update_loop)

    def stop_simulation(self):
        if not self.running: return
        
        self.controller.stop()
        self.running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)

    def add_vehicle(self, direction):
        if self.running and self.controller:
            self.controller.add_vehicle(direction)

    def update_loop(self):
        if not self.running: return
        
        # Get State
        try:
            state = self.controller.get_state() # Returns Dict
            
            # Update Canvas
            self.draw_intersection() # Refreshes background
            
            # Draw Lights
            # We need to map direction strings back to Enum if needed or just use strings
            # state keys are strings 'North', etc.
            
            # Map for coords
            d_map = {
                Direction.NORTH.value: Direction.NORTH,
                Direction.SOUTH.value: Direction.SOUTH,
                Direction.EAST.value: Direction.EAST,
                Direction.WEST.value: Direction.WEST
            }
            
            for d_str, info in state.items():
                d_enum = d_map.get(d_str)
                if d_enum:
                    lx, ly = self.light_coords[d_enum]
                    self.draw_light(lx, ly, info['color'], d_str)
            
            # Draw Vehicles
            self.draw_vehicles(state)
            
            # Update Stats (approximate or real)
            # In threading mode, self.stats is updated.
            # In process mode, we need to read from stats_queue if we want accurate wait times
            if isinstance(self.controller, ProcessController):
                # Drain queue
                while not self.controller.stats_queue.empty():
                    # Just count them, we don't have a local stats object for display logic implemented yet
                    val = self.controller.stats_queue.get()
                    # We can keep a local counter
                    if not hasattr(self, 'local_stats_count'):
                        self.local_stats_count = 0
                        self.local_stats_wait = 0.0
                    self.local_stats_count += 1
                    self.local_stats_wait += val
                
                if hasattr(self, 'local_stats_count') and self.local_stats_count > 0:
                     avg = self.local_stats_wait / self.local_stats_count
                     self.lbl_stats.config(text=f"Vehículos: {self.local_stats_count}\nEspera Prom: {avg:.2f}s")
            else:
                s = self.controller.stats
                self.lbl_stats.config(text=f"Vehículos: {s.total_vehicles}\nEspera Prom: {s.average_wait_time:.2f}s")

        except Exception as e:
            print(f"Error updating GUI: {e}")
        
        self.root.after(100, self.update_loop)

