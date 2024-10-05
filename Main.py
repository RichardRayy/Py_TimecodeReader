import pyaudio
import numpy as np
from scipy.signal import butter, lfilter
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from collections import deque
import audioop
import os
from datetime import datetime

# 音频参数
CHUNK = 2048
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
SYNC_WORD = '0011111111111101'
jam = '00:00:00:00'
now_tc = '00:00:00:00'
last_cam = '-1'
jam_advice = False
jammed = False

# 数字码到摄像机映射
codes = [49,50,51,52,53,54,55,56,57,48]
cams = {}
for i,j in enumerate(codes):
    cams[j] = str(i+1)

def bin_to_bytes(a, size=1):
    ret = int(a, 2).to_bytes(size, byteorder='little')
    return ret

def bin_to_int(a):
    out = 0
    for i, j in enumerate(a):
        out += int(j) * 2**i
    return out

def decode_frame(frame):
    o = {}
    # TODO 其他解码
    try:
        o['frame_units'] = bin_to_int(frame[:4])
        o['user_bits_1'] = int.from_bytes(bin_to_bytes(frame[4:8]), byteorder='little')
        o['frame_tens'] = bin_to_int(frame[8:10])
        o['drop_frame'] = int.from_bytes(bin_to_bytes(frame[10:11]), byteorder='little')
        o['color_frame'] = int.from_bytes(bin_to_bytes(frame[11:12]), byteorder='little')
        o['user_bits_2'] = int.from_bytes(bin_to_bytes(frame[12:16]), byteorder='little')
        o['sec_units'] = bin_to_int(frame[16:20])
        o['user_bits_3'] = int.from_bytes(bin_to_bytes(frame[20:24]), byteorder='little')
        o['sec_tens'] = bin_to_int(frame[24:27])
        o['flag_1'] = int.from_bytes(bin_to_bytes(frame[27:28]), byteorder='little')
        o['user_bits_4'] = int.from_bytes(bin_to_bytes(frame[28:32]), byteorder='little')
        o['min_units'] = bin_to_int(frame[32:36])
        o['user_bits_5'] = int.from_bytes(bin_to_bytes(frame[36:40]), byteorder='little')
        o['min_tens'] = bin_to_int(frame[40:43])
        o['flag_2'] = int.from_bytes(bin_to_bytes(frame[43:44]), byteorder='little')
        o['user_bits_6'] = int.from_bytes(bin_to_bytes(frame[44:48]), byteorder='little')
        o['hour_units'] = bin_to_int(frame[48:52])
        o['user_bits_7'] = int.from_bytes(bin_to_bytes(frame[52:56]), byteorder='little')
        o['hour_tens'] = bin_to_int(frame[56:58])
        o['bgf'] = int.from_bytes(bin_to_bytes(frame[58:59]), byteorder='little')
        o['flag_3'] = int.from_bytes(bin_to_bytes(frame[59:60]), byteorder='little')
        o['user_bits_8'] = int.from_bytes(bin_to_bytes(frame[60:64]), byteorder='little')
        o['sync_word'] = int.from_bytes(bin_to_bytes(frame[64:], 2), byteorder='little')
        o['formatted_tc'] = "{:02d}:{:02d}:{:02d}:{:02d}".format(
            o['hour_tens'] * 10 + o['hour_units'],
            o['min_tens'] * 10 + o['min_units'],
            o['sec_tens'] * 10 + o['sec_units'],
            o['frame_tens'] * 10 + o['frame_units'],
        )
    except Exception as e:
        print(f"解码错误: {e}")
    return o

def print_tc():
    global jam, now_tc
    inter = 1 / (24000 / 1000)
    last_jam = jam
    h, m, s, f = [int(x) for x in jam.split(':')]
    while True:
        if jam is None:
            break
        if jam != last_jam:
            h, m, s, f = [int(x) for x in jam.split(':')]
            last_jam = jam
        tcp = "{:02d}:{:02d}:{:02d}:{:02d}".format(h, m, s, f)
        print(tcp)
        now_tc = tcp
        time.sleep(inter)
        f += 1
        if f >= 24:
            f = 0
            s += 1
        if s >= 60:
            s = 0
            m += 1
        if m >= 60:
            m = 0
            h += 1
        if h >= 24:
            h = 0

def decode_ltc(wave_frames):
    global jam
    frames = []
    output = ''
    out2 = ''
    last = None
    toggle = True
    sp = 1
    first = True
    for i in range(0, len(wave_frames), 2):
        data = wave_frames[i:i+2]
        pos = audioop.minmax(data, 2)
        if pos[0] < 0:
            cyc = 'Neg'
        else:
            cyc = 'Pos'
        if cyc != last:
            if sp >= 7:
                out2 = 'Samples: ' + str(sp) + ' ' + cyc + '\n'
                if sp > 14:
                    bit = '0'
                    output += str(bit)
                else:
                    if toggle:
                        bit = '1'
                        output += str(bit)
                        toggle = False
                    else:
                        toggle = True
                if len(output) >= len(SYNC_WORD):
                    if output[-len(SYNC_WORD):] == SYNC_WORD:
                        if len(output) > 80:
                            frame_bits = output[-80:]
                            frames.append(frame_bits)
                            output = ''
                            decoded = decode_frame(frame_bits)
                            if 'formatted_tc' in decoded:
                                print('接收到重置信号:', decoded['formatted_tc'])
                                jam = decoded['formatted_tc']
            sp = 1
            last = cyc
        else:
            sp += 1

def start_read_ltc():
    t = threading.Thread(target=print_tc, daemon=True)
    t.start()
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)
    print("正在捕获LTC")
    frames = []
    try:
        while True:
            data = stream.read(CHUNK)
            decode_ltc(data)
            frames.append(data)
    except KeyboardInterrupt:
        jam = None
        print("程序关闭")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

class TimecodeReaderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("时间码读取器")
        self.root.geometry("800x600")

        self.jam = '00:00:00:00'
        self.now_tc = '00:00:00:00'

        # 创建选项卡
        self.tabs = ttk.Notebook(root)
        self.monitor_tab = ttk.Frame(self.tabs)
        self.record_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.monitor_tab, text="监控")
        self.tabs.add(self.record_tab, text="记录")
        self.tabs.pack(expand=1, fill="both")

        # 监控标签内容
        self.timecode_label = ttk.Label(self.monitor_tab, text="--:--:--:--", font=("Courier", 40))
        self.timecode_label.pack(pady=20)



        # 输入电平
        self.level_var = tk.IntVar()
        self.level_meter = ttk.Progressbar(self.monitor_tab, maximum=100, variable=self.level_var)
        self.level_meter.pack(pady=10, fill=tk.X, padx=20)

      
        # 本地时间显示
        self.local_time_label = ttk.Label(self.monitor_tab, text="本地时间: --:--:--", font=("Helvetica", 16))
        self.local_time_label.pack(pady=5)

        # 记录标签内容
        self.timecode_log = scrolledtext.ScrolledText(self.record_tab, state='disabled')
        self.timecode_log.pack(expand=1, fill='both', padx=10, pady=10)

        # 控制按钮
        self.start_button = ttk.Button(root, text="开始", command=self.toggle_start)
        self.start_button.pack(pady=10)

        # 菜单栏
        self.menu = tk.Menu(root)
        self.root.config(menu=self.menu)
        self.input_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="输入", menu=self.input_menu)
        self.populate_input_menu()

        self.record_menu = tk.Menu(self.menu, tearoff=0)
        self.menu.add_cascade(label="记录", menu=self.record_menu)
        self.populate_record_menu()

        # 线程控制
        self.reading_thread = None
        self.running = False

        # 更新本地时间
        self.update_local_time()

    def populate_input_menu(self):
        p = pyaudio.PyAudio()
        self.input_devices = []
        for i in range(p.get_device_count()):
            device = p.get_device_info_by_index(i)
            if device['maxInputChannels'] > 0:
                self.input_devices.append(device)
        if not self.input_devices:
            self.input_menu.add_command(label="无可用输入设备", state="disabled")
        else:
            self.selected_device = self.input_devices[0]
            for device in self.input_devices:
                self.input_menu.add_radiobutton(label=device['name'],
                                               command=lambda d=device: self.select_input(d))
            self.input_menu.invoke(0)  # 选中第一个设备

    def select_input(self, device):
        self.selected_device = device
        print(f"选择输入设备: {device['name']}")

    def populate_record_menu(self):
        self.record_type = tk.StringVar(value="None")
        options = ["None", "时间码"]
        for option in options:
            self.record_menu.add_radiobutton(label=option, variable=self.record_type, value=option)

        self.record_menu.add_separator()
        self.record_menu.add_command(label="清除记录", command=self.clear_log)
        self.record_menu.add_command(label="另存为...", command=self.save_log)

    def clear_log(self):
        self.timecode_log.config(state='normal')
        self.timecode_log.delete(1.0, tk.END)
        self.timecode_log.config(state='disabled')

    def save_log(self):
        log_content = self.timecode_log.get(1.0, tk.END).strip()
        if not log_content:
            messagebox.showwarning("保存记录", "记录为空，无需保存。")
            return
        file_path = filedialog.asksaveasfilename(defaultextension=".txt",
                                                 filetypes=[("文本文件", "*.txt"),
                                                            ("所有文件", "*.*")])
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                messagebox.showinfo("保存记录", f"记录已保存到 {file_path}")
            except Exception as e:
                messagebox.showerror("保存错误", f"无法保存记录: {e}")

    def toggle_start(self):
        if self.running:
            # 停止
            self.running = False
            if self.reading_thread:
                self.reading_thread.join()
                self.reading_thread = None
            self.start_button.config(text="开始")
            print("停止捕获LTC")
        else:
            # 开始
            if not hasattr(self, 'selected_device'):
                messagebox.showwarning("开始", "请选择输入设备。")
                return
            self.running = True
            self.reading_thread = threading.Thread(target=self.read_ltc, daemon=True)
            self.reading_thread.start()
            self.start_button.config(text="停止")
            print("开始捕获LTC")

    def read_ltc(self):
        global jam, now_tc
        p = pyaudio.PyAudio()
        try:
            stream = p.open(format=FORMAT,
                            channels=CHANNELS,
                            rate=RATE,
                            input=True,
                            frames_per_buffer=CHUNK,
                            input_device_index=self.selected_device['index'])
        except Exception as e:
            messagebox.showerror("音频错误", f"无法打开音频流: {e}")
            self.running = False
            return

        print("正在捕获LTC")
        try:
            while self.running:
                data = stream.read(CHUNK, exception_on_overflow=False)
                self.decode_ltc(data)
        except Exception as e:
            print(f"音频流处理错误: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    def decode_ltc(self, wave_frames):
        global jam
        frames = []
        output = ''
        out2 = ''
        last = None
        toggle = True
        sp = 1
        first = True
        for i in range(0, len(wave_frames), 2):
            data = wave_frames[i:i+2]
            pos = audioop.minmax(data, 2)
            if pos[0] < 0:
                cyc = 'Neg'
            else:
                cyc = 'Pos'
            if cyc != last:
                if sp >= 7:
                    out2 = 'Samples: ' + str(sp) + ' ' + cyc + '\n'
                    if sp > 14:
                        bit = '0'
                        output += str(bit)
                    else:
                        if toggle:
                            bit = '1'
                            output += str(bit)
                            toggle = False
                        else:
                            toggle = True
                    if len(output) >= len(SYNC_WORD):
                        if output[-len(SYNC_WORD):] == SYNC_WORD:
                            if len(output) > 80:
                                frame_bits = output[-80:]
                                frames.append(frame_bits)
                                output = ''
                                decoded = decode_frame(frame_bits)
                                if 'formatted_tc' in decoded:
                                    print('接收到重置信号:', decoded['formatted_tc'])
                                    jam = decoded['formatted_tc']
                                    self.update_timecode(jam)
                sp = 1
                last = cyc
            else:
                sp += 1

    def update_timecode(self, tc):
        # 修复时间码回退问题
        if self.compare_timecode(tc, self.now_tc) >= 0:
            self.now_tc = tc
            # 获取当前本地系统时间
            local_time = datetime.now().strftime("%H:%M:%S")
            combined_entry = f"{local_time} - {tc}"
            self.timecode_label.config(text=combined_entry)
            record_type = self.record_type.get()
            if record_type != "None":
                self.timecode_log.config(state='normal')
                if record_type in ["时间码", "时间码 + 原始帧"]:
                    self.timecode_log.insert(tk.END, f"{combined_entry}\n")
                # 若需要添加原始帧信息，可在此扩展
                self.timecode_log.config(state='disabled')

    def compare_timecode(self, tc1, tc2):
        # 比较两个时间码，返回1如果tc1 > tc2，-1如果tc1 < tc2，0如果相等
        h1, m1, s1, f1 = map(int, tc1.split(':'))
        h2, m2, s2, f2 = map(int, tc2.split(':'))
        if h1 != h2:
            return 1 if h1 > h2 else -1
        if m1 != m2:
            return 1 if m1 > m2 else -1
        if s1 != s2:
            return 1 if s1 > s2 else -1
        if f1 != f2:
            return 1 if f1 > f2 else -1
        return 0

    def update_local_time(self):
        # 定期更新本地时间显示
        if self.now_tc != '00:00:00:00':
            # 如果已经开始解码，显示已附加的本地时间
            pass
        else:
            # 显示默认本地时间
            local_time = datetime.now().strftime("%H:%M:%S")
            self.local_time_label.config(text=f"本地时间: {local_time}")
        self.root.after(1000, self.update_local_time)  # 每秒更新一次

def main():
    root = tk.Tk()
    app = TimecodeReaderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()