#PyTerm.py
"""
This is a terminal engine which is desined to be imported by other python files to use its features.\
init(screen); return bg_buffer, {vars dict}, "optional command string"
tick(screen, vars, keys); return None

"""
import sys, time, os, random, collections, re, ctypes
import copy, math, csv
from collections import deque
from time import sleep
import select

valid_run = True
if not os.name == 'nt':
    if not 'pyodide' in sys.modules:
        try: import tty, termios
        except: 
            print("Needed packages not present")
            valid_run = input("do you wish to continue (y/n): ")
            if "y" in valid_run: valid_run = True
            else: valid_run = False

def get_keys_linux_fallback():
    """Reads characters from stdin without blocking."""
    keys = set()
    # Check if there is data waiting in the buffer
    while select.select([sys.stdin], [], [], 0)[0]:
        char = sys.stdin.read(1)
        if char == '\x1b':  # Escape sequence (Arrows/Alt)
            next_char = sys.stdin.read(1)
            if next_char == '[':
                code = sys.stdin.read(1)
                mapping = {'A': 'up', 'B': 'down', 'C': 'right', 'D': 'left'}
                if code in mapping:
                    keys.add(mapping[code])
        elif char == '\n' or char == '\r':
            keys.add('enter')
        elif char == ' ':
            keys.add(' ')
        elif char == '\x7f':
            keys.add('backspace')
        else:
            keys.add(char.lower())
    return keys

# IMPORTANT
""" 
Never every change somthing without a direct request including all parts of this code comments ect. That includes this comment.
"""
# --- Input ---
# --- Key Tracking State ---
class KeyTracker:
    def __init__(self):
        self.press_times = {}  # {key: start_time}
        self.REPEAT_DELAY = 0.5 # Seconds before auto-repeat starts

    def update(self, active_keys):
        """Generates the 'p' (pulse) and 't' (time) versions of keys."""
        now = time.time()
        final_keys = set(active_keys)
        
        # Remove keys no longer pressed
        for k in list(self.press_times.keys()):
            if k not in active_keys:
                del self.press_times[k]

        for k in active_keys:
            if k not in self.press_times:
                # First frame: Add 'p' version
                self.press_times[k] = now
                final_keys.add(f'p{k}')
                final_keys.add(f't{k}:0')
            else:
                elapsed = now - self.press_times[k]
                # Add 't' version with milliseconds
                final_keys.add(f't{k}:{int(elapsed * 1000)}')
                
                # After delay, 'p' version shows every frame
                if elapsed >= self.REPEAT_DELAY:
                    final_keys.add(f'p{k}')
        
        return final_keys

tracker = KeyTracker()

# Shared shift mapping for filtering logic
SHIFT_MAP = {
    '1':'!', '2':'@', '3':'#', '4':'$', '5':'%', '6':'^', '7':'&', '8':'*', '9':'(', '0':')',
    '-':'_', '=':'+', '[':'{', ']':'}', '\\':'|', ';':':', "'":'"', ',':'<', '.':'>', '/':'?', '`':'~'
}

tab_size = 4

def filter_shift_keys(keys):
    """If shift is held, replaces base keys with symbols (e.g., '1' becomes '!')"""
    if 'shift' in keys:
        to_remove = set()
        to_add = set()
        for base, shifted in SHIFT_MAP.items():
            if base in keys:
                to_add.add(shifted)
                to_remove.add(base)
        return (keys | to_add) - to_remove
    return keys

# --- CROSS-PLATFORM COMPATIBILITY LAYER ---
if os.name == 'nt':
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    def get_keys():
        keys = set()
        is_pressed = lambda vk: user32.GetAsyncKeyState(vk) & 0x8000

        # Modifiers
        if is_pressed(0x10): keys.add('shift')
        if is_pressed(0x11): keys.add('ctrl')
        if is_pressed(0x12): keys.add('alt')
        if is_pressed(0x09): keys.add('tab')
        if is_pressed(0x1B): keys.add('escape')

        # Navigation
        nav = {0x26:'up', 0x28:'down', 0x25:'left', 0x27:'right', 0x2D:'insert', 0x2E:'delete'}
        for vk, name in nav.items():
            if is_pressed(vk): keys.add(name)

        # Alpha-Numeric & Symbols
        for i in range(0x30, 0x3A): 
            if is_pressed(i): keys.add(chr(i).lower())
        for i in range(0x41, 0x5B): 
            if is_pressed(i): keys.add(chr(i).lower())

        symbols = {0xBA:';', 0xBB:'=', 0xBC:',', 0xBD:'-', 0xBE:'.', 0xBF:'/', 0xC0:'`', 0xDB:'[', 0xDC:'\\', 0xDD:']', 0xDE:"'", 0x20:' ', 0x0D:'enter', 0x08:'backspace'}
        for vk, name in symbols.items():
            if is_pressed(vk): keys.add(name)

        keys = filter_shift_keys(keys)
        return tracker.update(keys)

elif 'pyodide' in sys.modules:
    def get_keys(): return set()

else: # Linux
    try:
        from evdev import InputDevice, ecodes, list_devices
        devices = [InputDevice(path) for path in list_devices()]
        kbd = next((d for d in devices if "key" in d.name.lower()), None)

        def get_keys():
            if not kbd: return set()
            keys = set()
            active = kbd.active_keys()
            mapping = {ecodes.KEY_UP:'up', ecodes.KEY_DOWN:'down', ecodes.KEY_LEFT:'left', ecodes.KEY_RIGHT:'right', ecodes.KEY_ENTER:'enter', ecodes.KEY_LEFTSHIFT:'shift', ecodes.KEY_RIGHTSHIFT:'shift', ecodes.KEY_SPACE:' '}
            
            for code in active:
                if code in mapping: keys.add(mapping[code])
                key_name = ecodes.KEY[code].replace('KEY_', '').lower()
                if len(key_name) == 1: keys.add(key_name)
            
            keys = filter_shift_keys(keys)
            return tracker.update(keys)

    except (ImportError, PermissionError):
        def get_keys():
            keys = get_keys_linux_fallback()
            keys = filter_shift_keys(keys)
            return tracker.update(keys)

def pressed(keys, k):
    if f"p{k}" in keys: return True
    else: return False

def get_typed_chars(keys):
    """
    Returns a string of all characters that 'pulsed' this frame.
    Handles 'pspace' as ' ' and ignores modifier pulses like 'pshift'.
    """
    typed_string = ""
    for k in keys:
        if k.startswith('p') and len(k) > 1:
            char = k[1:]
            if char == 'space': typed_string += ' '
            elif char == 'tab': typed_string += ' ' * tab_size
            elif len(char) == 1: typed_string += char
    return typed_string
# --- UI Logic ---

def handle_input(v, keys, multiline=True, cursor_pos_name="cpos", use_text_from_vars=True, text="", text_name="text"):
    if use_text_from_vars:lines = v[text_name].split('\n') if v[text_name] else [""]
    else: lines = text.split('\n') if text else [""]
    cx, _ = v[cursor_pos_name]
    if multiline: _, ly = v[cursor_pos_name]
    else: ly = 0

    # --- Navigation ---
    if multiline:
        if pressed(keys, 'up') and ly > 0:
            ly -= 1
            cx = min(cx, len(lines[ly]))

        if pressed(keys, 'down') and ly < len(lines) - 1:
            ly += 1
            if cx > len(lines[ly]): cx = min(cx, len(lines[ly]))

    if pressed(keys, 'left'):
        if cx > 0: cx -= 1
        elif ly > 0: 
            ly -= 1
            cx = len(lines[ly])

    if pressed(keys, 'right'):
        if cx < len(lines[ly]): cx += 1
        elif ly < len(lines) - 1:
            ly += 1
            cx = 0

    # --- Editing ---
    if pressed(keys, 'backspace'):
        if cx > 0:
            lines[ly] = lines[ly][:cx-1] + lines[ly][cx:]
            cx -= 1
        elif ly > 0:
            target_line = ly - 1
            new_cx = len(lines[target_line])
            lines[target_line] += lines[ly]
            lines.pop(ly)
            ly = target_line
            cx = new_cx
            
    if pressed(keys, 'delete'):
        if cx < len(lines[ly]):
            # Remove character at current cursor position
            lines[ly] = lines[ly][:cx] + lines[ly][cx+1:]
        elif ly < len(lines) - 1:
            # At end of line: pull the line below up to this line
            lines[ly] += lines[ly+1]
            lines.pop(ly + 1)

    if pressed(keys, 'enter') and multiline:
        left_part = lines[ly][:cx]
        right_part = lines[ly][cx:]
        lines[ly] = left_part
        lines.insert(ly + 1, right_part)
        ly += 1
        cx = 0

    # --- Typing ---
    typed = get_typed_chars(keys)
    lines[ly] = lines[ly][:cx] + typed + lines[ly][cx:]
    cx += len(typed)

    # Update State
    if multiline: v[cursor_pos_name] = cx, ly
    else: v[cursor_pos_name] = cx, 0
    if use_text_from_vars: v[text_name] = "\n".join(lines)
    else: return "\n".join(lines)

def draw_window(arr, x, y, sx, sy, color_offset=0, char=None):
    if isinstance(char, int):
        for xi in range(x, sx):
            for yi in range(y, sy):
                if inside(arr, (xi, yi)):
                    arr[yi][xi] = char
    for i in range(x, x + sx):
        if inside(arr, (i, y)):
            arr[y][i] = 101 + color_offset
    for i in range(y, y + sy):
        if inside(arr, (x, i)):
            arr[i][x] = 100 + color_offset
    for i in range(x, x + sx):
        if inside(arr, (i, y + sy)):
            arr[y + sy][i] = 101 + color_offset
    for i in range(y, y + sy):
        if inside(arr, (x + sx, i)):
            arr[i][x + sx] = 100 + color_offset
    if inside(arr, (x, y)):
        arr[y][x] = 96 + color_offset
    if inside(arr, (x + sx, y)):
        arr[y][x + sx] = 99 + color_offset
    if inside(arr, (x + sx, y + sy)):
        arr[y + sy][x + sx] = 97 + color_offset
    if inside(arr, (x, y + sy)):
        arr[y + sy][x] = 98 + color_offset


# --- sound ---

if os.name == 'nt':
    import winsound
    def beep(freq, duration):
        """Windows uses the built-in winsound module."""
        try:
            winsound.Beep(int(freq), int(duration))
        except: pass
else:
    def beep(freq, duration):
        """Linux/macOS fallback using the ASCII Bell or system beep."""
        # Note: This requires the 'beep' package on many Linux distros
        # Alternatively, we can use the terminal bell, though it lacks frequency control
        os.system(f'play -n synth {duration/1000} square {freq} > /dev/null 2>&1')
        
def play_note(note_index, duration=100):
    """
    Converts a MIDI note index to frequency.
    Example: 60 is Middle C.
    """
    # Formula: f = 440 * 2^((n-69)/12)
    freq = 440 * (2 ** ((note_index - 69) / 12))
    beep(freq, duration)

# --- binary utilities ---
def export_raw_data(data, path, data_type="hex"):
    """Writes binary files from hex or bit strings."""
    try:
        path = path if '.'in path else f"{path}.bin"
        clean = data.replace(" ", "").lower()
        is_hex = data_type == "hex" or clean.startswith("0x") or any(c in clean for c in "23456789abcdef")
        if is_hex:
            clean = clean.replace("0x", "")
            if len(clean) % 2: clean = "0" + clean
            rw_byt = bytes.fromhex(clean)
        else:
            clean = clean.replace("0b", "")
            pad = (8 - len(clean) % 8) % 8
            clean = clean + ("0" * pad)
            byte_list = []
            for i in range(0, len(clean), 8):
                byte_list.append(int(clean[i:i+8], 2))
            rw_byt = bytes(byte_list)
        with open(path, "wb") as f: f.write(rw_byt)
    except Exception as e: print(f"Export Error: {e}")

def load_raw_data(path, return_type="byt"):
    """Loads a binary file. Appends .bin if needed."""
    try:
        if not os.path.splitext(path)[1]: path += ".bin"
        with open(path, "rb") as f:content = f.read()
        return content.hex() if return_type == "hex" else content
    except Exception as e:print(f"Load Error: {e}"); return None

# --- Binary Map Format ---

def load_csv_array(file):
    """Loads a CSV file into a 2D list (list[y][x])."""
    file_path=file.strip('"').strip("'")
    try:
        with open(file_path, mode='r', encoding='utf-8') as f:
            reader = list(csv.reader(f))
            result = []
            for line in reader:
                result.append([int(v) for v in line])
            return result
    except FileNotFoundError:
        print(f"Error: The file at {file_path} was not found.")
        return []

def csv_to_bin(csv_path, output_path, force_zero_rle=False):
    grid = load_csv_array(csv_path)
    if not grid: return
    h, w = len(grid), len(grid[0])
    f_d = [item + 1 if item >= -1 else -1 for sublist in grid for item in sublist]
    
    unique_tls = sorted(list(set(f_d)))
    lut_size, lut_vw = len(unique_tls), max(1, math.ceil(math.log2(max(max(f_d), 1) + 1)))
    data_b_width = max(1, math.ceil(math.log2(lut_size)))
    tl_to_idx = {tl: i for i, tl in enumerate(unique_tls)}
    if force_zero_rle: best_lbw = 0
    else:
        runs = []; curr_idx, count = tl_to_idx[f_d[0]], 1
        for x in f_d[1:]:
            idx = tl_to_idx[x]
            if idx == curr_idx: count += 1
            else: runs.append((curr_idx, count)); curr_idx, count = idx, 1
        runs.append((curr_idx, count))
        best_lbw, min_bits = 1, float('inf')
        for lbw in range(1, 16):
            total = sum(math.ceil(c / (2**lbw - 1)) * (data_b_width + lbw) for _, c in runs)
            if total < min_bits: min_bits, best_lbw = total, lbw
        best_lbw -= 1
    b_s = format(data_b_width, '08b') + format(lut_vw, '08b') + format(lut_size, '024b')
    b_s += "".join(format(tl, f'0{lut_vw}b') for tl in unique_tls)
    b_s += format(w, '012b') + format(h, '012b') + format(best_lbw, '04b')
    if best_lbw == 0:b_s += "".join(format(tl_to_idx[tl], f'0{data_b_width}b') for tl in f_d)
    else:
        for idx, count in runs:
            m_r = (2**best_lbw) - 1
            while count > 0:
                cur = min(count, m_r); b_s += format(idx, f'0{data_b_width}b') + format(cur, f'0{best_lbw}b'); count -= cur
    output_path += ".map.bin"
    export_raw_data(b_s, output_path, data_type="in")

def bin_to_csv(bin_path):
    raw_bytes = load_raw_data(bin_path, return_type="byt")
    if not raw_bytes: return
    b_s = "".join(format(b, '08b') for b in raw_bytes); p = 0
    dbw, lvw = int(b_s[p:p+8], 2), int(b_s[p+8:p+16], 2); p += 16
    ls = int(b_s[p:p+24], 2); p += 24
    lut = [int(b_s[p+i*lvw:p+(i+1)*lvw],2) for i in range(ls)]; p += ls * lvw
    w, h = int(b_s[p:p+12], 2), int(b_s[p+12:p+24], 2); p += 24
    lbw = int(b_s[p:p+4], 2); p += 4;flat = []
    while len(flat) < w * h:
        idx = int(b_s[p:p+dbw], 2); p += dbw
        if lbw == 0: flat.append(lut[idx] - 1)
        else:
            length = int(b_s[p:p+lbw], 2); p += lbw; flat.extend([lut[idx] - 1] * length)
    return [flat[i*w : (i+1)*w] for i in range(h)]

# Dim: gets the dimensions of an array
def dim(arr): 
    try: return len(arr[0]), len(arr)
    except: return (0, 0)

WIDTH=128
HEIGHT=32

low_res = {
    ((0, 0), (0, 0)): 0,
    ((1, 0), (0, 0)): 69,
    ((0, 1), (0, 0)): 68,
    ((0, 0), (1, 0)): 66,
    ((0, 0), (0, 1)): 67,
    ((1, 1), (0, 0)): 78,
    ((0, 0), (1, 1)): 65,
    ((1, 0), (1, 0)): 76,
    ((0, 1), (0, 1)): 77,
    ((1, 0), (0, 1)): 71,
    ((0, 1), (1, 0)): 75,
    ((1, 1), (1, 0)): 72,
    ((1, 1), (0, 1)): 73,
    ((1, 0), (1, 1)): 70,
    ((0, 1), (1, 1)): 74,
    ((1, 1), (1, 1)): 64
}

ilow_res = {v: k for k, v in low_res.items()}
# Engine character set
TILE_SET = r" []/\|_‾@#*%$=.^-+&<>?{}ABCDEFGHIJKLMNOPQRSTUVWXYZ!0123456789░▒▓█▄▖▗▝▘▙▚▛▜▟▞▌▐▀ ':;~`,()╱╲╳╋┻┳┫┣┏┛┗┓┃━⌷"
CHAR_MAP = {}

for index, char in enumerate(TILE_SET):
    if char not in CHAR_MAP:
        CHAR_MAP[char] = index

# ANSI Colors (Foreground/background): Defualt 0, Black 1, White 2, Red 3, Green 4, Yellow 5, Blue 6, Magenta 7, Cyan 8
ANSI_COLORS = ["0","30","37","31","32","33","34","35","36"]

def color(tile, fg=2 , bg=1, invert=False):
    if isinstance(tile, str):
        temp_tile = []
        for char in list(tile):
            if char in TILE_SET: temp_tile.append(TILE_SET.find(char))
        tile = temp_tile
    def sub_color(char, fg_c, bg_c, inv):
        # Mask to 4 bits to ensure they stay in their 'slots'
        f = fg_c & 0xF;b = bg_c & 0xF
        if inv: color_bits = (b << 4) | f
        else: color_bits = (f << 4) | b
        return char + (len(TILE_SET) * color_bits)
    if isinstance(tile, list):return [sub_color(x, fg, bg, invert) for x in tile]
    else:return sub_color(tile, fg, bg, invert)

def str_to_arr(string, color=0):
    string = string.upper()
    lines = [line.replace('"', "'") for line in string.split('\n') if line]
    max_len = max(len(line) for line in lines) if lines else 0
    result = []
    for line in lines:
        row = [CHAR_MAP[c] + color for c in line]
        while len(row) < max_len:
            row.append(0 + color)
        result.append(row)
    return result

def plot(screen, char, x, y, color=0):
    screen[y][x] = TILE_SET.find(char) + color

def gplot(screen, x, y, state, color_idx):
    tx, ty = x // 2, y // 2
    if not inside(screen, (tx, ty)): return
    t_len = len(TILE_SET);current_val = screen[ty][tx];char_idx = current_val % t_len
    color_bits = current_val // t_len;curr_fg = (color_bits >> 4) & 0xF
    curr_bg = color_bits & 0xF
    raw_matrix = ilow_res.get(char_idx, ((0,0),(0,0)))
    matrix = [list(row) for row in raw_matrix] 
    if state:
        if matrix == [[0,0],[0,0]]:
            curr_fg = color_idx
        elif color_idx == curr_bg and color_idx != curr_fg:
            curr_fg, curr_bg = curr_bg, curr_fg
            for row in range(2):
                for col in range(2): matrix[row][col] = 1 - matrix[row][col]
        elif color_idx != curr_fg: curr_fg = color_idx
    matrix[y % 2][x % 2] = 1 if state else 0
    lookup_matrix = tuple(tuple(row) for row in matrix)
    new_char_idx = low_res.get(lookup_matrix, 0)
    new_color_bits = (curr_fg << 4) | curr_bg
    screen[ty][tx] = new_char_idx + (t_len * new_color_bits)

def draw_box(arr, start_x, start_y, width, height, fg=0, bg=1, invert=False):
    """Draws a box."""
    for y in range(start_y, start_y + height):
        if 0 <= y < len(arr):
            if 0 <= start_x < len(arr[y]): arr[y][start_x] = color(5, fg, bg, invert)
            if 0 <= start_x + 1 < len(arr[y]): arr[y][start_x + 1] = color(5, fg, bg, invert)
            if 0 <= start_x + width - 2 < len(arr[y]): arr[y][start_x + width - 2] = color(5, fg, bg, invert)
            if 0 <= start_x + width - 1 < len(arr[y]): arr[y][start_x + width - 1] = color(5, fg, bg, invert)
    for x in range(start_x, start_x + width):
        if 0 <= start_y < len(arr) and 0 <= x < len(arr[0]): arr[start_y][x] = color(13, fg, bg, invert)
        if 0 <= start_y + height - 1 < len(arr) and 0 <= x < len(arr[0]): arr[start_y + height - 1][x] = color(13, fg, bg, invert)

def draw_tri(arr, sx, sy, ph, color_ = 0):
    for o in range(ph):
        if inside(arr, (sx, sy)): arr[sy][sx] = 3 + color_
        sx += 1
        sy -= 1
        
    if inside(arr, (sx, sy)): arr[sy][sx] = 3 + color_
    sx += 1
    for o in range(ph):
        if inside(arr, (sx, sy)): arr[sy][sx] = 4 + color_
        sx += 1
        sy += 1
    if inside(arr, (sx, sy)): arr[sy][sx] = 4 + color_
def blit(arr0, arr1, sx, sy):
    w, h = dim(arr1)
    for y in range(h):
        for x in range(w):
            if inside(arr0, (x + sx, y + sy)):
                t = arr1[y][x]
                if t >= 0: arr0[y + sy][x + sx] = t

def getfg(arr, xy):
    """Returns the foreground color index of a tile at (x, y)."""
    x, y = xy
    if not inside(arr, xy):return 0
    val = arr[y][x]; t_len = len(TILE_SET)
    if val < t_len: return 0
    color_bits = val // t_len;fg_idx = (color_bits >> 4) & 0xF
    return fg_idx

def getbg(arr, xy):
    """Returns the background color index of a tile at (x, y)."""
    x, y = xy
    if not inside(arr, xy): return 1
    val = arr[y][x];t_len = len(TILE_SET)
    if val < t_len:return 1
    color_bits = val // t_len;bg_idx = color_bits & 0xF
    return bg_idx

def clear(screen, char=0):
    h, w = len(screen), len(screen[0])
    if isinstance(char, list):
        c_len = len(char)
        for y in range(h):
            for x in range(w):
                screen[y][x] = char[x % c_len]
    else:
        for y in range(h):
            for x in range(w): screen[y][x] = char

def print_screen(screen, color_suppress=False):
    # \033[H moves cursor to top-left. 
    # We add \033[J to clear from cursor to end of screen to prevent ghosting.
    sys.stdout.write("\033[H")
    full_tile_set = TILE_SET
    t_len = len(full_tile_set)
    c_len = len(ANSI_COLORS)
    output = []
    q_pos = TILE_SET.find("'")
    for y in range(HEIGHT):
        line = screen[y]
        row_str = []
        last_color_idx = -1
        for val in line:
            
            if val >= t_len and not color_suppress:
                color_val = (val // t_len)
                fg_idx = (color_val >> 4) & 0xF
                bg_idx = color_val & 0xF
                fg_idx %= c_len
                bg_idx %= c_len
                char_idx = val % t_len
                
                if color_val != last_color_idx:
                    fg_code = ANSI_COLORS[fg_idx]
                    bg_raw = int(ANSI_COLORS[bg_idx])
                    bg_code = str(bg_raw + 10) if bg_raw != 0 else "0"
                    row_str.append(f"\033[{fg_code};{bg_code}m")
                    last_color_idx = color_val
                if char_idx == q_pos: row_str.append('"')
                else: row_str.append(full_tile_set[char_idx])
            else:
                if last_color_idx >= 0:
                    row_str.append("\033[0m")
                    last_color_idx = -1
                if val % t_len == q_pos: row_str.append('"')
                else:row_str.append(full_tile_set[val % t_len])
        
        # We join the row and ensure no extra trailing spaces are added by the terminal
        output.append("".join(row_str))

    # IMPORTANT: Use join with a literal newline, but ensure the final string 
    # ends with a reset code to prevent the last line from "bleeding" into the prompt.
    sys.stdout.write("\n".join(output) + "\033[0m")
    sys.stdout.flush()

def inside(screen, xy, wrap=False, inch=False):
    x, y = xy; h = len(screen); w = len(screen[0]) if h > 0 else 0
    if not wrap:
        return 0 <= x < w and 0 <= y < h
    wx, wy = xy
    if inch:
        wy = (wy + (x // w)) % h; wx = (wx + (y // h)) % w
    else: wx, wy = x % w, y % h
    return wx, wy

""" --- example program -- """
def init(screen):
    bg_buffer = [[0 for _ in range(WIDTH)] for _ in range(HEIGHT)]
    clear(bg_buffer, color(0, bg=2))
    clear(screen, color(0, bg=2))
    for tx in range(len(TILE_SET)):
        screen[0][tx % WIDTH] = color(tx, 6, 2)
        screen[1][tx % WIDTH] = color(tx, 3, 2)
        screen[2][tx % WIDTH] = color(tx, 4, 2)
    return bg_buffer, {
        'px': 15, 'py': 15, 
        'debug': copy.deepcopy(screen),
        'mint': -1
    }

def render_background(arr):
    draw_box(arr, 10, 10, 20, 10, 2, 3, True);arr[12][29] = color(0, bg=2);arr[12][28] = color(0, bg=2)

def tick(screen, vars, keys):
    last_p = vars['px'], vars['py']
    vars['mint'] *= -1
    nx, ny = vars['px'], vars['py']
    if 'w' in keys: ny -= 1
    if 's' in keys: ny += 1
    if 'a' in keys: nx -= 1
    if 'd' in keys: nx += 1
    
    # Minimal validation to prevent IndexError
    if inside(screen, (nx, ny)):
        if screen[ny][nx] == color(0, bg=2):
            vars['px'], vars['py'] = nx, ny
    
    clear(screen, color(8, 0, bg=0));blit(screen, vars['debug'], 0, 0)
    render_background(screen);screen[vars['py']][vars['px']] = color(8, 7, 2)

# --- end ---
def prosses_result(res, data_list):
    if res == None: return
    command = res.split()
    cl = len(command)
    if cl >= 3:
        if command[0] == "att":
            if command[1] == "frame_speed" and cl >=3: data_list[0] = int(command[2])
            if command[1] == "color_supp":
                if command[2].lower() == "true": data_list[1] = True
                elif command[2].lower() == "false": data_list[1] = False
                    
def run(tick_func, init_func, quit_on_q=True):
    if not valid_run: return
    screen = [[0 for _ in range(WIDTH)] for _ in range(HEIGHT)]
    init_output = init_func(screen); color_suppress = False; frame = 30
    data = [frame, color_suppress]
    if len(init_output) == 3: # while not used in the init in this file it can be used by other files that provide their own init and tick functions
        state_bg, state_vars, res = init_output
        prosses_result(res, data)
    else: state_bg, state_vars = init_output
    old_settings = None
    if os.name != 'nt':
        old_settings = termios.tcgetattr(sys.stdin); tty.setcbreak(sys.stdin.fileno())
    os.system('cls' if os.name == 'nt' else 'clear')
    sys.stdout.write("\033[?25l")
    elapses = 0
    try:
        while True:
            start = time.time()
            keys = get_keys()
            if 'q' in keys and quit_on_q: break
            res = tick_func(screen, state_vars, keys)
            if res != None and "quit" in res: break
            if 'alt' in keys and 'delete' in keys: 
                sys.stdout.write("\033[H\033[J")
                sys.stdout.flush()
            prosses_result(res, data) 
            frame, color_suppress = data 
            print_screen(screen, color_suppress) 
            elapsed = time.time() - start 
            time.sleep(max(0, 1/frame - elapsed))
            elapses += 1
    finally:
        if old_settings: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[?25h\033[0m"); print("Engine Stopped.")

if __name__ == "__main__":
    run(tick, init)