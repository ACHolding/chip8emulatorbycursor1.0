#!/usr/bin/env python3
from __future__ import annotations

USER_GUIDE = """
chip8emulator by cursor 0.1.1a
================================================================================

A clean, visually polished CHIP-8 emulator with an mGBA-inspired dark GUI
built in Python and Tkinter.

Features
--------------------------------------------------------------------------------
  • Accurate CHIP-8 CPU core
  • Dark mGBA-style interface (menu bar, toolbar, framed display, status bar)
  • Built-in sprite bounce demo
  • Load .ch8, .rom, .c8 files
  • Adjustable speed (1–40 instructions per frame)
  • Improved sound: retro square-wave beep (pygame when installed), else system bell
  • Real-time FPS counter (measured frame timing)
  • Proper key waiting (opcode FX0A)
  • In-app User Guide (Help menu)

Sound (0.1.1a)
--------------------------------------------------------------------------------
  • Classic square-wave tone at 440 Hz when pygame is available
  • pygame mixer plays a seamless looping buffer while the sound timer is active
  • If pygame is not installed, a periodic system bell approximates the buzz
  • Audio/Video → Beep test previews the active backend

Keyboard controls
--------------------------------------------------------------------------------
  CHIP-8 keypad          Emulator keys
  ----------------       -------------
  1  2  3  C             1  2  3  4
  4  5  6  D             Q  W  E  R
  7  8  9  E             A  S  D  F
  A  0  B  F             Z  X  C  V

  Hotkeys:
    Esc       Run / Pause
    Ctrl+O    Load ROM
    Ctrl+R    Reset
    Ctrl+Q    Quit

How to run
--------------------------------------------------------------------------------
  Prerequisites: Python 3.8+   |   Optional: pygame (pip install pygame)

    python3 chip8emu0.1.1a.py

  Full path example:

    python3 "/Volumes/1TB/:STUFF~ /:Coding~/chip8emu0.1.1a.py"
""".strip()

__doc__ = USER_GUIDE

import array
import random
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path

TITLE = "chip8emulator by cursor 0.1.1a"
DISPLAY_WIDTH = 64
DISPLAY_HEIGHT = 32
SCALE = 10
PROGRAM_START = 0x200
FONT_START = 0x050
MEMORY_SIZE = 4096
FRAME_MS = 1000 // 60

# Seamless loop: 2205 samples @ 44100 Hz == exactly 22 cycles of 440 Hz
_SAMPLE_RATE = 44100
_BEEP_HZ = 440
_SQUARE_PCM_SAMPLES = 2205

BG = "#000000"
BUTTON_BG = "#000000"
PANEL = "#050508"
FRAME = "#0c1018"
BLUE = "#4da6ff"
BLUE_DIM = "#0d2844"
BLUE_EDGE = "#2563a8"
BLUE_GLOW = "#2a6ecc"

FONTSET = [
    0xF0, 0x90, 0x90, 0x90, 0xF0,
    0x20, 0x60, 0x20, 0x20, 0x70,
    0xF0, 0x10, 0xF0, 0x80, 0xF0,
    0xF0, 0x10, 0xF0, 0x10, 0xF0,
    0x90, 0x90, 0xF0, 0x10, 0x10,
    0xF0, 0x80, 0xF0, 0x10, 0xF0,
    0xF0, 0x80, 0xF0, 0x90, 0xF0,
    0xF0, 0x10, 0x20, 0x40, 0x40,
    0xF0, 0x90, 0xF0, 0x90, 0xF0,
    0xF0, 0x90, 0xF0, 0x10, 0xF0,
    0xF0, 0x90, 0xF0, 0x90, 0x90,
    0xE0, 0x90, 0xE0, 0x90, 0xE0,
    0xF0, 0x80, 0x80, 0x80, 0xF0,
    0xE0, 0x90, 0x90, 0x90, 0xE0,
    0xF0, 0x80, 0xF0, 0x80, 0xF0,
    0xF0, 0x80, 0xF0, 0x80, 0x80,
]

KEYMAP = {
    "1": 0x1, "2": 0x2, "3": 0x3, "4": 0xC,
    "q": 0x4, "w": 0x5, "e": 0x6, "r": 0xD,
    "a": 0x7, "s": 0x8, "d": 0x9, "f": 0xE,
    "z": 0xA, "x": 0x0, "c": 0xB, "v": 0xF,
}


def _square_wave_pcm_mono16(
    *,
    sample_rate: int = _SAMPLE_RATE,
    frequency_hz: float = _BEEP_HZ,
    num_samples: int = _SQUARE_PCM_SAMPLES,
    amplitude: int = 24000,
) -> bytes:
    buf = array.array("h")
    for i in range(num_samples):
        phase = (i * frequency_hz / sample_rate) % 1.0
        buf.append(amplitude if phase < 0.5 else -amplitude)
    return buf.tobytes()


class Chip8Audio:
    """Square-wave buzz while sound_timer > 0; pygame loop if available else Tk bell pulses."""

    def __init__(self, bell_fn) -> None:
        self._bell = bell_fn
        self._pygame = None
        self._tone: object | None = None
        self._playing = False
        self.backend_name = "system bell (install pygame for square wave)"

        try:
            import pygame  # type: ignore[import-untyped]

            pygame.mixer.init(_SAMPLE_RATE, size=-16, channels=1, buffer=512)
            pcm = _square_wave_pcm_mono16()
            self._tone = pygame.mixer.Sound(buffer=pcm)
            self._pygame = pygame
            self.backend_name = f"pygame square wave ({_BEEP_HZ} Hz loop)"
        except Exception:
            self._pygame = None
            self._tone = None

        self._fallback_pulse = 0

    def sync(self, sound_active: bool) -> None:
        if self._tone is not None and self._pygame is not None:
            if sound_active:
                if not self._playing:
                    self._tone.play(loops=-1)
                    self._playing = True
            elif self._playing:
                self._tone.stop()
                self._playing = False
            return

        if sound_active:
            self._fallback_pulse = (self._fallback_pulse + 1) % 3
            if self._fallback_pulse == 0:
                self._bell()
        else:
            self._fallback_pulse = 0

    def test(self) -> None:
        if self._tone is not None:
            self._tone.play(loops=2)
        else:
            for _ in range(3):
                self._bell()

    def shutdown(self) -> None:
        if self._tone is not None:
            try:
                self._tone.stop()
            except Exception:
                pass
        if self._pygame is not None:
            try:
                self._pygame.mixer.quit()
            except Exception:
                pass


def build_demo_rom() -> bytes:
    code = bytes([
        0x00, 0xE0,
        0x60, 0x0C,
        0x61, 0x08,
        0xA3, 0x00,
        0xD0, 0x15,
        0x70, 0x08,
        0xA3, 0x05,
        0xD0, 0x15,
        0x12, 0x10,
    ])
    sprites = bytes([
        0xF0, 0x90, 0xF0, 0x90, 0x90,
        0xF0, 0x80, 0x80, 0x80, 0xF0,
    ])
    sprite_address = 0x300
    padding_len = sprite_address - PROGRAM_START - len(code)
    return code + bytes(padding_len) + sprites


DEMO_ROM = build_demo_rom()


class Chip8:
    def __init__(self) -> None:
        self.rng = random.Random()
        self.last_rom: bytes | None = None
        self.reset()

    def reset(self) -> None:
        self.memory = bytearray(MEMORY_SIZE)
        self.memory[FONT_START:FONT_START + len(FONTSET)] = bytes(FONTSET)
        self.v = bytearray(16)
        self.i = 0
        self.pc = PROGRAM_START
        self.stack: list[int] = []
        self.delay_timer = 0
        self.sound_timer = 0
        self.keys = [False] * 16
        self.display = [0] * (DISPLAY_WIDTH * DISPLAY_HEIGHT)
        self.draw_flag = True
        self.waiting_for_key_reg: int | None = None
        self.halted = False
        self.status = "Ready - load a .ch8 ROM"

    def load_rom(self, rom: bytes) -> None:
        if not rom:
            raise ValueError("ROM is empty.")
        if len(rom) > MEMORY_SIZE - PROGRAM_START:
            raise ValueError("ROM is too large for CHIP-8 memory.")
        self.reset()
        self.memory[PROGRAM_START:PROGRAM_START + len(rom)] = rom
        self.last_rom = rom
        self.status = f"ROM loaded ({len(rom)} bytes)"

    def reload_last_rom(self) -> bool:
        if self.last_rom is None:
            self.reset()
            return False
        self.load_rom(self.last_rom)
        return True

    def set_key(self, key: int, pressed: bool) -> None:
        self.keys[key] = pressed
        if pressed and self.waiting_for_key_reg is not None:
            self.v[self.waiting_for_key_reg] = key
            self.waiting_for_key_reg = None
            self.status = "Running"

    def tick_timers(self) -> None:
        if self.delay_timer > 0:
            self.delay_timer -= 1
        if self.sound_timer > 0:
            self.sound_timer -= 1

    def step(self) -> None:
        if self.halted or self.waiting_for_key_reg is not None:
            return
        if self.pc >= MEMORY_SIZE - 1:
            self.halted = True
            self.status = f"Halted - PC out of memory at 0x{self.pc:03X}"
            return

        opcode = (self.memory[self.pc] << 8) | self.memory[self.pc + 1]
        self.pc = (self.pc + 2) & 0xFFF
        self.execute(opcode)

    def execute(self, opcode: int) -> None:
        nnn = opcode & 0x0FFF
        nn = opcode & 0x00FF
        n = opcode & 0x000F
        x = (opcode & 0x0F00) >> 8
        y = (opcode & 0x00F0) >> 4
        op = opcode & 0xF000

        if opcode == 0x00E0:
            self.display = [0] * (DISPLAY_WIDTH * DISPLAY_HEIGHT)
            self.draw_flag = True
        elif opcode == 0x00EE:
            if not self.stack:
                self.halted = True
                self.status = "Halted - return with empty stack"
                return
            self.pc = self.stack.pop()
        elif op == 0x0000:
            pass
        elif op == 0x1000:
            self.pc = nnn
        elif op == 0x2000:
            if len(self.stack) >= 16:
                self.halted = True
                self.status = "Halted - stack overflow"
                return
            self.stack.append(self.pc)
            self.pc = nnn
        elif op == 0x3000:
            if self.v[x] == nn:
                self.pc = (self.pc + 2) & 0xFFF
        elif op == 0x4000:
            if self.v[x] != nn:
                self.pc = (self.pc + 2) & 0xFFF
        elif op == 0x5000 and n == 0:
            if self.v[x] == self.v[y]:
                self.pc = (self.pc + 2) & 0xFFF
        elif op == 0x6000:
            self.v[x] = nn
        elif op == 0x7000:
            self.v[x] = (self.v[x] + nn) & 0xFF
        elif op == 0x8000:
            self._execute_8xy(opcode, x, y, n)
        elif op == 0x9000 and n == 0:
            if self.v[x] != self.v[y]:
                self.pc = (self.pc + 2) & 0xFFF
        elif op == 0xA000:
            self.i = nnn
        elif op == 0xB000:
            self.pc = (nnn + self.v[0]) & 0xFFF
        elif op == 0xC000:
            self.v[x] = self.rng.randint(0, 255) & nn
        elif op == 0xD000:
            self._draw_sprite(self.v[x], self.v[y], n)
        elif op == 0xE000:
            key = self.v[x] & 0xF
            if nn == 0x9E:
                if self.keys[key]:
                    self.pc = (self.pc + 2) & 0xFFF
            elif nn == 0xA1:
                if not self.keys[key]:
                    self.pc = (self.pc + 2) & 0xFFF
            else:
                self._unknown(opcode)
        elif op == 0xF000:
            self._execute_fx(opcode, x, nn)
        else:
            self._unknown(opcode)

    def _execute_8xy(self, opcode: int, x: int, y: int, n: int) -> None:
        if n == 0x0:
            self.v[x] = self.v[y]
        elif n == 0x1:
            self.v[x] |= self.v[y]
        elif n == 0x2:
            self.v[x] &= self.v[y]
        elif n == 0x3:
            self.v[x] ^= self.v[y]
        elif n == 0x4:
            total = self.v[x] + self.v[y]
            self.v[0xF] = 1 if total > 0xFF else 0
            self.v[x] = total & 0xFF
        elif n == 0x5:
            self.v[0xF] = 1 if self.v[x] >= self.v[y] else 0
            self.v[x] = (self.v[x] - self.v[y]) & 0xFF
        elif n == 0x6:
            self.v[0xF] = self.v[x] & 0x1
            self.v[x] = (self.v[x] >> 1) & 0xFF
        elif n == 0x7:
            self.v[0xF] = 1 if self.v[y] >= self.v[x] else 0
            self.v[x] = (self.v[y] - self.v[x]) & 0xFF
        elif n == 0xE:
            self.v[0xF] = (self.v[x] >> 7) & 0x1
            self.v[x] = (self.v[x] << 1) & 0xFF
        else:
            self._unknown(opcode)

    def _execute_fx(self, opcode: int, x: int, nn: int) -> None:
        if nn == 0x07:
            self.v[x] = self.delay_timer
        elif nn == 0x0A:
            self.waiting_for_key_reg = x
            self.status = "Waiting for key"
        elif nn == 0x15:
            self.delay_timer = self.v[x]
        elif nn == 0x18:
            self.sound_timer = self.v[x]
        elif nn == 0x1E:
            self.i = (self.i + self.v[x]) & 0xFFF
        elif nn == 0x29:
            self.i = FONT_START + ((self.v[x] & 0xF) * 5)
        elif nn == 0x33:
            value = self.v[x]
            self.memory[self.i] = value // 100
            self.memory[self.i + 1] = (value // 10) % 10
            self.memory[self.i + 2] = value % 10
        elif nn == 0x55:
            for idx in range(x + 1):
                self.memory[self.i + idx] = self.v[idx]
        elif nn == 0x65:
            for idx in range(x + 1):
                self.v[idx] = self.memory[self.i + idx]
        else:
            self._unknown(opcode)

    def _draw_sprite(self, vx: int, vy: int, height: int) -> None:
        self.v[0xF] = 0
        for row in range(height):
            sprite_byte = self.memory[(self.i + row) & 0xFFF]
            for col in range(8):
                if sprite_byte & (0x80 >> col):
                    x_coord = (vx + col) % DISPLAY_WIDTH
                    y_coord = (vy + row) % DISPLAY_HEIGHT
                    index = y_coord * DISPLAY_WIDTH + x_coord
                    if self.display[index] == 1:
                        self.v[0xF] = 1
                    self.display[index] ^= 1
        self.draw_flag = True

    def _unknown(self, opcode: int) -> None:
        self.halted = True
        self.status = f"Halted - unknown opcode 0x{opcode:04X}"


class Chip8App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(TITLE)
        self.root.configure(bg=PANEL)
        self.root.resizable(False, False)

        self.chip8 = Chip8()
        self.running = False
        self.cycles_per_frame = 10
        self.last_drawn = [-1] * (DISPLAY_WIDTH * DISPLAY_HEIGHT)
        self.audio = Chip8Audio(bell_fn=lambda: self.root.bell())

        self._fps_last_t = time.perf_counter()
        self._fps_ema = 60.0

        self.status_var = tk.StringVar(value=self.chip8.status)
        self.fps_var = tk.StringVar(value="0 fps")
        self.speed_var = tk.StringVar(value=f"{self.cycles_per_frame} ipf")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_menu()
        self._build_ui()
        self._bind_keys()
        self.root.after(FRAME_MS, self._tick)

    def _on_close(self) -> None:
        self.audio.shutdown()
        self.root.destroy()

    def _build_menu(self) -> None:
        menubar = tk.Menu(
            self.root,
            bg=PANEL,
            fg=BLUE,
            activebackground=BLUE_DIM,
            activeforeground=BLUE_GLOW,
            borderwidth=0,
        )

        file_menu = self._submenu()
        file_menu.add_command(label="Load ROM...", accelerator="Ctrl+O", command=self.load_rom)
        file_menu.add_command(label="Load Demo", command=self.load_demo)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", accelerator="Ctrl+Q", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        emu_menu = self._submenu()
        emu_menu.add_command(label="Run / Pause", accelerator="Esc", command=self.toggle_running)
        emu_menu.add_command(label="Reset", accelerator="Ctrl+R", command=self.reset)
        emu_menu.add_separator()
        emu_menu.add_command(label="Speed -", command=self.slower)
        emu_menu.add_command(label="Speed +", command=self.faster)
        menubar.add_cascade(label="Emulation", menu=emu_menu)

        av_menu = self._submenu()
        av_menu.add_command(label="Beep test", command=self.audio.test)
        av_menu.add_separator()
        av_menu.add_command(
            label="Audio backend info",
            command=lambda: messagebox.showinfo(TITLE, self.audio.backend_name),
        )
        menubar.add_cascade(label="Audio/Video", menu=av_menu)

        tools_menu = self._submenu()
        tools_menu.add_command(label="Keypad map", command=self._show_keypad)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = self._submenu()
        help_menu.add_command(label="User Guide", command=self._show_user_guide)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.configure(menu=menubar)

        self.root.bind_all("<Control-o>", lambda _e: self.load_rom())
        self.root.bind_all("<Control-O>", lambda _e: self.load_rom())
        self.root.bind_all("<Control-q>", lambda _e: self._on_close())
        self.root.bind_all("<Control-r>", lambda _e: self.reset())

    def _submenu(self) -> tk.Menu:
        return tk.Menu(
            self.root,
            tearoff=0,
            bg=PANEL,
            fg=BLUE,
            activebackground=BLUE_DIM,
            activeforeground=BLUE_GLOW,
            borderwidth=0,
        )

    def _build_ui(self) -> None:
        toolbar = tk.Frame(self.root, bg=PANEL, height=34)
        toolbar.pack(fill="x", side="top")

        self.load_button = self._button(toolbar, "Open", self.load_rom)
        self.demo_button = self._button(toolbar, "Demo", self.load_demo)
        self.pause_button = self._button(toolbar, "Run/Pause", self.toggle_running)
        self.reset_button = self._button(toolbar, "Reset", self.reset)
        self.slower_button = self._button(toolbar, "-", self.slower)
        self.faster_button = self._button(toolbar, "+", self.faster)

        for button in (
            self.load_button,
            self.demo_button,
            self.pause_button,
            self.reset_button,
            self.slower_button,
            self.faster_button,
        ):
            button.pack(side="left", padx=3, pady=3)

        speed_label = tk.Label(
            toolbar,
            textvariable=self.speed_var,
            bg=PANEL,
            fg=BLUE,
            font=("Courier New", 10, "bold"),
            padx=8,
        )
        speed_label.pack(side="right")

        viewport = tk.Frame(self.root, bg=FRAME, padx=6, pady=6)
        viewport.pack(padx=8, pady=(6, 0))

        self.canvas = tk.Canvas(
            viewport,
            width=DISPLAY_WIDTH * SCALE,
            height=DISPLAY_HEIGHT * SCALE,
            bg=BG,
            highlightthickness=1,
            highlightbackground=BLUE_EDGE,
            bd=0,
        )
        self.canvas.pack()

        self.pixel_items: list[int] = []
        for y in range(DISPLAY_HEIGHT):
            for x in range(DISPLAY_WIDTH):
                item = self.canvas.create_rectangle(
                    x * SCALE,
                    y * SCALE,
                    (x + 1) * SCALE,
                    (y + 1) * SCALE,
                    fill=BG,
                    outline="",
                )
                self.pixel_items.append(item)

        statusbar = tk.Frame(self.root, bg=PANEL)
        statusbar.pack(fill="x", side="bottom", pady=(6, 0))

        status = tk.Label(
            statusbar,
            textvariable=self.status_var,
            bg=PANEL,
            fg=BLUE,
            font=("Courier New", 10),
            anchor="w",
            padx=8,
            pady=4,
        )
        status.pack(side="left", fill="x", expand=True)

        fps = tk.Label(
            statusbar,
            textvariable=self.fps_var,
            bg=PANEL,
            fg=BLUE,
            font=("Courier New", 10),
            padx=8,
            pady=4,
        )
        fps.pack(side="right")

    def _button(self, parent: tk.Widget, text: str, command) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=BUTTON_BG,
            fg=BLUE,
            activebackground=BLUE_DIM,
            activeforeground=BLUE_GLOW,
            disabledforeground=BLUE_EDGE,
            highlightbackground=BLUE_EDGE,
            highlightcolor=BLUE_GLOW,
            highlightthickness=1,
            relief="flat",
            borderwidth=0,
            font=("Courier New", 10, "bold"),
            padx=10,
            pady=3,
            cursor="hand2",
        )

    def _bind_keys(self) -> None:
        self.root.bind("<KeyPress>", self._on_key_press)
        self.root.bind("<KeyRelease>", self._on_key_release)
        self.root.focus_set()

    def _on_key_press(self, event: tk.Event) -> None:
        key_name = str(event.keysym).lower()
        if key_name == "escape":
            self.toggle_running()
            return
        if key_name in KEYMAP:
            self.chip8.set_key(KEYMAP[key_name], True)

    def _on_key_release(self, event: tk.Event) -> None:
        key_name = str(event.keysym).lower()
        if key_name in KEYMAP:
            self.chip8.set_key(KEYMAP[key_name], False)

    def load_demo(self) -> None:
        self.chip8.load_rom(DEMO_ROM)
        self.running = True
        self.status_var.set("Loaded built-in demo")
        self.root.focus_set()

    def load_rom(self) -> None:
        path = filedialog.askopenfilename(
            title="Load CHIP-8 ROM",
            filetypes=(
                ("CHIP-8 ROMs", "*.ch8 *.rom *.c8"),
                ("All files", "*.*"),
            ),
        )
        if not path:
            self.root.focus_set()
            return

        try:
            rom = Path(path).read_bytes()
            self.chip8.load_rom(rom)
        except Exception as exc:
            messagebox.showerror(TITLE, f"Could not load ROM:\n{exc}")
            self.root.focus_set()
            return

        self.running = True
        self.status_var.set(f"Loaded {Path(path).name} ({len(rom)} bytes)")
        self.root.focus_set()

    def toggle_running(self) -> None:
        if self.chip8.last_rom is None:
            self.status_var.set("Load a ROM first")
            self.root.focus_set()
            return
        self.running = not self.running
        self.status_var.set("Running" if self.running else "Paused")
        self.root.focus_set()

    def reset(self) -> None:
        had_rom = self.chip8.reload_last_rom()
        self.running = had_rom
        self.status_var.set("Reset and running" if had_rom else "Reset - load a ROM")
        self.last_drawn = [-1] * (DISPLAY_WIDTH * DISPLAY_HEIGHT)
        self._draw()
        self.root.focus_set()

    def slower(self) -> None:
        self.cycles_per_frame = max(1, self.cycles_per_frame - 1)
        self.speed_var.set(f"{self.cycles_per_frame} ipf")
        self.root.focus_set()

    def faster(self) -> None:
        self.cycles_per_frame = min(40, self.cycles_per_frame + 1)
        self.speed_var.set(f"{self.cycles_per_frame} ipf")
        self.root.focus_set()

    def _show_keypad(self) -> None:
        messagebox.showinfo(
            TITLE,
            "CHIP-8 keypad mapping:\n\n"
            "  1 2 3 C    ->    1 2 3 4\n"
            "  4 5 6 D    ->    Q W E R\n"
            "  7 8 9 E    ->    A S D F\n"
            "  A 0 B F    ->    Z X C V\n\n"
            "Esc = pause/resume",
        )

    def _show_user_guide(self) -> None:
        win = tk.Toplevel(self.root)
        win.title(f"{TITLE} — User Guide")
        win.configure(bg=PANEL)
        win.minsize(520, 420)
        txt = scrolledtext.ScrolledText(
            win,
            width=86,
            height=26,
            wrap="word",
            bg=BG,
            fg=BLUE,
            insertbackground=BLUE,
            font=("Courier New", 11),
            relief="flat",
            highlightthickness=1,
            highlightbackground=BLUE_EDGE,
            padx=10,
            pady=10,
        )
        txt.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        txt.insert("1.0", USER_GUIDE)
        txt.configure(state="disabled")

        bar = tk.Frame(win, bg=PANEL)
        bar.pack(fill="x", pady=(6, 10))
        self._button(bar, "Close", win.destroy).pack(side="right", padx=10)

    def _show_about(self) -> None:
        messagebox.showinfo(
            TITLE,
            f"{TITLE}\n\n"
            f"{self.audio.backend_name}\n\n"
            "CHIP-8 emulator — mGBA-style layout.\n"
            "Help → User Guide for full documentation.",
        )

    def _tick(self) -> None:
        if self.running and not self.chip8.halted:
            for _ in range(self.cycles_per_frame):
                self.chip8.step()
                if self.chip8.halted:
                    self.running = False
                    break
            self.chip8.tick_timers()

        sound_active = (
            self.chip8.sound_timer > 0 and self.running and not self.chip8.halted
        )
        self.audio.sync(sound_active)

        if self.chip8.draw_flag:
            self._draw()
            self.chip8.draw_flag = False

        if self.chip8.halted:
            self.status_var.set(self.chip8.status)
        elif self.chip8.waiting_for_key_reg is not None:
            self.status_var.set(self.chip8.status)

        now = time.perf_counter()
        dt = now - self._fps_last_t
        self._fps_last_t = now
        if dt > 1e-9:
            inst = 1.0 / dt
            self._fps_ema = self._fps_ema * 0.92 + inst * 0.08

        if self.running:
            self.fps_var.set(f"{self._fps_ema:.0f} fps")
        else:
            self.fps_var.set("-- fps")

        self.root.after(FRAME_MS, self._tick)

    def _draw(self) -> None:
        for index, value in enumerate(self.chip8.display):
            if value != self.last_drawn[index]:
                self.canvas.itemconfigure(self.pixel_items[index], fill=BLUE if value else BG)
                self.last_drawn[index] = value

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = Chip8App()
    app.run()


if __name__ == "__main__":
    main()
