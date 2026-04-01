import tkinter as tk
import json
import os
import time
import random

WINDOW_SIZE = 150
STATE_FILE = "face_state.json"

# BMO colors
BODY = "#5BCEFA"
SCREEN = "#1a1a2e"
WHITE = "#FFFFFF"
BLACK = "#000000"
PINK = "#FF9999"


class BMOFace:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BMO")
        self.root.overrideredirect(True)    # borderless
        self.root.wm_attributes('-topmost', True)  # always on top

        # Position top right corner
        sw = self.root.winfo_screenwidth()
        self.root.geometry(
            f"{WINDOW_SIZE}x{WINDOW_SIZE}+{sw - WINDOW_SIZE - 10}+10")

        self.canvas = tk.Canvas(
            self.root,
            width=WINDOW_SIZE,
            height=WINDOW_SIZE,
            bg=BODY,
            highlightthickness=0
        )
        self.canvas.pack()

        # Make window draggable
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.do_drag)

        self.mood = "neutral"
        self.typing = False
        self.reacting = False
        self.react_timer = 0
        self.blinking = False
        self.blink_timer = time.time()
        self.dot_frame = 0

        self.update_loop()

    def start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def do_drag(self, event):
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f"+{x}+{y}")

    def read_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    self.mood = data.get('mood', 'neutral')
                    self.typing = data.get('typing', False)
                    reacting = data.get('reacting', False)
                    if reacting and not self.reacting:
                        self.reacting = True
                        self.react_timer = time.time()
            except:
                pass

    def draw(self):
        c = self.canvas
        c.delete("all")
        cx = WINDOW_SIZE // 2

        # Body
        c.create_rectangle(0, 0, WINDOW_SIZE, WINDOW_SIZE,
                           fill=BODY, outline="")

        # Screen
        m = 18
        c.create_rectangle(m, m, WINDOW_SIZE - m, WINDOW_SIZE - m,
                           fill=SCREEN, outline="#2a2a4a", width=2)

        # Cheeks (happy only)
        if self.mood == "happy" or self.reacting:
            c.create_oval(28, 82, 44, 94, fill=PINK, outline="")
            c.create_oval(106, 82, 122, 94, fill=PINK, outline="")

        # Eyes
        self.draw_eyes()

        # Mouth
        self.draw_mouth()

    def draw_eyes(self):
        c = self.canvas
        lx, rx, ey = 48, 90, 55

        if self.reacting:
            # Big wide eyes
            c.create_rectangle(lx - 4, ey - 4, lx + 16,
                               ey + 16, fill=WHITE, outline="")
            c.create_rectangle(lx + 2, ey + 2, lx + 10,
                               ey + 10, fill=BLACK, outline="")
            c.create_rectangle(rx - 4, ey - 4, rx + 16,
                               ey + 16, fill=WHITE, outline="")
            c.create_rectangle(rx + 2, ey + 2, rx + 10,
                               ey + 10, fill=BLACK, outline="")

        elif self.blinking:
            # Closed — thin lines
            c.create_rectangle(lx, ey + 5, lx + 12, ey +
                               7, fill=WHITE, outline="")
            c.create_rectangle(rx, ey + 5, rx + 12, ey +
                               7, fill=WHITE, outline="")

        elif self.mood == "sad":
            # Droopy eyes
            c.create_rectangle(lx, ey + 4, lx + 12, ey +
                               14, fill=WHITE, outline="")
            c.create_rectangle(lx + 2, ey + 6, lx + 10,
                               ey + 12, fill=BLACK, outline="")
            c.create_rectangle(rx, ey + 4, rx + 12, ey +
                               14, fill=WHITE, outline="")
            c.create_rectangle(rx + 2, ey + 6, rx + 10,
                               ey + 12, fill=BLACK, outline="")

        elif self.mood == "anxious":
            # Slanted worried eyes
            c.create_rectangle(lx, ey, lx + 12, ey + 10,
                               fill=WHITE, outline="")
            c.create_rectangle(lx + 4, ey + 2, lx + 10,
                               ey + 8, fill=BLACK, outline="")
            c.create_rectangle(rx, ey, rx + 12, ey + 10,
                               fill=WHITE, outline="")
            c.create_rectangle(rx + 2, ey + 2, rx + 8,
                               ey + 8, fill=BLACK, outline="")

        else:
            # Normal eyes
            c.create_rectangle(lx, ey, lx + 12, ey + 12,
                               fill=WHITE, outline="")
            c.create_rectangle(lx + 3, ey + 3, lx + 9,
                               ey + 9, fill=BLACK, outline="")
            c.create_rectangle(rx, ey, rx + 12, ey + 12,
                               fill=WHITE, outline="")
            c.create_rectangle(rx + 3, ey + 3, rx + 9,
                               ey + 9, fill=BLACK, outline="")

    def draw_mouth(self):
        c = self.canvas
        cx = WINDOW_SIZE // 2
        my = 95

        if self.typing:
            # Animated bouncing dots
            self.dot_frame = (self.dot_frame + 1) % 6
            for i in range(3):
                offset = -4 if (self.dot_frame // 2) == i else 0
                x = cx - 12 + i * 12
                c.create_oval(x, my + offset, x + 6, my + 6 + offset,
                              fill=WHITE, outline="")

        elif self.mood == "happy" or self.reacting:
            c.create_arc(cx - 22, my - 12, cx + 22, my + 12,
                         start=200, extent=140,
                         style=tk.ARC, outline=WHITE, width=3)

        elif self.mood == "sad":
            c.create_arc(cx - 18, my, cx + 18, my + 18,
                         start=20, extent=140,
                         style=tk.ARC, outline=WHITE, width=3)

        elif self.mood == "anxious":
            # Wavy mouth
            points = [cx-14, my+6, cx-7, my+2,
                      cx, my+6, cx+7, my+2, cx+14, my+6]
            c.create_line(points, fill=WHITE, width=2, smooth=True)

        elif self.mood == "tired":
            # Flat mouth
            c.create_line(cx - 12, my + 4, cx + 12, my + 4,
                          fill=WHITE, width=2)

        else:
            # Neutral smile
            c.create_arc(cx - 16, my - 6, cx + 16, my + 6,
                         start=210, extent=120,
                         style=tk.ARC, outline=WHITE, width=2)

    def update_loop(self):
        self.read_state()

        now = time.time()

        # Blink logic
        if not self.blinking and now - self.blink_timer > random.uniform(3, 6):
            self.blinking = True
            self.blink_timer = now
        elif self.blinking and now - self.blink_timer > 0.15:
            self.blinking = False
            self.blink_timer = now

        # React timeout — reset after 1.5 seconds
        if self.reacting and now - self.react_timer > 1.5:
            self.reacting = False
            self.clear_react()

        self.draw()
        self.root.after(100, self.update_loop)

    def clear_react(self):
        """Clear react flag in state file."""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                data['reacting'] = False
                with open(STATE_FILE, 'w') as f:
                    json.dump(data, f)
            except:
                pass

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    face = BMOFace()
    face.run()
