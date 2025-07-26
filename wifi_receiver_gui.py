# -*- coding: utf-8 -*-
import socket
import os
import datetime
import threading
import sys
import time
import json
import hashlib
import tkinter as tk
from tkinter import ttk, scrolledtext
from tkinter import messagebox, filedialog

# 图像接收配置
IMAGE_HOST = '0.0.0.0'
IMAGE_PORT = 8888

# 指令发送配置
SENDER_IP = '192.168.1.205'  # 发送端的IP地址，需要根据实际情况修改
COMMAND_PORT = 8889

# 全局变量控制程序运行
running = True
command_socket = None
image_connected = False
command_connected = False
last_runtime_status = ""
last_gpio_data = ""
last_temp_humidity = ""
latest_sensor_data = None  # 存储最新的传感器数据

# 状态变量
monitoring_status = False
recording_status = False
data_recording_status = False
combined_status = False

# 记录时间相关变量
monitoring_start_time = None
recording_start_time = None
data_recording_start_time = None
combined_start_time = None

# 消息类型定义
class MessageType:
    STATUS = "STATUS"
    RUNTIME_STATUS = "RUNTIME_STATUS"
    GPIO_DATA = "GPIO_DATA"
    TEMP_HUMIDITY = "TEMP_HUMIDITY"
    SYSTEM_INFO = "SYSTEM_INFO"
    FILE_LIST = "FILE_LIST"
    FILE_TRANSFER = "FILE_TRANSFER"

class WiFiReceiverGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("WiFi摄像头控制系统 - 接收端")
        self.root.geometry("800x600")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 创建主框架
        self.create_widgets()
        
        # 启动后台线程
        self.start_background_threads()
        
        # 定期更新GUI
        self.update_gui()
    
    def create_widgets(self):
        # 标题
        title_label = tk.Label(self.root, text="WiFi摄像头控制系统 - 接收端", 
                              font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        # 连接状态框架
        status_frame = tk.Frame(self.root)
        status_frame.pack(pady=10, padx=20, fill="x")
        
        # 连接状态标签
        self.command_status_label = tk.Label(status_frame, text="指令连接状态: 未连接", 
                                           fg="red", font=("Arial", 10))
        self.command_status_label.pack(anchor="w")
        
        self.image_status_label = tk.Label(status_frame, text="图像服务器状态: 未启动", 
                                         fg="red", font=("Arial", 10))
        self.image_status_label.pack(anchor="w")
        
        # 控制按钮框架
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=20)
        
        # 第一行按钮
        row1_frame = tk.Frame(button_frame)
        row1_frame.pack(pady=5)
        
        # 数据监测控制按钮
        self.monitoring_btn = tk.Button(row1_frame, text="开启数据监测", 
                                      command=self.toggle_monitoring,
                                      width=15, height=2, font=("Arial", 10))
        self.monitoring_btn.pack(side="left", padx=5)
        
        # 录像控制按钮
        self.recording_btn = tk.Button(row1_frame, text="开启录像", 
                                     command=self.toggle_recording,
                                     width=15, height=2, font=("Arial", 10))
        self.recording_btn.pack(side="left", padx=5)
        
        # 数据记录控制按钮
        self.data_recording_btn = tk.Button(row1_frame, text="开启数据记录", 
                                          command=self.toggle_data_recording,
                                          width=15, height=2, font=("Arial", 10))
        self.data_recording_btn.pack(side="left", padx=5)
        
        # 录像+数据控制按钮
        self.combined_btn = tk.Button(row1_frame, text="录像+数据", 
                                    command=self.toggle_combined,
                                    width=15, height=2, font=("Arial", 10))
        self.combined_btn.pack(side="left", padx=5)
        
        # 第二行按钮
        row2_frame = tk.Frame(button_frame)
        row2_frame.pack(pady=5)
        
        # 发送当前图像按钮
        self.send_image_btn = tk.Button(row2_frame, text="发送当前图像", 
                                      command=self.send_current_image,
                                      width=15, height=2, font=("Arial", 10))
        self.send_image_btn.pack(side="left", padx=5)
        
        # 文件传输按钮
        self.file_transfer_btn = tk.Button(row2_frame, text="文件传输", 
                                         command=self.open_file_transfer,
                                         width=15, height=2, font=("Arial", 10),
                                         bg="lightcyan")
        self.file_transfer_btn.pack(side="left", padx=5)
        
        # 退出程序按钮
        self.quit_btn = tk.Button(row2_frame, text="退出程序", 
                                command=self.on_closing,
                                width=15, height=2, font=("Arial", 10),
                                bg="red", fg="white")
        self.quit_btn.pack(side="left", padx=5)
        
        # 状态信息显示区域
        info_frame = tk.Frame(self.root)
        info_frame.pack(pady=10, padx=20, fill="both", expand=True)
        
        # 运行状态标签
        self.runtime_status_label = tk.Label(info_frame, text="运行状态: 等待连接...", 
                                           font=("Arial", 10), anchor="w")
        self.runtime_status_label.pack(fill="x", pady=2)
        
        # 传感器数据显示框架
        sensor_frame = tk.LabelFrame(info_frame, text="传感器数据", font=("Arial", 10, "bold"))
        sensor_frame.pack(fill="x", pady=5)
        
        # ADC数据显示
        adc_frame = tk.Frame(sensor_frame)
        adc_frame.pack(fill="x", padx=5, pady=2)
        
        tk.Label(adc_frame, text="📊 ADC数据:", font=("Arial", 9, "bold"), anchor="w").pack(anchor="w")
        self.voltage_label = tk.Label(adc_frame, text="  通道0 - 电压: 未检测", 
                                    font=("Arial", 9), anchor="w", fg="gray")
        self.voltage_label.pack(anchor="w")
        
        self.current_label = tk.Label(adc_frame, text="  通道1 - 电流: 未检测", 
                                    font=("Arial", 9), anchor="w", fg="gray")
        self.current_label.pack(anchor="w")
        
        self.voltage_ch2_label = tk.Label(adc_frame, text="  通道2 - 电压: 未检测", 
                                        font=("Arial", 9), anchor="w", fg="gray")
        self.voltage_ch2_label.pack(anchor="w")
        
        self.voltage_ch3_label = tk.Label(adc_frame, text="  通道3 - 电压: 未检测", 
                                        font=("Arial", 9), anchor="w", fg="gray")
        self.voltage_ch3_label.pack(anchor="w")
        
        # 环境传感器数据显示
        env_frame = tk.Frame(sensor_frame)
        env_frame.pack(fill="x", padx=5, pady=2)
        
        tk.Label(env_frame, text="🌡️ 环境传感器数据:", font=("Arial", 9, "bold"), anchor="w").pack(anchor="w")
        self.lux_label = tk.Label(env_frame, text="  光照强度: 未检测", 
                                font=("Arial", 9), anchor="w", fg="gray")
        self.lux_label.pack(anchor="w")
        
        self.temperature_label = tk.Label(env_frame, text="  温度: 未检测", 
                                        font=("Arial", 9), anchor="w", fg="gray")
        self.temperature_label.pack(anchor="w")
        
        self.pressure_label = tk.Label(env_frame, text="  气压: 未检测", 
                                     font=("Arial", 9), anchor="w", fg="gray")
        self.pressure_label.pack(anchor="w")
        
        self.humidity_label = tk.Label(env_frame, text="  湿度: 未检测", 
                                     font=("Arial", 9), anchor="w", fg="gray")
        self.humidity_label.pack(anchor="w")
        
        self.altitude_label = tk.Label(env_frame, text="  海拔: 未检测", 
                                     font=("Arial", 9), anchor="w", fg="gray")
        self.altitude_label.pack(anchor="w")
        
        # 兼容性保留的标签（用于原有逻辑）
        self.gpio_data_label = tk.Label(info_frame, text="", font=("Arial", 8), anchor="w")
        self.temp_humidity_label = tk.Label(info_frame, text="", font=("Arial", 8), anchor="w")
        
        # 数据监测时间显示标签
        self.monitoring_time_label = tk.Label(info_frame, text="数据监测时长: 未开始", 
                                            font=("Arial", 10), anchor="w", fg="darkgreen")
        self.monitoring_time_label.pack(fill="x", pady=2)
        
        # 记录时间显示标签
        self.recording_time_label = tk.Label(info_frame, text="录像时长: 未开始", 
                                           font=("Arial", 10), anchor="w", fg="blue")
        self.recording_time_label.pack(fill="x", pady=2)
        
        self.data_recording_time_label = tk.Label(info_frame, text="数据记录时长: 未开始", 
                                                font=("Arial", 10), anchor="w", fg="green")
        self.data_recording_time_label.pack(fill="x", pady=2)
        
        self.combined_time_label = tk.Label(info_frame, text="录像+数据时长: 未开始", 
                                          font=("Arial", 10), anchor="w", fg="purple")
        self.combined_time_label.pack(fill="x", pady=2)
        
        # 日志显示区域
        log_label = tk.Label(info_frame, text="系统日志:", font=("Arial", 10, "bold"))
        log_label.pack(anchor="w", pady=(10, 5))
        
        self.log_text = scrolledtext.ScrolledText(info_frame, height=15, width=80, 
                                                font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)        
        # 文件传输相关变量
        self.file_transfer_window = None
        self.file_list = []
        self.current_download = None
        self.download_buffer = b''
        self.download_dir = ""
        self.download_queue = []
        self.file_tree = None
        self.expected_md5 = ""
        self.received_chunks = {}
        self.expected_chunks = 0
        
    def log_message(self, message):
        """在日志区域添加消息"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        # 在主线程中更新GUI
        self.root.after(0, lambda: self._append_log(log_entry))
    
    def _append_log(self, log_entry):
        """在GUI主线程中添加日志"""
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        
        # 限制日志行数，保留最后1000行
        lines = self.log_text.get("1.0", tk.END).split('\n')
        if len(lines) > 1000:
            self.log_text.delete("1.0", f"{len(lines) - 1000}.0")
    
    def toggle_monitoring(self):
        """切换数据监测状态"""
        global monitoring_status, monitoring_start_time
        if not monitoring_status:
            self.send_command("start_monitoring")
            monitoring_status = True
            monitoring_start_time = datetime.datetime.now()
            self.monitoring_btn.config(text="停止数据监测", bg="lightgreen")
            self.log_message("开启数据监测")
        else:
            self.send_command("stop_monitoring")
            monitoring_status = False
            monitoring_start_time = None
            self.monitoring_btn.config(text="开启数据监测", bg="SystemButtonFace")
            self.log_message("停止数据监测")
    
    def toggle_recording(self):
        """切换录像状态"""
        global recording_status, recording_start_time
        if not recording_status:
            self.send_command("rb")
            recording_status = True
            recording_start_time = datetime.datetime.now()
            self.recording_btn.config(text="停止录像", bg="orange")
            self.log_message("开启延时录像")
        else:
            self.send_command("rs")
            recording_status = False
            recording_start_time = None
            self.recording_btn.config(text="开启录像", bg="SystemButtonFace")
            self.log_message("停止延时录像")
    
    def toggle_data_recording(self):
        """切换数据记录状态"""
        global data_recording_status, data_recording_start_time
        if not data_recording_status:
            self.send_command("cb")
            data_recording_status = True
            data_recording_start_time = datetime.datetime.now()
            self.data_recording_btn.config(text="停止数据记录", bg="lightblue")
            self.log_message("开启数据记录")
        else:
            self.send_command("cs")
            data_recording_status = False
            data_recording_start_time = None
            self.data_recording_btn.config(text="开启数据记录", bg="SystemButtonFace")
            self.log_message("停止数据记录")
    
    def toggle_combined(self):
        """切换录像+数据状态"""
        global combined_status, combined_start_time
        if not combined_status:
            self.send_command("rcb")
            combined_status = True
            combined_start_time = datetime.datetime.now()
            self.combined_btn.config(text="停止录像+数据", bg="lightgreen")
            self.log_message("开启延时录像+数据记录")
        else:
            self.send_command("rcs")
            combined_status = False
            combined_start_time = None
            self.combined_btn.config(text="录像+数据", bg="SystemButtonFace")
            self.log_message("停止延时录像+数据记录")
    
    def send_current_image(self):
        """发送当前图像"""
        self.send_command("s")
        self.log_message("请求发送当前图像")
    
    def open_file_transfer(self):
        """打开文件传输窗口"""
        if not command_connected:
            messagebox.showwarning("连接错误", "未连接到发送端，无法进行文件传输")
            return
        
        # 如果窗口已存在，先关闭
        if self.file_transfer_window:
            self.file_transfer_window.destroy()
        
        # 创建文件传输窗口
        self.file_transfer_window = tk.Toplevel(self.root)
        self.file_transfer_window.title("文件传输")
        self.file_transfer_window.geometry("600x400")
        self.file_transfer_window.transient(self.root)
        
        # 请求文件列表
        self.send_command("list_files")
        self.log_message("正在获取发送端文件列表...")
        
        # 创建界面
        self.create_file_transfer_ui()
    
    def create_file_transfer_ui(self):
        """创建文件传输界面"""
        if not self.file_transfer_window:
            return
        
        # 标题
        title_label = tk.Label(self.file_transfer_window, text="发送端文件列表", 
                              font=("Arial", 12, "bold"))
        title_label.pack(pady=10)
        
        # 文件列表框架
        list_frame = tk.Frame(self.file_transfer_window)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 创建Treeview来显示文件列表
        columns = ('name', 'size', 'modified')
        self.file_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=10)
        
        # 定义列标题
        self.file_tree.heading('name', text='文件名')
        self.file_tree.heading('size', text='大小(MB)')
        self.file_tree.heading('modified', text='修改时间')
        
        # 设置列宽
        self.file_tree.column('name', width=200)
        self.file_tree.column('size', width=100)
        self.file_tree.column('modified', width=150)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=scrollbar.set)
        
        self.file_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 按钮框架
        button_frame = tk.Frame(self.file_transfer_window)
        button_frame.pack(pady=10)
        
        # 下载按钮
        self.download_btn = tk.Button(button_frame, text="下载选中文件", 
                                    command=self.download_selected_files,
                                    bg="lightgreen", font=("Arial", 10))
        self.download_btn.pack(side="left", padx=5)
        
        # 刷新按钮
        refresh_btn = tk.Button(button_frame, text="刷新列表", 
                              command=self.refresh_file_list,
                              font=("Arial", 10))
        refresh_btn.pack(side="left", padx=5)
        
        # 关闭按钮
        close_btn = tk.Button(button_frame, text="关闭", 
                            command=self.close_file_transfer,
                            font=("Arial", 10))
        close_btn.pack(side="left", padx=5)
        
        # 进度显示框架
        self.progress_frame = tk.Frame(self.file_transfer_window)
        self.progress_frame.pack(fill="x", padx=10, pady=5)
        
        # 进度标签
        self.progress_label = tk.Label(self.progress_frame, text="", font=("Arial", 9))
        self.progress_label.pack()
        
        # 进度条
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode='determinate')
        self.progress_bar.pack(fill="x", pady=2)
        
        # 速度标签
        self.speed_label = tk.Label(self.progress_frame, text="", font=("Arial", 9))
        self.speed_label.pack()
        
        # 隐藏进度显示
        self.progress_frame.pack_forget()
    
    def refresh_file_list(self):
        """刷新文件列表"""
        self.send_command("list_files")
        self.log_message("刷新文件列表...")
    
    def download_selected_files(self):
        """下载选中的文件"""
        if not self.file_tree:
            return
        
        selected_items = self.file_tree.selection()
        if not selected_items:
            messagebox.showwarning("选择错误", "请先选择要下载的文件")
            return
        
        # 选择保存目录
        save_dir = filedialog.askdirectory(title="选择保存目录")
        if not save_dir:
            return
        
        self.download_dir = save_dir
        self.download_queue = []
        
        # 获取选中文件的名称
        for item in selected_items:
            filename = self.file_tree.item(item, 'values')[0]
            self.download_queue.append(filename)
        
        # 开始下载
        self.start_download()
    
    def start_download(self):
        """开始下载队列中的文件"""
        if not self.download_queue:
            messagebox.showinfo("下载完成", "所有文件下载完成！")
            self.progress_frame.pack_forget()
            return
        
        filename = self.download_queue.pop(0)
        self.current_download = {
            "filename": filename,
            "start_time": time.time(),
            "bytes_received": 0,
            "total_size": 0,
            "last_update_time": time.time()
        }
        
        # 重置下载状态
        self.download_buffer = b''
        self.expected_md5 = ""
        self.received_chunks = {}
        self.expected_chunks = 0
        
        # 显示进度
        self.progress_frame.pack(fill="x", padx=10, pady=5)
        self.progress_label.config(text=f"正在下载: {filename}")
        self.progress_bar['value'] = 0
        self.speed_label.config(text="准备下载...")
        
        # 发送下载命令
        self.send_command(f"download_file:{filename}")
        self.log_message(f"开始下载文件: {filename}")
    
    def close_file_transfer(self):
        """关闭文件传输窗口"""
        if self.file_transfer_window:
            self.file_transfer_window.destroy()
            self.file_transfer_window = None
    
    def update_file_list_display(self):
        """更新文件列表显示"""
        if not self.file_tree:
            return
        
        # 清空现有项目
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        
        # 添加文件项目
        for file_info in self.file_list:
            self.file_tree.insert('', 'end', values=(
                file_info['name'],
                file_info['size_mb'],
                file_info['modified']
            ))
    
    def update_download_progress(self, bytes_sent, total_size, progress, speed_mbps=None):
        """更新下载进度 - 优化版本"""
        if not self.current_download:
            return
        
        # 更新进度条
        self.progress_bar['value'] = progress
        
        # 计算下载速度
        current_time = time.time()
        elapsed_time = current_time - self.current_download["start_time"]
        
        if speed_mbps is not None:
            # 使用服务器提供的速度信息
            speed_text = f"{speed_mbps:.2f} MB/s"
        else:
            # 本地计算速度
            if elapsed_time > 0:
                speed_bps = self.current_download["bytes_received"] / elapsed_time
                speed_mbps_local = speed_bps / (1024 * 1024)
                speed_text = f"{speed_mbps_local:.2f} MB/s"
            else:
                speed_text = "计算中..."
        
        # 计算预计剩余时间
        if speed_mbps and speed_mbps > 0:
            remaining_mb = (total_size - bytes_sent) / (1024 * 1024)
            eta_seconds = remaining_mb / speed_mbps
            if eta_seconds < 60:
                eta_text = f"剩余 {eta_seconds:.0f}秒"
            else:
                eta_minutes = eta_seconds / 60
                eta_text = f"剩余 {eta_minutes:.1f}分钟"
        else:
            eta_text = ""
        
        self.speed_label.config(text=f"速度: {speed_text} {eta_text}")
        
        # 更新进度文本
        mb_sent = bytes_sent / (1024 * 1024)
        mb_total = total_size / (1024 * 1024)
        self.progress_label.config(text=f"下载: {self.current_download['filename']} ({mb_sent:.1f}/{mb_total:.1f} MB - {progress:.1f}%)")
        
        # 记录最后更新时间
        self.current_download["last_update_time"] = current_time
    
    def save_downloaded_file(self):
        """保存下载的文件 - 优化版本with校验"""
        if not self.current_download or not self.download_buffer:
            return
        
        try:
            filename = self.current_download["filename"]
            filepath = os.path.join(self.download_dir, filename)
            
            # 保存文件
            with open(filepath, 'wb') as f:
                f.write(self.download_buffer)
            
            # 验证文件完整性
            if self.expected_md5:
                actual_md5 = self.calculate_file_md5(filepath)
                if actual_md5 == self.expected_md5:
                    self.log_message(f"文件保存成功并校验通过: {filepath}")
                    
                    # 显示传输统计
                    total_time = time.time() - self.current_download["start_time"]
                    file_size_mb = len(self.download_buffer) / (1024 * 1024)
                    avg_speed = file_size_mb / total_time if total_time > 0 else 0
                    self.log_message(f"传输统计: 大小={file_size_mb:.2f}MB, 用时={total_time:.2f}s, 平均速度={avg_speed:.2f}MB/s")
                else:
                    self.log_message(f"警告: 文件校验失败! 期望MD5={self.expected_md5}, 实际MD5={actual_md5}")
                    messagebox.showwarning("校验失败", f"文件 {filename} 校验失败，可能已损坏")
            else:
                self.log_message(f"文件保存成功: {filepath} (未校验)")
            
            self.download_buffer = b''
            
        except Exception as e:
            self.log_message(f"保存文件失败: {e}")
            messagebox.showerror("保存失败", f"保存文件失败: {e}")
    
    def calculate_file_md5(self, filepath):
        """计算文件的MD5校验值"""
        try:
            hash_md5 = hashlib.md5()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            self.log_message(f"计算MD5失败: {e}")
            return ""
    
    def send_command(self, command):
        """发送指令到发送端"""
        global command_socket, command_connected
        if command_connected and command_socket:
            try:
                command_socket.sendall(f"{command}\n".encode())
                self.log_message(f"已发送指令: {command}")
            except Exception as e:
                self.log_message(f"发送指令失败: {e}，连接可能已断开")
                command_connected = False
        else:
            self.log_message("未连接到发送端，无法发送指令")
    
    def update_sensor_data_display(self):
        """更新传感器数据显示"""
        global latest_sensor_data, monitoring_status, recording_status, data_recording_status, combined_status
        
        # 检查是否应该显示数据（数据监测、录像、数据记录或录像+数据模式下）
        should_display_data = monitoring_status or recording_status or data_recording_status or combined_status
        
        if should_display_data and latest_sensor_data:
            # 获取ADC数据
            adc_data = latest_sensor_data.get('adc_data', {})
            env_data = latest_sensor_data.get('env_data', {})
            
            if adc_data:
                # 更新ADC数据显示
                voltage = adc_data.get('channel0_voltage', 0)
                current = adc_data.get('channel1_current', 0)
                voltage_ch2 = adc_data.get('channel2_voltage', 0)
                voltage_ch3 = adc_data.get('channel3_voltage', 0)
                raw_values = adc_data.get('raw_values', [0, 0, 0, 0])
                
                self.voltage_label.config(
                    text=f"  通道0 - 电压: {voltage:8.2f} V    (原始值: {raw_values[0]:6})",
                    fg="darkblue"
                )
                self.current_label.config(
                    text=f"  通道1 - 电流: {current:8.2f} A    (原始值: {raw_values[1]:6})",
                    fg="darkblue"
                )
                self.voltage_ch2_label.config(
                    text=f"  通道2 - 电压: {voltage_ch2:8.3f} V  (原始值: {raw_values[2]:6})",
                    fg="darkblue"
                )
                self.voltage_ch3_label.config(
                    text=f"  通道3 - 电压: {voltage_ch3:8.3f} V  (原始值: {raw_values[3]:6})",
                    fg="darkblue"
                )
            else:
                # ADC数据不可用
                self.voltage_label.config(text="  通道0 - 电压: 数据不可用", fg="orange")
                self.current_label.config(text="  通道1 - 电流: 数据不可用", fg="orange")
                self.voltage_ch2_label.config(text="  通道2 - 电压: 数据不可用", fg="orange")
                self.voltage_ch3_label.config(text="  通道3 - 电压: 数据不可用", fg="orange")
            
            if env_data:
                # 更新环境传感器数据显示
                lux = env_data.get('lux', 0)
                temperature = env_data.get('temperature', 0)
                pressure = env_data.get('pressure', 0)
                humidity = env_data.get('humidity', 0)
                altitude = env_data.get('altitude', 0)
                
                self.lux_label.config(
                    text=f"  光照强度: {lux:8.2f} lux",
                    fg="darkorange"
                )
                self.temperature_label.config(
                    text=f"  温度: {temperature:6.2f} °C",
                    fg="red"
                )
                self.pressure_label.config(
                    text=f"  气压: {pressure:8.2f} Pa",
                    fg="purple"
                )
                self.humidity_label.config(
                    text=f"  湿度: {humidity:6.2f} %",
                    fg="blue"
                )
                self.altitude_label.config(
                    text=f"  海拔: {altitude:6} m",
                    fg="brown"
                )
            else:
                # 环境传感器数据不可用
                self.lux_label.config(text="  光照强度: 数据不可用", fg="orange")
                self.temperature_label.config(text="  温度: 数据不可用", fg="orange")
                self.pressure_label.config(text="  气压: 数据不可用", fg="orange")
                self.humidity_label.config(text="  湿度: 数据不可用", fg="orange")
                self.altitude_label.config(text="  海拔: 数据不可用", fg="orange")
        else:
            # 未开启监测或无数据时显示"未检测"
            self.voltage_label.config(text="  通道0 - 电压: 未检测", fg="gray")
            self.current_label.config(text="  通道1 - 电流: 未检测", fg="gray")
            self.voltage_ch2_label.config(text="  通道2 - 电压: 未检测", fg="gray")
            self.voltage_ch3_label.config(text="  通道3 - 电压: 未检测", fg="gray")
            
            self.lux_label.config(text="  光照强度: 未检测", fg="gray")
            self.temperature_label.config(text="  温度: 未检测", fg="gray")
            self.pressure_label.config(text="  气压: 未检测", fg="gray")
            self.humidity_label.config(text="  湿度: 未检测", fg="gray")
            self.altitude_label.config(text="  海拔: 未检测", fg="gray")
    
    def update_gui(self):
        """定期更新GUI状态"""
        # 更新连接状态
        if command_connected:
            self.command_status_label.config(text="指令连接状态: 已连接", fg="green")
        else:
            self.command_status_label.config(text="指令连接状态: 未连接", fg="red")
        
        if image_connected:
            self.image_status_label.config(text="图像服务器状态: 运行中", fg="green")
        else:
            self.image_status_label.config(text="图像服务器状态: 未启动", fg="red")
        
        # 更新状态信息
        if last_runtime_status:
            self.runtime_status_label.config(text=f"运行状态: {last_runtime_status}")
        else:
            # 如果没有运行时状态数据，根据连接状态显示相应信息
            if command_connected:
                self.runtime_status_label.config(text="运行状态: 已连接，等待数据...")
            else:
                self.runtime_status_label.config(text="运行状态: 等待连接...")
        
        # 更新传感器数据显示
        self.update_sensor_data_display()
        
        if last_gpio_data:
            self.gpio_data_label.config(text=f"GPIO数据: {last_gpio_data}")
        
        if last_temp_humidity:
            self.temp_humidity_label.config(text=f"温湿度: {last_temp_humidity}")
        
        # 更新记录时间
        self.update_recording_times()
        
        # 500毫秒后再次更新
        self.root.after(500, self.update_gui)
    
    def update_recording_times(self):
        """更新记录时间显示"""
        global monitoring_status, recording_status, data_recording_status, combined_status
        global monitoring_start_time, recording_start_time, data_recording_start_time, combined_start_time
        
        current_time = datetime.datetime.now()
        
        # 优先显示记录时长逻辑：
        # 1. 如果有录像+数据记录，优先显示录像+数据时长
        # 2. 如果有单独的录像记录，显示录像时长
        # 3. 如果有单独的数据记录，显示数据记录时长
        # 4. 最后才显示数据监测时长
        
        main_display_set = False  # 标记是否已设置主要显示内容
        
        # 更新录像+数据时间（最高优先级）
        if combined_status and combined_start_time:
            elapsed = current_time - combined_start_time
            elapsed_str = self.format_elapsed_time(elapsed)
            self.combined_time_label.config(text=f"延时录像+数据时长: {elapsed_str}", fg="lightgreen")
            # 同时更新数据监测显示为记录时长
            self.monitoring_time_label.config(text=f"记录时长: {elapsed_str}", fg="lightgreen")
            main_display_set = True
        else:
            self.combined_time_label.config(text="延时录像+数据时长: 未开始", fg="gray")
        
        # 更新录像时间（第二优先级）
        if recording_status and recording_start_time:
            elapsed = current_time - recording_start_time
            elapsed_str = self.format_elapsed_time(elapsed)
            self.recording_time_label.config(text=f"延时录像时长: {elapsed_str}", fg="orange")
            # 如果没有更高优先级的记录，则显示录像时长
            if not main_display_set:
                self.monitoring_time_label.config(text=f"录像时长: {elapsed_str}", fg="orange")
                main_display_set = True
        else:
            self.recording_time_label.config(text="延时录像时长: 未开始", fg="gray")
        
        # 更新数据记录时间（第三优先级）
        if data_recording_status and data_recording_start_time:
            elapsed = current_time - data_recording_start_time
            elapsed_str = self.format_elapsed_time(elapsed)
            self.data_recording_time_label.config(text=f"数据记录时长: {elapsed_str}", fg="lightblue")
            # 如果没有更高优先级的记录，则显示数据记录时长
            if not main_display_set:
                self.monitoring_time_label.config(text=f"数据记录时长: {elapsed_str}", fg="lightblue")
                main_display_set = True
        else:
            self.data_recording_time_label.config(text="数据记录时长: 未开始", fg="gray")
        
        # 更新数据监测时间（最低优先级）
        if not main_display_set:
            if monitoring_status and monitoring_start_time:
                elapsed = current_time - monitoring_start_time
                elapsed_str = self.format_elapsed_time(elapsed)
                self.monitoring_time_label.config(text=f"数据监测时长: {elapsed_str}", fg="darkgreen")
            else:
                self.monitoring_time_label.config(text="数据监测时长: 未开始", fg="gray")
    
    def format_elapsed_time(self, elapsed):
        """格式化时间显示"""
        total_seconds = int(elapsed.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    def start_background_threads(self):
        """启动后台线程"""
        # 启动连接到发送端的线程
        connect_thread = threading.Thread(target=connect_to_sender, daemon=True)
        connect_thread.start()
        
        # 设置图像服务器
        server_socket = setup_image_server()
        if server_socket:
            # 启动图像连接处理线程
            image_handler = threading.Thread(target=handle_image_connection, 
                                           args=(server_socket,), daemon=True)
            image_handler.start()
        else:
            self.log_message("无法启动图像服务器")
    
    def on_closing(self):
        """处理窗口关闭事件"""
        global running
        if messagebox.askokcancel("退出", "确定要退出程序吗？"):
            self.log_message("用户请求退出程序...")
            self.send_command("quit")
            running = False
            self.root.quit()
            self.root.destroy()

# GUI实例
gui = None

def connect_to_sender():
    """连接到发送端的指令接口，不停重试直到连接成功"""
    global command_socket, command_connected, gui, last_runtime_status
    
    while running:
        if not command_connected:
            try:
                if gui:
                    gui.log_message(f"正在尝试连接发送端指令接口 {SENDER_IP}:{COMMAND_PORT}...")
                command_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                command_socket.settimeout(5)  # 设置连接超时
                
                # 优化TCP参数以提高传输性能
                try:
                    command_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024*1024)  # 1MB接收缓冲区
                    command_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)  # 启用keepalive
                    # TCP_NODELAY在某些系统上可能不可用
                    try:
                        command_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # 禁用Nagle算法
                        tcp_optimized = True
                    except:
                        tcp_optimized = False
                except:
                    tcp_optimized = False
                
                command_socket.connect((SENDER_IP, COMMAND_PORT))
                command_connected = True
                if gui:
                    gui.log_message(f"已成功连接到发送端指令接口 {SENDER_IP}:{COMMAND_PORT}")
                    if tcp_optimized:
                        gui.log_message("TCP参数已优化: 1MB缓冲区, Keepalive, 无延迟")
                    else:
                        gui.log_message("TCP基础连接已建立")
                
                # 连接成功后，清空运行状态以便GUI及时更新
                last_runtime_status = ""
                
                # 监听状态消息
                status_thread = threading.Thread(target=listen_status, daemon=True)
                status_thread.start()
                
            except Exception as e:
                if gui:
                    gui.log_message(f"连接发送端失败: {e}，3秒后重试...")
                command_connected = False
                if command_socket:
                    try:
                        command_socket.close()
                    except:
                        pass
                    command_socket = None
                time.sleep(3)
        else:
            time.sleep(1)  # 已连接时等待1秒再检查

def listen_status():
    """监听发送端的状态消息"""
    global command_socket, command_connected, last_runtime_status, last_gpio_data, last_temp_humidity, gui
    buffer = b''
    
    while running and command_socket and command_connected:
        try:
            data = command_socket.recv(1024)
            if not data:
                if gui:
                    gui.log_message("发送端断开连接，将尝试重新连接...")
                command_connected = False
                break
                
            buffer += data
            while b'\n' in buffer:
                line_end = buffer.find(b'\n')
                message = buffer[:line_end].decode('utf-8').strip()
                buffer = buffer[line_end+1:]
                
                # 尝试解析JSON格式的消息
                try:
                    msg_obj = json.loads(message)
                    if msg_obj.get("type") == "FILE_DATA":
                        # 处理文件数据
                        process_file_data(msg_obj)
                    else:
                        process_structured_message(msg_obj)
                except json.JSONDecodeError:
                    # 处理旧格式的消息
                    process_legacy_message(message)
                    
        except Exception as e:
            if running and gui:
                gui.log_message(f"状态监听错误: {e}，连接断开，将尝试重新连接...")
            command_connected = False
            break
    
    # 连接断开，设置状态
    if running and not command_connected:
        if command_socket:
            try:
                command_socket.close()
            except:
                pass
            command_socket = None

def process_file_data(msg_obj):
    """处理文件数据 - 优化版本with校验"""
    global gui
    if not gui or not gui.current_download:
        return
    
    try:
        data_hex = msg_obj.get("data", "")
        chunk_id = msg_obj.get("chunk_id", 0)
        chunk_md5 = msg_obj.get("chunk_md5", "")
        
        # 将十六进制转换为字节
        data_bytes = bytes.fromhex(data_hex)
        
        # 校验数据块完整性
        if chunk_md5:
            actual_md5 = hashlib.md5(data_bytes).hexdigest()
            if actual_md5 != chunk_md5:
                gui.log_message(f"警告: 数据块 {chunk_id} 校验失败")
                return
        
        # 存储已接收的数据块
        gui.received_chunks[chunk_id] = data_bytes
        
        # 更新接收的字节数
        gui.current_download["bytes_received"] += len(data_bytes)
        
        # 累积数据到缓冲区（按顺序）
        gui.download_buffer += data_bytes
        
    except Exception as e:
        if gui:
            gui.log_message(f"处理文件数据错误: {e}")

def process_structured_message(msg_obj):
    """处理结构化的JSON消息"""
    global last_runtime_status, last_gpio_data, last_temp_humidity, gui, latest_sensor_data
    global monitoring_status, recording_status, data_recording_status, combined_status
    global monitoring_start_time, recording_start_time, data_recording_start_time, combined_start_time
    
    msg_type = msg_obj.get("type", "")
    timestamp = msg_obj.get("timestamp", "")
    data = msg_obj.get("data", {})
    
    if msg_type == MessageType.RUNTIME_STATUS:
        # 运行时状态信息 - 也包含传感器数据，更新latest_sensor_data
        latest_sensor_data = data
        
        recording = data.get("recording", "未知")
        data_recording = data.get("data_recording", "未知")
        combined = data.get("combined", "未知")
        i2c_available = data.get("i2c_available", False)
        
        i2c_str = "可用" if i2c_available else "不可用"
        
        last_runtime_status = f"录像:{recording}, 数据记录:{data_recording}, 录像+数据:{combined}, I2C:{i2c_str}"
        
    elif msg_type == MessageType.GPIO_DATA:
        # GPIO数据信息（现在包含传感器数据）- 更新latest_sensor_data
        latest_sensor_data = data
        
        adc_data = data.get("adc_data", {})
        env_data = data.get("env_data", {})
        
        voltage = adc_data.get("channel0_voltage", 0) if adc_data else 0
        current = adc_data.get("channel1_current", 0) if adc_data else 0
        temperature = env_data.get("temperature") if env_data else None
        humidity = env_data.get("humidity") if env_data else None
        
        temp_str = f"{temperature:.1f}°C" if temperature is not None else "N/A"
        hum_str = f"{humidity:.1f}%" if humidity is not None else "N/A"
        
        last_gpio_data = f"电压:{voltage:.2f}V, 电流:{current:.2f}A, 温度:{temp_str}, 湿度:{hum_str}"
        
    elif msg_type == MessageType.STATUS:
        # 处理状态变更消息，同步按钮状态
        status_data = data
        current_time = datetime.datetime.now()
        
        if status_data == "DATA_MONITORING_STARTED":
            if not monitoring_status:
                monitoring_status = True
                monitoring_start_time = current_time
                if gui:
                    gui.monitoring_btn.config(text="停止数据监测", bg="lightgreen")
        elif status_data == "DATA_MONITORING_STOPPED":
            if monitoring_status:
                monitoring_status = False
                monitoring_start_time = None
                if gui:
                    gui.monitoring_btn.config(text="开启数据监测", bg="SystemButtonFace")
        elif status_data == "TIMELAPSE_RECORDING_STARTED":
            if not recording_status:
                recording_status = True
                recording_start_time = current_time
                if gui:
                    gui.recording_btn.config(text="停止录像", bg="orange")
        elif status_data == "TIMELAPSE_RECORDING_STOPPED":
            if recording_status:
                recording_status = False
                recording_start_time = None
                if gui:
                    gui.recording_btn.config(text="开启录像", bg="SystemButtonFace")
        elif status_data == "GPIO_MONITORING_STARTED":
            if not data_recording_status:
                data_recording_status = True
                data_recording_start_time = current_time
                if gui:
                    gui.data_recording_btn.config(text="停止数据记录", bg="lightblue")
        elif status_data == "GPIO_MONITORING_STOPPED":
            if data_recording_status:
                data_recording_status = False
                data_recording_start_time = None
                if gui:
                    gui.data_recording_btn.config(text="开启数据记录", bg="SystemButtonFace")
        elif status_data == "TIMELAPSE_RECORDING_AND_GPIO_STARTED":
            if not combined_status:
                combined_status = True
                combined_start_time = current_time
                if gui:
                    gui.combined_btn.config(text="停止录像+数据", bg="lightgreen")
        elif status_data == "TIMELAPSE_RECORDING_AND_GPIO_STOPPED":
            if combined_status:
                combined_status = False
                combined_start_time = None
                if gui:
                    gui.combined_btn.config(text="录像+数据", bg="SystemButtonFace")
        
        # 一般状态信息
        if gui:
            gui.log_message(f"[状态] {status_data}")
        
    elif msg_type == MessageType.TEMP_HUMIDITY:
        # 温湿度数据
        temperature = data.get("temperature")
        humidity = data.get("humidity")
        temp_str = f"{temperature:.1f}°C" if temperature is not None else "N/A"
        hum_str = f"{humidity:.1f}%" if humidity is not None else "N/A"
        last_temp_humidity = f"温度:{temp_str}, 湿度:{hum_str}"
    
    elif msg_type == MessageType.FILE_LIST:
        # 文件列表信息
        gui.file_list = data.get("files", [])
        current_dir = data.get("current_dir", "")
        if gui.file_transfer_window and gui.file_tree:
            # 更新文件列表显示
            gui.update_file_list_display()
        if gui:
            gui.log_message(f"收到文件列表，共 {len(gui.file_list)} 个文件，目录: {current_dir}")
    
    elif msg_type == MessageType.FILE_TRANSFER:
        # 文件传输状态
        status = data.get("status", "")
        if status == "start":
            filename = data.get("filename", "")
            size = data.get("size", 0)
            md5_hash = data.get("md5", "")
            if gui.current_download:
                gui.current_download["total_size"] = size
                gui.download_buffer = b''
                gui.expected_md5 = md5_hash
                gui.received_chunks = {}
            if gui:
                gui.log_message(f"开始接收文件: {filename} ({size} 字节, MD5: {md5_hash[:8]}...)")
        elif status == "progress":
            if gui.current_download:
                bytes_sent = data.get("bytes_sent", 0)
                total_size = data.get("total_size", 0)
                progress = data.get("progress", 0)
                speed_mbps = data.get("speed_mbps", None)
                chunk_count = data.get("chunk_count", 0)
                gui.update_download_progress(bytes_sent, total_size, progress, speed_mbps)
        elif status == "complete":
            filename = data.get("filename", "")
            transfer_time = data.get("transfer_time", 0)
            avg_speed = data.get("avg_speed_mbps", 0)
            chunk_count = data.get("chunk_count", 0)
            if gui.current_download and gui.download_buffer:
                gui.save_downloaded_file()
            if gui:
                gui.log_message(f"文件接收完成: {filename} (用时: {transfer_time}s, 平均速度: {avg_speed}MB/s, 数据块: {chunk_count})")
                gui.start_download()  # 下载下一个文件
        elif status == "error":
            message = data.get("message", "未知错误")
            if gui:
                gui.log_message(f"文件传输错误: {message}")
                messagebox.showerror("传输错误", message)

def process_legacy_message(message):
    """处理旧格式的消息（兼容性）"""
    global last_runtime_status, gui
    
    if message.startswith("STATUS:"):
        status = message.split(":", 1)[1]
        if status.startswith("RUNTIME_STATUS:"):
            # 运行时状态信息
            runtime_info = status.split(":", 1)[1]
            last_runtime_status = runtime_info
        else:
            # 其他状态信息
            if gui:
                gui.log_message(f"[状态] {status}")
    elif message == "SENDER_READY":
        if gui:
            gui.log_message("[状态] 发送端已准备就绪")

def save_image(data):
    """保存图像文件，使用日期格式命名"""
    current_time = datetime.datetime.now()
    filename = f'img_{current_time.strftime("%Y%m%d_%H%M%S")}.jpg'
    with open(filename, 'wb') as f:
        f.write(data)
    if gui:
        gui.log_message(f"图像保存为: {filename}")
    return filename

def setup_image_server():
    """设置图像服务器，不停重试直到绑定成功"""
    global image_connected, gui
    
    retry_count = 0
    while running and not image_connected and retry_count < 5:
        try:
            if gui:
                gui.log_message(f"正在设置图像服务器，监听端口: {IMAGE_PORT}...")
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((IMAGE_HOST, IMAGE_PORT))
            server_socket.listen(1)
            image_connected = True
            if gui:
                gui.log_message(f"图像服务器已启动，监听端口: {IMAGE_PORT}")
            return server_socket
        except Exception as e:
            if gui:
                gui.log_message(f"图像服务器启动失败: {e}，3秒后重试...")
            try:
                server_socket.close()
            except:
                pass
            time.sleep(3)
            retry_count += 1
    
    return None

def handle_image_connection(server_socket):
    """处理图像连接的函数"""
    global running, gui
    conn = None
    
    while running:
        try:
            if gui:
                gui.log_message("等待发送端连接图像服务器...")
            conn, addr = server_socket.accept()
            if gui:
                gui.log_message(f"发送端已连接: {addr}")
            
            buffer = b''
            while running:
                try:
                    data = conn.recv(4096)
                    if not data:
                        if gui:
                            gui.log_message("图像连接断开，等待重新连接...")
                        break
                    buffer += data

                    while b'\n' in buffer:
                        line_end = buffer.find(b'\n')
                        line = buffer[:line_end].decode()
                        buffer = buffer[line_end+1:]

                        if line.startswith("IMG_START:"):
                            size = int(line.split(":")[1])
                            if gui:
                                gui.log_message(f"准备接收图像，共 {size} 字节")
                            image_data = b''
                            while len(image_data) < size and running:
                                chunk = conn.recv(size - len(image_data))
                                if not chunk:
                                    break
                                image_data += chunk
                            if running and len(image_data) == size:
                                save_image(image_data)
                        elif line == "IMG_END":
                            if gui:
                                gui.log_message("图像接收完成")
                
                except Exception as e:
                    if running and gui:
                        gui.log_message(f"接收图像数据时出错: {e}，连接断开，等待重新连接...")
                    break
            
            # 关闭当前连接
            if conn:
                try:
                    conn.close()
                except:
                    pass
                conn = None
                
        except Exception as e:
            if running and gui:
                gui.log_message(f"图像服务器接受连接时出错: {e}")
                time.sleep(1)

def main():
    global gui
    
    # 创建并启动GUI
    root = tk.Tk()
    gui = WiFiReceiverGUI(root)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\n用户中断程序...")
    finally:
        global running
        running = False
        
        # 清理资源
        if command_socket:
            try:
                command_socket.close()
            except:
                pass

if __name__ == "__main__":
    main()
