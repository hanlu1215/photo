# -*- coding: utf-8 -*-
"""
WiFi 传感器数据发送端 - 集成ADC数据读取、图像采集和WiFi传输
功能：
1. 读取ADS1115 ADC数据和环境传感器数据
2. 摄像头图像采集
3. WiFi数据传输和远程控制
4. 数据和图像保存
"""

import socket
import threading
import time
import json
import datetime
import os
import sys
import hashlib
import csv
import io

# 传感器相关导入
try:
    import Adafruit_ADS1x15
    import smbus
    ADS_AVAILABLE = True
except ImportError:
    print("警告: ADS1x15或smbus模块不可用，传感器功能将被禁用")
    ADS_AVAILABLE = False

# 摄像头相关导入
try:
    import cv2
    CAMERA_AVAILABLE = True
    CAMERA_TYPE = "opencv"
    print("使用OpenCV摄像头驱动")
except ImportError:
    try:
        import picamera
        import picamera.array
        CAMERA_AVAILABLE = True
        CAMERA_TYPE = "picamera"
        print("使用PiCamera摄像头驱动")
    except ImportError:
        print("警告: 摄像头模块不可用，摄像头功能将被禁用")
        CAMERA_AVAILABLE = False
        CAMERA_TYPE = None

# 网络配置
COMMAND_HOST = '0.0.0.0'
COMMAND_PORT = 8889
IMAGE_HOST = '192.168.1.116'  # 接收端IP
IMAGE_PORT = 8888

# ADC配置参数
GAIN = 1
MAX_ADC_VALUE = 32767
ADC_VOLTAGE_RANGE = 4.096  # V
VOLTAGE_SCALE = 60.0 / 3.3  # 实际电压范围 / 测量电压范围
CURRENT_SCALE = 120.0 / 3.3  # 实际电流范围 / 测量电压范围

# 环境传感器配置
ENV_SENSOR_ADDR = 0x5B

# 系统状态
class SystemState:
    def __init__(self):
        self.running = True
        self.data_monitoring = False  # 数据监测状态
        self.data_recording = False   # 数据记录状态
        self.image_recording = False  # 图像录制状态
        self.combined_recording = False  # 录像+数据状态
        
        # 时间间隔设置
        self.data_interval = 0.1  # 数据监测间隔（秒）
        self.image_interval = 10.0  # 图像记录间隔（秒）
        self.last_image_time = 0  # 上次图像记录时间戳
        
        # 数据保存相关
        self.data_save_thread = None
        self.image_save_thread = None
        self.current_result_folder = None
        self.csv_file = None
        self.csv_writer = None
        
        # 网络连接
        self.command_socket = None
        self.image_socket = None
        self.client_connected = False
        
        # 最新数据
        self.latest_sensor_data = None
        self.latest_image_data = None

# 全局状态实例
state = SystemState()

# 传感器管理类
class SensorManager:
    def __init__(self):
        self.adc = None
        self.i2c_bus = None
        self.i2c_available = False
        self.initialize_sensors()
    
    def initialize_sensors(self):
        """初始化传感器"""
        if not ADS_AVAILABLE:
            print("ADC功能不可用")
            return
        
        try:
            # 初始化ADS1115
            self.adc = Adafruit_ADS1x15.ADS1115(busnum=1)
            print("ADS1115初始化成功")
            
            # 初始化I2C环境传感器
            self.i2c_bus = smbus.SMBus(1)
            self.i2c_available = True
            print("I2C环境传感器初始化成功")
            
        except Exception as e:
            print(f"传感器初始化失败: {e}")
            try:
                self.adc = Adafruit_ADS1x15.ADS1115()
                self.i2c_bus = smbus.SMBus(1)
                self.i2c_available = True
                print("使用默认参数初始化传感器成功")
            except Exception as e2:
                print(f"传感器完全初始化失败: {e2}")
                self.i2c_available = False
    
    def adc_to_voltage_reading(self, adc_value):
        """将ADC原始值转换为电压读数(V)"""
        if adc_value < 0:
            return 0.0
        voltage_reading = (adc_value / MAX_ADC_VALUE) * ADC_VOLTAGE_RANGE
        return min(voltage_reading, 3.3)
    
    def convert_to_actual_voltage(self, adc_value):
        """将ADC值转换为实际电压(0-60V)"""
        voltage_reading = self.adc_to_voltage_reading(adc_value)
        return voltage_reading * VOLTAGE_SCALE
    
    def convert_to_actual_current(self, adc_value):
        """将ADC值转换为实际电流(0-120A)"""
        voltage_reading = self.adc_to_voltage_reading(adc_value)
        return voltage_reading * CURRENT_SCALE
    
    def read_adc_data(self):
        """读取ADC数据"""
        if not self.adc:
            return None
        
        try:
            values = [0] * 4
            for i in range(4):
                values[i] = self.adc.read_adc(i, gain=GAIN)
            
            # 转换数据
            voltage = self.convert_to_actual_voltage(values[0])
            current = self.convert_to_actual_current(values[1])
            voltage_ch2 = self.adc_to_voltage_reading(values[2])
            voltage_ch3 = self.adc_to_voltage_reading(values[3])
            
            return {
                'channel0_voltage': voltage,
                'channel1_current': current,
                'channel2_voltage': voltage_ch2,
                'channel3_voltage': voltage_ch3,
                'raw_values': values
            }
        except Exception as e:
            print(f"ADC读取错误: {e}")
            return None
    
    def read_env_sensor_data(self):
        """读取环境传感器数据"""
        if not self.i2c_available or not self.i2c_bus:
            return None
        
        try:
            # 读取光照强度数据
            lux_data = []
            for i in range(4):
                lux_data.append(self.i2c_bus.read_byte_data(ENV_SENSOR_ADDR, 0x00 + i))
            
            # 读取BME传感器数据
            bme_data = []
            for i in range(10):
                bme_data.append(self.i2c_bus.read_byte_data(ENV_SENSOR_ADDR, 0x04 + i))
            
            # 解析光照强度
            if lux_data[0] == 0x80:
                lux_raw = (lux_data[1] << 16) | (lux_data[2] << 8) | lux_data[3]
            else:
                data_16_0 = (lux_data[0] << 8) | lux_data[1]
                data_16_1 = (lux_data[2] << 8) | lux_data[3]
                lux_raw = (data_16_0 << 16) | data_16_1
            
            lux = min(lux_raw / 100.0, 100000) if lux_raw <= 1000000 else 0
            
            # 解析温度、气压、湿度、海拔
            temperature = ((bme_data[0] << 8) | bme_data[1]) / 100.0
            pressure_16_0 = (bme_data[2] << 8) | bme_data[3]
            pressure_16_1 = (bme_data[4] << 8) | bme_data[5]
            pressure = ((pressure_16_0 << 16) | pressure_16_1) / 100.0
            humidity = ((bme_data[6] << 8) | bme_data[7]) / 100.0
            altitude = (bme_data[8] << 8) | bme_data[9]
            
            return {
                'lux': lux,
                'temperature': temperature,
                'pressure': pressure,
                'humidity': humidity,
                'altitude': altitude
            }
        except Exception as e:
            print(f"环境传感器读取错误: {e}")
            return None
    
    def read_all_sensor_data(self):
        """读取所有传感器数据"""
        timestamp = datetime.datetime.now()
        
        # 读取ADC数据
        adc_data = self.read_adc_data()
        
        # 读取环境数据
        env_data = self.read_env_sensor_data()
        
        # 组合数据
        combined_data = {
            'timestamp': timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            'adc_data': adc_data,
            'env_data': env_data
        }
        
        return combined_data

# 摄像头管理类
class CameraManager:
    def __init__(self):
        self.camera = None
        self.camera_available = False
        self.camera_type = CAMERA_TYPE
        self.initialize_camera()
    
    def initialize_camera(self):
        """初始化摄像头"""
        if not CAMERA_AVAILABLE:
            print("摄像头功能不可用：无可用的摄像头模块")
            return
        
        if self.camera_type == "opencv":
            self._initialize_opencv_camera()
        elif self.camera_type == "picamera":
            self._initialize_picamera()
    
    def _initialize_opencv_camera(self):
        """初始化OpenCV摄像头"""
        try:
            print("正在初始化OpenCV摄像头...")
            
            # 尝试不同的摄像头索引
            for camera_index in [0, 1, 2]:
                print(f"尝试摄像头索引: {camera_index}")
                self.camera = cv2.VideoCapture(camera_index)
                
                if self.camera.isOpened():
                    # 设置摄像头参数
                    self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1024)
                    self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 768)
                    self.camera.set(cv2.CAP_PROP_FPS, 30)
                    
                    # 测试捕获
                    ret, test_frame = self.camera.read()
                    if ret and test_frame is not None:
                        print(f"OpenCV摄像头初始化成功，索引: {camera_index}")
                        print(f"分辨率: {test_frame.shape[1]}x{test_frame.shape[0]}")
                        self.camera_available = True
                        return
                    else:
                        self.camera.release()
                        self.camera = None
                else:
                    if self.camera:
                        self.camera.release()
                        self.camera = None
            
            print("所有摄像头索引都无法工作")
            self.camera_available = False
            
        except Exception as e:
            print(f"OpenCV摄像头初始化失败: {e}")
            print(f"错误类型: {type(e).__name__}")
            self.camera_available = False
            if self.camera:
                self.camera.release()
                self.camera = None
    
    def _initialize_picamera(self):
        """初始化PiCamera摄像头"""
        try:
            print("正在初始化PiCamera摄像头...")
            self.camera = picamera.PiCamera()
            self.camera.resolution = (1024, 768)
            self.camera.rotation = 0
            
            # 设置摄像头参数
            self.camera.framerate = 30
            self.camera.brightness = 50
            self.camera.contrast = 0
            
            print("摄像头预热中...")
            time.sleep(3)  # 延长预热时间
            
            # 测试捕获以确保摄像头工作正常
            test_stream = io.BytesIO()
            self.camera.capture(test_stream, format='jpeg')
            test_data = test_stream.getvalue()
            test_stream.close()
            
            if len(test_data) > 0:
                self.camera_available = True
                print(f"PiCamera摄像头初始化成功，测试图像大小: {len(test_data)} 字节")
            else:
                print("PiCamera摄像头测试失败：捕获的图像为空")
                self.camera_available = False
                
        except Exception as e:
            print(f"PiCamera摄像头初始化失败: {e}")
            print(f"错误类型: {type(e).__name__}")
            self.camera_available = False
            if self.camera:
                try:
                    self.camera.close()
                    self.camera = None
                except:
                    pass
    
    def capture_image(self):
        """捕获图像"""
        if not self.camera_available or not self.camera:
            print("摄像头不可用，无法捕获图像")
            return None
        
        if self.camera_type == "opencv":
            return self._capture_opencv_image()
        elif self.camera_type == "picamera":
            return self._capture_picamera_image()
        
        return None
    
    def _capture_opencv_image(self):
        """使用OpenCV捕获图像"""
        try:
            # 捕获帧
            ret, frame = self.camera.read()
            
            if not ret or frame is None:
                print("OpenCV图像捕获失败：无法读取帧")
                return None
            
            # 上下翻转图像
            frame = cv2.flip(frame, 0)  # 0表示垂直翻转（上下翻转）
            
            # 添加时间水印在右上角
            current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 设置字体参数
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.7
            color = (255, 255, 255)  # 白色
            thickness = 2
            
            # 获取文本尺寸以便定位在右上角
            text_size = cv2.getTextSize(current_time, font, font_scale, thickness)[0]
            text_x = frame.shape[1] - text_size[0] - 10  # 距离右边缘10像素
            text_y = text_size[1] + 10  # 距离顶部10像素
            
            # 添加黑色背景矩形，提高文字可读性
            cv2.rectangle(frame, 
                         (text_x - 5, text_y - text_size[1] - 5), 
                         (text_x + text_size[0] + 5, text_y + 5), 
                         (0, 0, 0), -1)  # 黑色填充矩形
            
            # 在图像上添加时间文字
            cv2.putText(frame, current_time, (text_x, text_y), font, font_scale, color, thickness)
            
            # 将帧编码为JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
            ret, buffer = cv2.imencode('.jpg', frame, encode_param)
            
            if not ret:
                print("OpenCV图像编码失败")
                return None
            
            image_data = buffer.tobytes()
            
            if len(image_data) > 0:
                print(f"OpenCV图像捕获成功（已翻转并添加时间水印），大小: {len(image_data)} 字节")
                return image_data
            else:
                print("OpenCV图像捕获失败：编码数据为空")
                return None
                
        except Exception as e:
            print(f"OpenCV图像捕获错误: {e}")
            print(f"错误类型: {type(e).__name__}")
            
            # 尝试重新初始化摄像头
            print("尝试重新初始化OpenCV摄像头...")
            self.cleanup()
            time.sleep(1)
            self.initialize_camera()
            
            return None
    
    def _capture_picamera_image(self):
        """使用PiCamera捕获图像"""
        try:
            # 使用内存流
            stream = io.BytesIO()
            
            # 添加一个小延迟确保摄像头准备就绪
            time.sleep(0.1)
            
            # 捕获图像
            self.camera.capture(stream, format='jpeg', quality=85, use_video_port=True)
            stream.seek(0)
            image_data = stream.getvalue()
            stream.close()
            
            if len(image_data) == 0:
                print("PiCamera图像捕获失败：数据为空")
                return None
            
            # 如果系统支持OpenCV且需要添加水印和翻转，则进行后处理
            try:
                import cv2
                import numpy as np
                
                # 将JPEG数据转换为OpenCV图像
                nparr = np.frombuffer(image_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if frame is not None:
                    # 上下翻转图像
                    frame = cv2.flip(frame, 0)  # 0表示垂直翻转（上下翻转）
                    
                    # 添加时间水印在右上角
                    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 设置字体参数
                    font = cv2.FONT_HERSHEY_SIMPLEX
                    font_scale = 0.7
                    color = (255, 255, 255)  # 白色
                    thickness = 2
                    
                    # 获取文本尺寸以便定位在右上角
                    text_size = cv2.getTextSize(current_time, font, font_scale, thickness)[0]
                    text_x = frame.shape[1] - text_size[0] - 10  # 距离右边缘10像素
                    text_y = text_size[1] + 10  # 距离顶部10像素
                    
                    # 添加黑色背景矩形，提高文字可读性
                    cv2.rectangle(frame, 
                                 (text_x - 5, text_y - text_size[1] - 5), 
                                 (text_x + text_size[0] + 5, text_y + 5), 
                                 (0, 0, 0), -1)  # 黑色填充矩形
                    
                    # 在图像上添加时间文字
                    cv2.putText(frame, current_time, (text_x, text_y), font, font_scale, color, thickness)
                    
                    # 重新编码为JPEG
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                    ret, buffer = cv2.imencode('.jpg', frame, encode_param)
                    
                    if ret:
                        image_data = buffer.tobytes()
                        print(f"PiCamera图像捕获成功（已翻转并添加时间水印），大小: {len(image_data)} 字节")
                    else:
                        print(f"PiCamera图像后处理编码失败，使用原始图像，大小: {len(image_data)} 字节")
                else:
                    print(f"PiCamera图像后处理失败，使用原始图像，大小: {len(image_data)} 字节")
                    
            except ImportError:
                # 如果没有OpenCV，只能使用原始图像
                print(f"PiCamera图像捕获成功（无OpenCV后处理），大小: {len(image_data)} 字节")
            except Exception as post_error:
                print(f"PiCamera图像后处理错误: {post_error}，使用原始图像")
            
            return image_data
                
        except Exception as e:
            print(f"PiCamera图像捕获错误: {e}")
            print(f"错误类型: {type(e).__name__}")
            
            # 尝试重新初始化摄像头
            print("尝试重新初始化PiCamera摄像头...")
            self.cleanup()
            time.sleep(1)
            self.initialize_camera()
            
            return None
    
    def cleanup(self):
        """清理摄像头资源"""
        if self.camera:
            try:
                print("正在关闭摄像头...")
                if self.camera_type == "opencv":
                    self.camera.release()
                elif self.camera_type == "picamera":
                    self.camera.close()
                
                self.camera = None
                self.camera_available = False
                print("摄像头已关闭")
            except Exception as e:
                print(f"关闭摄像头时出错: {e}")
        else:
            print("摄像头已经关闭")

# 数据保存管理类
class DataSaveManager:
    def __init__(self):
        pass
    
    def create_result_folder(self):
        """创建结果文件夹"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"result_{timestamp}"
        
        if not os.path.exists(folder_name):
            os.makedirs(folder_name)
        
        return folder_name
    
    def initialize_csv_file(self, folder_path):
        """初始化CSV文件"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"data_{timestamp}.csv"
        csv_path = os.path.join(folder_path, csv_filename)
        
        csv_file = open(csv_path, 'w', newline='', encoding='utf-8')
        csv_writer = csv.writer(csv_file)
        
        # 写入CSV头部
        headers = [
            'timestamp', 'voltage_ch0', 'current_ch1', 'voltage_ch2', 'voltage_ch3',
            'raw_ch0', 'raw_ch1', 'raw_ch2', 'raw_ch3',
            'lux', 'temperature', 'pressure', 'humidity', 'altitude'
        ]
        csv_writer.writerow(headers)
        csv_file.flush()
        
        return csv_file, csv_writer
    
    def save_sensor_data_to_csv(self, csv_writer, csv_file, sensor_data):
        """保存传感器数据到CSV"""
        if not sensor_data:
            return
        
        try:
            adc_data = sensor_data.get('adc_data', {}) or {}
            env_data = sensor_data.get('env_data', {}) or {}
            
            row = [
                sensor_data['timestamp'],
                adc_data.get('channel0_voltage', 0),
                adc_data.get('channel1_current', 0),
                adc_data.get('channel2_voltage', 0),
                adc_data.get('channel3_voltage', 0),
                adc_data.get('raw_values', [0,0,0,0])[0] if adc_data.get('raw_values') else 0,
                adc_data.get('raw_values', [0,0,0,0])[1] if adc_data.get('raw_values') else 0,
                adc_data.get('raw_values', [0,0,0,0])[2] if adc_data.get('raw_values') else 0,
                adc_data.get('raw_values', [0,0,0,0])[3] if adc_data.get('raw_values') else 0,
                env_data.get('lux', 0),
                env_data.get('temperature', 0),
                env_data.get('pressure', 0),
                env_data.get('humidity', 0),
                env_data.get('altitude', 0)
            ]
            csv_writer.writerow(row)
            csv_file.flush()
        except Exception as e:
            print(f"保存CSV数据错误: {e}")
    
    def save_image_to_file(self, folder_path, image_data):
        """保存图像到文件"""
        if not image_data:
            return None
        
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"img_{timestamp}.jpg"
            filepath = os.path.join(folder_path, filename)
            
            with open(filepath, 'wb') as f:
                f.write(image_data)
            
            return filename
        except Exception as e:
            print(f"保存图像错误: {e}")
            return None

# 网络通信管理类
class NetworkManager:
    def __init__(self):
        pass
    
    def send_message(self, socket_obj, message_type, data):
        """发送结构化消息"""
        try:
            message = {
                "type": message_type,
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data": data
            }
            json_message = json.dumps(message, ensure_ascii=False)
            socket_obj.sendall(f"{json_message}\n".encode('utf-8'))
            return True
        except Exception as e:
            print(f"发送消息错误: {e}")
            return False
    
    def send_image_data(self, image_data):
        """发送图像数据"""
        if not state.image_socket or not image_data:
            return False
        
        try:
            # 发送图像头部信息
            header = f"IMG_START:{len(image_data)}\n"
            state.image_socket.sendall(header.encode())
            
            # 发送图像数据
            state.image_socket.sendall(image_data)
            
            # 发送结束标记
            state.image_socket.sendall(b"IMG_END\n")
            return True
        except Exception as e:
            print(f"发送图像错误: {e}")
            return False

# 初始化全局管理器
sensor_manager = SensorManager()
camera_manager = CameraManager()
data_save_manager = DataSaveManager()
network_manager = NetworkManager()

def data_monitoring_loop():
    """数据监测主循环"""
    print("数据监测线程启动")
    
    while state.running:
        if state.data_monitoring:
            try:
                current_time = time.time()
                
                # 读取传感器数据（每0.1秒）
                sensor_data = sensor_manager.read_all_sensor_data()
                state.latest_sensor_data = sensor_data
                
                # 发送运行时状态
                if state.command_socket and state.client_connected:
                    runtime_data = {
                        "recording": "是" if state.image_recording else "否",
                        "data_recording": "是" if state.data_recording else "否",
                        "combined": "是" if state.combined_recording else "否",
                        "temperature": sensor_data['env_data']['temperature'] if sensor_data.get('env_data') else None,
                        "humidity": sensor_data['env_data']['humidity'] if sensor_data.get('env_data') else None,
                        "i2c_available": sensor_manager.i2c_available,
                        # 添加完整的传感器数据
                        "adc_data": sensor_data.get('adc_data', {}),
                        "env_data": sensor_data.get('env_data', {}),
                        # 添加图像记录间隔信息
                        "image_interval": state.image_interval
                    }
                    network_manager.send_message(state.command_socket, "RUNTIME_STATUS", runtime_data)
                
                # 如果正在记录数据，保存到CSV（每0.1秒）
                if state.data_recording and state.csv_writer and state.csv_file:
                    data_save_manager.save_sensor_data_to_csv(state.csv_writer, state.csv_file, sensor_data)
                
                # 读取图像（仅在录像模式下，按设定间隔）
                if state.image_recording:
                    # 检查是否到了图像记录时间
                    if current_time - state.last_image_time >= state.image_interval:
                        print(f"图像记录间隔: {state.image_interval}秒，开始捕获图像...")
                        image_data = camera_manager.capture_image()
                        state.latest_image_data = image_data
                        state.last_image_time = current_time
                        
                        # 保存图像
                        if image_data and state.current_result_folder:
                            filename = data_save_manager.save_image_to_file(state.current_result_folder, image_data)
                            if filename:
                                print(f"图像已保存: {filename}")
                
            except Exception as e:
                print(f"数据监测错误: {e}")
        
        time.sleep(state.data_interval)  # 使用配置的数据间隔

def setup_command_server():
    """设置指令服务器"""
    while state.running:
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((COMMAND_HOST, COMMAND_PORT))
            server_socket.listen(1)
            print(f"指令服务器启动，监听端口: {COMMAND_PORT}")
            
            while state.running:
                try:
                    client_socket, address = server_socket.accept()
                    print(f"客户端连接: {address}")
                    state.command_socket = client_socket
                    state.client_connected = True
                    
                    # 处理客户端命令
                    handle_client_commands(client_socket)
                    
                except Exception as e:
                    print(f"客户端连接错误: {e}")
                    state.client_connected = False
                    if state.command_socket:
                        try:
                            state.command_socket.close()
                        except:
                            pass
                        state.command_socket = None
            
        except Exception as e:
            print(f"指令服务器错误: {e}")
            time.sleep(3)

def handle_client_commands(client_socket):
    """处理客户端指令"""
    buffer = b''
    
    while state.running and state.client_connected:
        try:
            data = client_socket.recv(1024)
            if not data:
                print("客户端断开连接")
                break
            
            buffer += data
            while b'\n' in buffer:
                line_end = buffer.find(b'\n')
                command = buffer[:line_end].decode('utf-8').strip()
                buffer = buffer[line_end+1:]
                
                print(f"收到指令: {command}")
                process_command(command)
                
        except Exception as e:
            print(f"处理客户端指令错误: {e}")
            break
    
    state.client_connected = False

def process_command(command):
    """处理具体指令"""
    try:
        if command == "start_monitoring":
            # 开启数据监测
            state.data_monitoring = True
            network_manager.send_message(state.command_socket, "STATUS", "DATA_MONITORING_STARTED")
            print("开启数据监测")
            
        elif command == "stop_monitoring":
            # 停止数据监测
            state.data_monitoring = False
            network_manager.send_message(state.command_socket, "STATUS", "DATA_MONITORING_STOPPED")
            print("停止数据监测")
            
        elif command == "cb":
            # 开启数据记录
            start_data_recording()
            
        elif command == "cs":
            # 停止数据记录
            stop_data_recording()
            
        elif command == "rb":
            # 开启图像录制
            start_image_recording()
            
        elif command == "rs":
            # 停止图像录制
            stop_image_recording()
            
        elif command == "rcb":
            # 开启录像+数据
            start_combined_recording()
            
        elif command == "rcs":
            # 停止录像+数据
            stop_combined_recording()
            
        elif command == "s":
            # 发送当前图像
            send_current_image()
            
        elif command.startswith("set_image_interval:"):
            # 设置图像记录间隔
            try:
                interval_str = command.split(":", 1)[1]
                interval = float(interval_str)
                if interval >= 0.1:  # 最小间隔0.1秒
                    state.image_interval = interval
                    print(f"图像记录间隔已设置为: {interval}秒")
                    network_manager.send_message(state.command_socket, "STATUS", f"IMAGE_INTERVAL_SET:{interval}")
                else:
                    print("图像记录间隔不能小于0.1秒")
                    network_manager.send_message(state.command_socket, "STATUS", "IMAGE_INTERVAL_ERROR:最小间隔0.1秒")
            except (ValueError, IndexError):
                print("图像记录间隔设置格式错误")
                network_manager.send_message(state.command_socket, "STATUS", "IMAGE_INTERVAL_ERROR:格式错误")
            
        elif command == "get_image_interval":
            # 获取当前图像记录间隔
            network_manager.send_message(state.command_socket, "STATUS", f"CURRENT_IMAGE_INTERVAL:{state.image_interval}")
            print(f"当前图像记录间隔: {state.image_interval}秒")
            
        elif command == "quit":
            # 退出程序
            print("收到退出指令")
            state.running = False
            
    except Exception as e:
        print(f"处理指令错误: {e}")

def start_data_recording():
    """开启数据记录"""
    if state.data_recording:
        return
    
    try:
        # 创建结果文件夹
        state.current_result_folder = data_save_manager.create_result_folder()
        
        # 初始化CSV文件
        state.csv_file, state.csv_writer = data_save_manager.initialize_csv_file(state.current_result_folder)
        
        state.data_recording = True
        print(f"开启数据记录，保存到: {state.current_result_folder}")
        
        # 开启数据监测（如果尚未开启）
        if not state.data_monitoring:
            state.data_monitoring = True
        
        network_manager.send_message(state.command_socket, "STATUS", "GPIO_MONITORING_STARTED")
        
    except Exception as e:
        print(f"开启数据记录错误: {e}")

def stop_data_recording():
    """停止数据记录"""
    if not state.data_recording:
        return
    
    try:
        state.data_recording = False
        
        # 关闭CSV文件
        if state.csv_file:
            state.csv_file.close()
            state.csv_file = None
            state.csv_writer = None
        
        print("停止数据记录")
        network_manager.send_message(state.command_socket, "STATUS", "GPIO_MONITORING_STOPPED")
        
    except Exception as e:
        print(f"停止数据记录错误: {e}")

def start_image_recording():
    """开启图像录制"""
    if state.image_recording:
        return
    
    try:
        # 如果没有结果文件夹，创建一个
        if not state.current_result_folder:
            state.current_result_folder = data_save_manager.create_result_folder()
        
        state.image_recording = True
        state.last_image_time = 0  # 重置时间戳，立即开始第一次记录
        print(f"开启图像录制，保存到: {state.current_result_folder}")
        print(f"图像记录间隔: {state.image_interval}秒")
        
        # 开启数据监测（如果尚未开启）
        if not state.data_monitoring:
            state.data_monitoring = True
        
        network_manager.send_message(state.command_socket, "STATUS", "TIMELAPSE_RECORDING_STARTED")
        
    except Exception as e:
        print(f"开启图像录制错误: {e}")

def stop_image_recording():
    """停止图像录制"""
    if not state.image_recording:
        return
    
    try:
        state.image_recording = False
        print("停止图像录制")
        
        network_manager.send_message(state.command_socket, "STATUS", "TIMELAPSE_RECORDING_STOPPED")
        
    except Exception as e:
        print(f"停止图像录制错误: {e}")

def start_combined_recording():
    """开启录像+数据记录"""
    try:
        # 创建结果文件夹
        state.current_result_folder = data_save_manager.create_result_folder()
        
        # 初始化CSV文件
        state.csv_file, state.csv_writer = data_save_manager.initialize_csv_file(state.current_result_folder)
        
        state.data_recording = True
        state.image_recording = True
        state.combined_recording = True
        state.last_image_time = 0  # 重置时间戳，立即开始第一次记录
        
        # 开启数据监测
        if not state.data_monitoring:
            state.data_monitoring = True
        
        print(f"开启录像+数据记录，保存到: {state.current_result_folder}")
        print(f"数据记录间隔: {state.data_interval}秒")
        print(f"图像记录间隔: {state.image_interval}秒")
        network_manager.send_message(state.command_socket, "STATUS", "TIMELAPSE_RECORDING_AND_GPIO_STARTED")
        
    except Exception as e:
        print(f"开启录像+数据记录错误: {e}")

def stop_combined_recording():
    """停止录像+数据记录"""
    try:
        state.data_recording = False
        state.image_recording = False
        state.combined_recording = False
        
        # 关闭CSV文件
        if state.csv_file:
            state.csv_file.close()
            state.csv_file = None
            state.csv_writer = None
        
        print("停止录像+数据记录")
        network_manager.send_message(state.command_socket, "STATUS", "TIMELAPSE_RECORDING_AND_GPIO_STOPPED")
        
    except Exception as e:
        print(f"停止录像+数据记录错误: {e}")

def send_current_image():
    """发送当前图像"""
    print("=== 开始发送当前图像 ===")
    
    try:
        # 首先检查摄像头状态
        if not camera_manager.camera_available:
            print("错误：摄像头不可用，尝试重新初始化...")
            camera_manager.initialize_camera()
            if not camera_manager.camera_available:
                print("错误：摄像头重新初始化失败")
                return
        
        # 捕获图像
        print("正在捕获图像...")
        image_data = camera_manager.capture_image()
        
        if not image_data:
            print("错误：图像捕获失败，无数据返回")
            return
        
        print(f"图像捕获成功，大小: {len(image_data)} 字节")
        
        # 连接到图像接收端
        if not state.image_socket:
            print(f"正在连接到图像服务器: {IMAGE_HOST}:{IMAGE_PORT}")
            try:
                state.image_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                state.image_socket.settimeout(10)  # 设置连接超时
                state.image_socket.connect((IMAGE_HOST, IMAGE_PORT))
                print(f"成功连接到图像服务器: {IMAGE_HOST}:{IMAGE_PORT}")
            except Exception as conn_error:
                print(f"连接图像服务器失败: {conn_error}")
                if state.image_socket:
                    try:
                        state.image_socket.close()
                    except:
                        pass
                    state.image_socket = None
                return
        
        # 发送图像数据
        print("正在发送图像数据...")
        success = network_manager.send_image_data(image_data)
        
        if success:
            print("✓ 当前图像发送成功")
        else:
            print("✗ 当前图像发送失败")
            
    except Exception as e:
        print(f"发送当前图像错误: {e}")
        print(f"错误类型: {type(e).__name__}")
        
        if state.image_socket:
            try:
                state.image_socket.close()
            except:
                pass
            state.image_socket = None
    
    print("=== 发送当前图像结束 ===\n")

def cleanup():
    """清理资源"""
    print("正在清理资源...")
    
    # 停止所有记录
    stop_data_recording()
    stop_image_recording()
    state.data_monitoring = False
    
    # 关闭网络连接
    if state.command_socket:
        try:
            state.command_socket.close()
        except:
            pass
    
    if state.image_socket:
        try:
            state.image_socket.close()
        except:
            pass
    
    # 清理摄像头
    camera_manager.cleanup()
    
    print("资源清理完成")

def main():
    """主函数"""
    print("=" * 60)
    print("WiFi传感器发送端启动")
    print("=" * 60)
    
    # 显示模块可用性
    print(f"📊 ADC模块可用: {ADS_AVAILABLE}")
    print(f"📷 摄像头模块可用: {CAMERA_AVAILABLE}")
    print(f"🌡️  I2C环境传感器可用: {sensor_manager.i2c_available}")
    
    # 显示时间间隔配置
    print(f"⏱️  时间间隔配置:")
    print(f"   数据记录间隔: {state.data_interval}秒")
    print(f"   图像记录间隔: {state.image_interval}秒")
    
    # 显示摄像头详细状态
    print(f"📷 摄像头硬件状态: {camera_manager.camera_available}")
    if camera_manager.camera_available:
        print("📷 摄像头初始化成功，可以进行图像捕获")
    else:
        print("⚠️  摄像头初始化失败！请检查：")
        print("   1. 摄像头是否正确连接")
        print("   2. 是否已启用摄像头 (sudo raspi-config)")
        print("   3. 是否安装了picamera模块 (pip3 install picamera)")
        print("   4. 摄像头是否被其他程序占用")
    
    print(f"🌐 网络配置:")
    print(f"   指令端口: {COMMAND_PORT}")
    print(f"   图像接收端: {IMAGE_HOST}:{IMAGE_PORT}")
    
    print(f"💡 图像间隔设置指令:")
    print(f"   设置间隔: set_image_interval:<秒数>")
    print(f"   查询间隔: get_image_interval")
    print("=" * 60)
    
    try:
        # 启动数据监测线程
        print("🚀 启动数据监测线程...")
        data_thread = threading.Thread(target=data_monitoring_loop, daemon=True)
        data_thread.start()
        
        # 启动指令服务器
        print("🚀 启动指令服务器...")
        setup_command_server()
        
    except KeyboardInterrupt:
        print("\n⏹️  用户中断程序")
    except Exception as e:
        print(f"❌ 程序错误: {e}")
        print(f"错误类型: {type(e).__name__}")
    finally:
        state.running = False
        cleanup()

if __name__ == "__main__":
    main()
