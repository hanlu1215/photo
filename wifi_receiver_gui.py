# -*- coding: utf-8 -*-
import socket
import os
import datetime
import threading
import sys
import time
import json
import tkinter as tk
from tkinter import ttk, scrolledtext
from tkinter import messagebox

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
data_recording_status = False
combined_status = False

# 记录时间相关变量
monitoring_start_time = None
data_recording_start_time = None
combined_start_time = None

# 消息类型定义
class MessageType:
    STATUS = "STATUS"
    RUNTIME_STATUS = "RUNTIME_STATUS"
    GPIO_DATA = "GPIO_DATA"
    TEMP_HUMIDITY = "TEMP_HUMIDITY"
    SYSTEM_INFO = "SYSTEM_INFO"

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
        
        # 停止发送端按钮
        self.stop_sender_btn = tk.Button(row2_frame, text="停止发送端", 
                                       command=self.stop_sender,
                                       width=15, height=2, font=("Arial", 10),
                                       bg="orange", fg="white")
        self.stop_sender_btn.pack(side="left", padx=5)
        
        # 退出GUI按钮
        self.quit_btn = tk.Button(row2_frame, text="退出GUI", 
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
    
    def stop_sender(self):
        """停止发送端程序"""
        if messagebox.askokcancel("停止发送端", "确定要停止发送端程序吗？"):
            self.send_command("quit")
            self.log_message("已发送停止指令给发送端")
    
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
        global latest_sensor_data, monitoring_status, data_recording_status, combined_status
        
        # 检查是否应该显示数据（数据监测、数据记录或录像+数据模式下）
        should_display_data = monitoring_status or data_recording_status or combined_status
        
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
        global monitoring_status, data_recording_status, combined_status
        global monitoring_start_time, data_recording_start_time, combined_start_time
        
        current_time = datetime.datetime.now()
        
        # 优先显示记录时长逻辑：
        # 1. 如果有录像+数据记录，优先显示录像+数据时长
        # 2. 如果有单独的数据记录，显示数据记录时长
        # 3. 最后才显示数据监测时长
        
        main_display_set = False  # 标记是否已设置主要显示内容
        
        # 更新录像+数据时间（最高优先级）
        if combined_status and combined_start_time:
            elapsed = current_time - combined_start_time
            elapsed_str = self.format_elapsed_time(elapsed)
            self.combined_time_label.config(text=f"录像+数据时长: {elapsed_str}", fg="lightgreen")
            # 同时更新数据监测显示为记录时长
            self.monitoring_time_label.config(text=f"录像+数据时长: {elapsed_str}", fg="lightgreen")
            main_display_set = True
        else:
            self.combined_time_label.config(text="录像+数据时长: 未开始", fg="gray")
        
        # 更新数据记录时间（第二优先级）
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
        if messagebox.askokcancel("退出", "确定要退出GUI程序吗？"):
            self.log_message("用户请求退出GUI程序...")
            # 只退出GUI，不向发送端发送退出指令
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
                
                # 重置状态变量，准备从发送端同步最新状态
                global monitoring_status, data_recording_status, combined_status
                global monitoring_start_time, data_recording_start_time, combined_start_time
                monitoring_status = False
                data_recording_status = False
                combined_status = False
                monitoring_start_time = None
                data_recording_start_time = None
                combined_start_time = None
                
                # 监听状态消息
                status_thread = threading.Thread(target=listen_status, daemon=True)
                status_thread.start()
                
                # 请求发送端当前状态更新
                if gui:
                    gui.log_message("正在同步发送端状态...")
                    # 给发送端一点时间建立连接，然后请求状态同步
                    def request_status_sync():
                        time.sleep(1)  # 等待1秒确保连接稳定
                        if command_connected and command_socket:
                            try:
                                # 请求状态同步（发送端会发送当前状态）
                                command_socket.sendall("sync_status\n".encode())
                            except:
                                pass
                    
                    sync_thread = threading.Thread(target=request_status_sync, daemon=True)
                    sync_thread.start()
                
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

def process_structured_message(msg_obj):
    """处理结构化的JSON消息"""
    global last_runtime_status, last_gpio_data, last_temp_humidity, gui, latest_sensor_data
    global monitoring_status, data_recording_status, combined_status
    global monitoring_start_time, data_recording_start_time, combined_start_time
    
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
        
        last_runtime_status = f"数据记录:{data_recording}, 录像+数据:{combined}, I2C:{i2c_str}"
        
        # 根据运行时状态同步GUI按钮状态
        current_time = datetime.datetime.now()
        
        # 同步数据记录状态
        if data_recording == "是" and not data_recording_status:
            data_recording_status = True
            if not data_recording_start_time:
                data_recording_start_time = current_time
            if gui:
                gui.data_recording_btn.config(text="停止数据记录", bg="lightblue")
                gui.log_message("[状态同步] 检测到正在记录数据，已同步按钮状态")
        elif data_recording == "否" and data_recording_status:
            data_recording_status = False
            data_recording_start_time = None
            if gui:
                gui.data_recording_btn.config(text="开启数据记录", bg="SystemButtonFace")
        
        # 同步录像+数据状态
        if combined == "是" and not combined_status:
            combined_status = True
            if not combined_start_time:
                combined_start_time = current_time
            if gui:
                gui.combined_btn.config(text="停止录像+数据", bg="lightgreen")
                gui.log_message("[状态同步] 检测到正在录像+数据记录，已同步按钮状态")
        elif combined == "否" and combined_status:
            combined_status = False
            combined_start_time = None
            if gui:
                gui.combined_btn.config(text="录像+数据", bg="SystemButtonFace")
        
        # 同步数据监测状态（如果有任何数据记录在进行，通常数据监测也是开启的）
        should_monitor = (data_recording == "是" or combined == "是")
        if should_monitor and not monitoring_status:
            monitoring_status = True
            if not monitoring_start_time:
                monitoring_start_time = current_time
            if gui:
                gui.monitoring_btn.config(text="停止数据监测", bg="lightgreen")
                gui.log_message("[状态同步] 检测到数据监测已开启，已同步按钮状态")
        
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
        
        # 在状态同步时，不更新开始时间，保持原有的记录时间连续性
        preserve_time = False
        if isinstance(status_data, str) and status_data.endswith("_SYNC"):
            preserve_time = True
            status_data = status_data.replace("_SYNC", "")
        
        if status_data == "DATA_MONITORING_STARTED":
            if not monitoring_status:
                monitoring_status = True
                if not preserve_time or not monitoring_start_time:
                    monitoring_start_time = current_time
                if gui:
                    gui.monitoring_btn.config(text="停止数据监测", bg="lightgreen")
        elif status_data == "DATA_MONITORING_STOPPED":
            if monitoring_status:
                monitoring_status = False
                if not preserve_time:
                    monitoring_start_time = None
                if gui:
                    gui.monitoring_btn.config(text="开启数据监测", bg="SystemButtonFace")
        elif status_data == "GPIO_MONITORING_STARTED":
            if not data_recording_status:
                data_recording_status = True
                if not preserve_time or not data_recording_start_time:
                    data_recording_start_time = current_time
                if gui:
                    gui.data_recording_btn.config(text="停止数据记录", bg="lightblue")
        elif status_data == "GPIO_MONITORING_STOPPED":
            if data_recording_status:
                data_recording_status = False
                if not preserve_time:
                    data_recording_start_time = None
                if gui:
                    gui.data_recording_btn.config(text="开启数据记录", bg="SystemButtonFace")
        elif status_data == "TIMELAPSE_RECORDING_AND_GPIO_STARTED":
            if not combined_status:
                combined_status = True
                if not preserve_time or not combined_start_time:
                    combined_start_time = current_time
                if gui:
                    gui.combined_btn.config(text="停止录像+数据", bg="lightgreen")
        elif status_data == "TIMELAPSE_RECORDING_AND_GPIO_STOPPED":
            if combined_status:
                combined_status = False
                if not preserve_time:
                    combined_start_time = None
                if gui:
                    gui.combined_btn.config(text="录像+数据", bg="SystemButtonFace")
        
        # 一般状态信息
        if gui and not preserve_time:  # 同步状态时不显示日志，避免重复信息
            gui.log_message(f"[状态] {status_data}")
        elif gui and preserve_time:
            gui.log_message(f"[状态同步] 已恢复状态: {status_data}")
        
    elif msg_type == MessageType.TEMP_HUMIDITY:
        # 温湿度数据
        temperature = data.get("temperature")
        humidity = data.get("humidity")
        temp_str = f"{temperature:.1f}°C" if temperature is not None else "N/A"
        hum_str = f"{humidity:.1f}%" if humidity is not None else "N/A"
        last_temp_humidity = f"温度:{temp_str}, 湿度:{hum_str}"

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
