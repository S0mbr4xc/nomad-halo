import sys
import os

# Add project root to sys.path so we can import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.gui import TrafficGUI
import tkinter as tk
import multiprocessing

if __name__ == "__main__":
    # Required for Windows multiprocessing
    multiprocessing.freeze_support()
    
    root = tk.Tk()
    app = TrafficGUI(root)
    root.mainloop()
