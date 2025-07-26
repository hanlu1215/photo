# -*- coding: utf-8 -*-
import cv2
import socket
import threading
import time
import sys
import csv
import os
import re
import json
import hashlib
from datetime import datetime
try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    print("警告: 未找到RPi.GPIO库，GPIO监测功能将无法使用")

try:
    import board
    import adafruit_dht
    I2C_AVAILABLE = True
    # 初始化DHT22传感器 (可以改为DHT11)
    dht = adafruit_dht.DHT22(board.D4)  # GPIO4引脚连接DHT22
    print("I2C温湿度传感器初始化成功")
except ImportError:
    I2C_AVAILABLE = False
    print("警告: 未找到adafruit-circuitpython-dht库，温湿度传感器功能将无法使用")
except Exception as e:
    I2C_AVAILABLE = False
    print(f"警告: 温湿度传感器初始化失败: {e}")

# ==== 摄像头初始化 ====
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("无法打开摄像头")
    sys.exit()

# 尝试设置摄像头为最大分辨率（根据摄像头硬件决定是否有效）
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"摄像头分辨率: {frame_width}x{frame_height}")

# ==== 视频保存配置 ====
# 录像相关变量
recording = False
video_writer = None
current_fps = 30
recording_start_time = None
last_record_frame_time = 0  # 上次录制帧的时间
record_interval = 1.0  # 录制间隔（秒）

# GPIO监测配置
GPIO_PIN = 18  # 可根据需要修改
gpio_monitoring = False
csv_file = None
csv_writer = None

# 温湿度传感器数据
last_temperature = None
last_humidity = None
sensor_error_count = 0

# 消息结构体定义
class MessageType:
    STATUS = "STATUS"
    RUNTIME_STATUS = "RUNTIME_STATUS"
    GPIO_DATA = "GPIO_DATA"
    TEMP_HUMIDITY = "TEMP_HUMIDITY"
    SYSTEM_INFO = "SYSTEM_INFO"
    FILE_LIST = "FILE_LIST"
    FILE_TRANSFER = "FILE_TRANSFER"

def create_message(msg_type, data):
    """创建统一格式的消息"""
    return {
        "type": msg_type,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "data": data
    }

def read_temperature_humidity():
    """读取温湿度传感器数据"""
    global last_temperature, last_humidity, sensor_error_count
    
    if not I2C_AVAILABLE:
        return None, None
        
    try:
        temperature = dht.temperature
        humidity = dht.humidity
        if temperature is not None and humidity is not None:
            last_temperature = temperature
            last_humidity = humidity
            sensor_error_count = 0
            return temperature, humidity
        else:
            sensor_error_count += 1
            return last_temperature, last_humidity
    except Exception as e:
        sensor_error_count += 1
        if sensor_error_count % 10 == 0:  # 每10次错误打印一次
            print(f"温湿度传感器读取错误: {e}")
        return last_temperature, last_humidity

def get_file_list():
    """获取当前工作目录下的文件列表"""
    try:
        current_dir = os.getcwd()
        files = []
        for item in os.listdir(current_dir):
            full_path = os.path.join(current_dir, item)
            if os.path.isfile(full_path):
                file_size = os.path.getsize(full_path)
                file_info = {
                    "name": item,
                    "size": file_size,
                    "size_mb": round(file_size / (1024 * 1024), 2),
                    "modified": datetime.fromtimestamp(os.path.getmtime(full_path)).strftime('%Y-%m-%d %H:%M:%S')
                }
                files.append(file_info)
        return files
    except Exception as e:
        print(f"获取文件列表失败: {e}")
        return []

def send_file_data(filename):
    """发送文件数据 - 优化版本"""
    global command_conn
    if not command_conn:
        return False
    
    try:
        if not os.path.exists(filename):
            error_msg = create_message(MessageType.FILE_TRANSFER, {
                "status": "error",
                "message": f"文件不存在: {filename}"
            })
            send_status_message(error_msg)
            return False
        
        file_size = os.path.getsize(filename)
        
        # 计算文件MD5校验值
        print(f"正在计算文件校验值: {filename}")
        file_md5 = calculate_file_md5(filename)
        
        # 发送文件开始信息（包含MD5）
        start_msg = create_message(MessageType.FILE_TRANSFER, {
            "status": "start",
            "filename": filename,
            "size": file_size,
            "md5": file_md5
        })
        send_status_message(start_msg)
        
        # 优化传输参数
        chunk_size = 65536  # 64KB per chunk (大幅增加块大小)
        bytes_sent = 0
        chunk_count = 0
        start_time = time.time()
        
        # 设置socket缓冲区大小
        try:
            command_conn.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024*1024)  # 1MB发送缓冲区
        except:
            pass
        
        print(f"开始传输文件: {filename} ({file_size} 字节)")
        
        with open(filename, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                
                chunk_count += 1
                
                # 计算当前块的MD5
                chunk_md5 = hashlib.md5(chunk).hexdigest()
                
                # 发送数据块（带校验）
                chunk_msg = {
                    "type": "FILE_DATA",
                    "data": chunk.hex(),  # 转换为十六进制字符串
                    "chunk_id": chunk_count,
                    "chunk_md5": chunk_md5,
                    "bytes_sent": bytes_sent,
                    "total_size": file_size
                }
                json_msg = json.dumps(chunk_msg, ensure_ascii=False)
                
                # 分段发送大数据包，避免TCP缓冲区溢出
                msg_bytes = f"{json_msg}\n".encode('utf-8')
                sent = 0
                while sent < len(msg_bytes):
                    try:
                        n = command_conn.send(msg_bytes[sent:])
                        if n == 0:
                            raise ConnectionError("连接断开")
                        sent += n
                    except Exception as e:
                        print(f"发送数据块失败: {e}")
                        return False
                
                bytes_sent += len(chunk)
                
                # 每传输1MB或每50个块报告一次进度
                if chunk_count % 50 == 0 or bytes_sent >= file_size:
                    progress = (bytes_sent / file_size) * 100
                    elapsed = time.time() - start_time
                    speed_mbps = (bytes_sent / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                    
                    progress_msg = create_message(MessageType.FILE_TRANSFER, {
                        "status": "progress",
                        "filename": filename,
                        "bytes_sent": bytes_sent,
                        "total_size": file_size,
                        "progress": round(progress, 1),
                        "speed_mbps": round(speed_mbps, 2),
                        "chunk_count": chunk_count
                    })
                    send_status_message(progress_msg)
                    
                    print(f"传输进度: {progress:.1f}% ({speed_mbps:.2f} MB/s)")
                
                # 减少延时，提高传输速度
                if chunk_count % 100 == 0:  # 每100个块稍微延时一下
                    time.sleep(0.001)
        
        # 发送完成信息
        elapsed_total = time.time() - start_time
        avg_speed = (file_size / (1024 * 1024)) / elapsed_total if elapsed_total > 0 else 0
        
        complete_msg = create_message(MessageType.FILE_TRANSFER, {
            "status": "complete",
            "filename": filename,
            "size": file_size,
            "md5": file_md5,
            "chunk_count": chunk_count,
            "transfer_time": round(elapsed_total, 2),
            "avg_speed_mbps": round(avg_speed, 2)
        })
        send_status_message(complete_msg)
        
        print(f"文件发送完成: {filename} ({file_size} 字节)")
        print(f"传输时间: {elapsed_total:.2f}秒, 平均速度: {avg_speed:.2f} MB/s")
        return True
        
    except Exception as e:
        error_msg = create_message(MessageType.FILE_TRANSFER, {
            "status": "error",
            "message": f"发送文件失败: {e}"
        })
        send_status_message(error_msg)
        print(f"发送文件失败: {e}")
        return False

def calculate_file_md5(filename):
    """计算文件的MD5校验值"""
    try:
        hash_md5 = hashlib.md5()
        with open(filename, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"计算MD5失败: {e}")
        return ""

# ==== TCP连接配置 ====
# 作为图像发送端
IMAGE_SERVER_IP = '192.168.1.116'   # 替换为图像接收端的实际IP
IMAGE_SERVER_PORT = 8888

# 作为指令接收端
COMMAND_PORT = 8889

# 连接状态标志
image_connected = False
command_connected = False
image_client_socket = None
command_server_socket = None

# ==== 通信控制 ====
latest_frame = None
exit_flag = False
send_flag = False
command_conn = None

# GPIO初始化
if GPIO_AVAILABLE:
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(GPIO_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        print(f"GPIO初始化成功，监控引脚: {GPIO_PIN}")
    except Exception as e:
        print(f"GPIO初始化失败: {e}")
        print("提示: GPIO功能将被禁用，其他功能正常运行")
        print("如需使用GPIO功能，请检查用户权限或运行 'sudo usermod -a -G gpio $USER' 添加用户到gpio组")
        GPIO_AVAILABLE = False

def add_timestamp_watermark(frame):
    """在图像右上角添加时间水印"""
    # 先旋转图像180度
    frame = cv2.rotate(frame, cv2.ROTATE_180)
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.7
    color = (255, 255, 255)  # 白色
    thickness = 2
    
    # 计算文本大小
    (text_width, text_height), baseline = cv2.getTextSize(timestamp, font, font_scale, thickness)
    
    # 在右上角位置添加文本
    x = frame.shape[1] - text_width - 10
    y = text_height + 10
    
    # 添加黑色背景使文字更清晰
    cv2.rectangle(frame, (x-5, y-text_height-5), (x+text_width+5, y+baseline+5), (0, 0, 0), -1)
    cv2.putText(frame, timestamp, (x, y), font, font_scale, color, thickness)
    
    return frame

def start_recording(fps=30):
    """开始录像（延时录像模式，每隔1秒录制一帧）"""
    global recording, video_writer, current_fps, recording_start_time, last_record_frame_time
    
    if recording:
        print("已在录像中")
        return
    
    current_fps = fps
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'timelapse_recording_{timestamp}.avi'
    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    video_writer = cv2.VideoWriter(filename, fourcc, fps, (frame_width, frame_height))
    
    if not video_writer.isOpened():
        print("录像器初始化失败")
        return
    
    recording = True
    recording_start_time = datetime.now()
    last_record_frame_time = 0  # 重置帧记录时间
    print(f"[延时录像] 开始延时录像: {filename}, 播放FPS: {fps}")
    print(f"[延时录像] 录制模式: 每1秒录制1帧")
    print(f"[延时录像] GPIO监测状态: {'监测中' if gpio_monitoring else '未监测'}")
    print(f"[延时录像] 录像和GPIO监测可以同时进行")

def stop_recording():
    """停止录像"""
    global recording, video_writer, recording_start_time, last_record_frame_time
    
    if not recording:
        print("当前未在录像")
        return
    
    recording = False
    if video_writer:
        video_writer.release()
        video_writer = None
    
    duration = datetime.now() - recording_start_time
    recorded_frames = int(duration.total_seconds())  # 按1秒1帧计算
    print(f"[延时录像] 延时录像已保存，录像时长: {duration.total_seconds():.1f}秒")
    print(f"[延时录像] 预计录制帧数: {recorded_frames}帧")
    print(f"[延时录像] GPIO监测状态: {'监测中' if gpio_monitoring else '未监测'}")
    last_record_frame_time = 0  # 重置帧记录时间

def start_gpio_monitoring():
    """开始GPIO监测"""
    global gpio_monitoring, csv_file, csv_writer
    
    if not GPIO_AVAILABLE:
        print("GPIO库不可用，无法开始监测")
        return
    
    if gpio_monitoring:
        print("GPIO监测已在运行")
        return
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_filename = f'gpio_log_{timestamp}.csv'
    csv_file = open(csv_filename, 'w', newline='')
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow(['时间', '电平状态', '录像状态', '温度(°C)', '湿度(%)'])
    
    gpio_monitoring = True
    print(f"[GPIO监测] 开始监测引脚{GPIO_PIN}，保存到: {csv_filename}")
    print(f"[GPIO监测] 当前录像状态: {'录像中' if recording else '未录像'}")
    print(f"[GPIO监测] GPIO监测和录像可以同时进行")
    print(f"[GPIO监测] 温湿度传感器状态: {'可用' if I2C_AVAILABLE else '不可用'}")

def stop_gpio_monitoring():
    """停止GPIO监测"""
    global gpio_monitoring, csv_file, csv_writer
    
    if not gpio_monitoring:
        print("GPIO监测未在运行")
        return
    
    gpio_monitoring = False
    if csv_file:
        csv_file.close()
        csv_file = None
        csv_writer = None
    
    print("[GPIO监测] GPIO监测已停止")
    print(f"[GPIO监测] 当前录像状态: {'录像中' if recording else '未录像'}")

def runtime_status_thread():
    """运行时状态输出线程，每秒输出一次状态"""
    last_status_time = 0
    
    while not exit_flag:
        current_time = time.time()
        
        # 每秒输出一次状态
        if current_time - last_status_time >= 1.0:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # 获取GPIO状态
            gpio_status = "未知"
            if GPIO_AVAILABLE and gpio_monitoring:
                try:
                    pin_state = GPIO.input(GPIO_PIN)
                    gpio_status = "高" if pin_state else "低"
                except:
                    gpio_status = "错误"
            elif not GPIO_AVAILABLE:
                gpio_status = "不可用"
            elif not gpio_monitoring:
                gpio_status = "未监测"
            
            # 获取温湿度数据
            temperature, humidity = read_temperature_humidity()
            
            # 构建状态信息
            recording_status = "延时录像中" if recording else "否"
            gpio_monitor_status = "是" if gpio_monitoring else "否"
            
            # 创建运行状态消息
            status_data = {
                "recording": recording_status,
                "gpio_monitoring": gpio_monitor_status,
                "gpio_status": gpio_status,
                "temperature": temperature,
                "humidity": humidity,
                "i2c_available": I2C_AVAILABLE
            }
            
            status_msg = create_message(MessageType.RUNTIME_STATUS, status_data)
            send_status_message(status_msg)
            
            # 本地输出状态
            temp_str = f"{temperature:.1f}°C" if temperature is not None else "N/A"
            hum_str = f"{humidity:.1f}%" if humidity is not None else "N/A"
            print(f"[运行状态] {timestamp} - 录像:{recording_status}, GPIO监测:{gpio_monitor_status}, GPIO状态:{gpio_status}, 温度:{temp_str}, 湿度:{hum_str}")
            
            last_status_time = current_time
        
        time.sleep(0.1)  # 每100毫秒检查一次

def gpio_monitoring_thread():
    """GPIO监测线程"""
    global gpio_monitoring, csv_writer
    last_record_time = 0
    
    while not exit_flag:
        if gpio_monitoring and GPIO_AVAILABLE and csv_writer:
            try:
                current_time = time.time()
                pin_state = GPIO.input(GPIO_PIN)
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                state_text = "高" if pin_state else "低"
                
                # 获取温湿度数据
                temperature, humidity = read_temperature_humidity()
                
                # 每秒记录一次数据到CSV文件
                if current_time - last_record_time >= 1.0:
                    temp_str = f"{temperature:.1f}" if temperature is not None else "N/A"
                    hum_str = f"{humidity:.1f}" if humidity is not None else "N/A"
                    csv_writer.writerow([timestamp, state_text, '延时录像中' if recording else '未录像', temp_str, hum_str])
                    csv_file.flush()  # 确保数据写入文件
                    
                    # 发送GPIO和温湿度数据
                    gpio_temp_data = {
                        "gpio_pin": GPIO_PIN,
                        "gpio_state": state_text,
                        "recording": recording,
                        "temperature": temperature,
                        "humidity": humidity
                    }
                    gpio_msg = create_message(MessageType.GPIO_DATA, gpio_temp_data)
                    send_status_message(gpio_msg)
                    
                    last_record_time = current_time
                
            except Exception as e:
                print(f"GPIO读取错误: {e}")
                print("停止GPIO监测以避免重复错误")
                gpio_monitoring = False
                break
        
        time.sleep(0.1)  # 每100毫秒检查一次，提高响应速度

def connect_to_image_server():
    """连接到图像服务器，不停重试直到连接成功"""
    global image_client_socket, image_connected
    
    while not exit_flag:
        if not image_connected:
            try:
                print(f"正在尝试连接图像服务器 {IMAGE_SERVER_IP}:{IMAGE_SERVER_PORT}...")
                image_client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                image_client_socket.settimeout(5)  # 设置连接超时
                image_client_socket.connect((IMAGE_SERVER_IP, IMAGE_SERVER_PORT))
                image_connected = True
                print(f"已成功连接图像服务器 {IMAGE_SERVER_IP}:{IMAGE_SERVER_PORT}")
            except Exception as e:
                print(f"连接图像服务器失败: {e}，3秒后重试...")
                image_connected = False
                if image_client_socket:
                    try:
                        image_client_socket.close()
                    except:
                        pass
                    image_client_socket = None
                time.sleep(3)
        else:
            time.sleep(1)  # 已连接时等待1秒再检查

def setup_command_server():
    """设置指令接收服务器，不停重试直到绑定成功"""
    global command_server_socket, command_connected
    
    while not exit_flag:
        if not command_connected:
            try:
                print(f"正在设置指令服务器，监听端口: {COMMAND_PORT}...")
                command_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                command_server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                command_server_socket.bind(('0.0.0.0', COMMAND_PORT))
                command_server_socket.listen(1)
                command_connected = True
                print(f"指令服务器已启动，监听端口: {COMMAND_PORT}")
            except Exception as e:
                print(f"指令服务器启动失败: {e}，3秒后重试...")
                command_connected = False
                if command_server_socket:
                    try:
                        command_server_socket.close()
                    except:
                        pass
                    command_server_socket = None
                time.sleep(3)
        else:
            time.sleep(1)  # 已启动时等待1秒再检查

def send_image(image):
    global image_client_socket, image_connected
    
    if not image_connected or not image_client_socket:
        print("图像服务器未连接，无法发送图像")
        return False
    
    # 使用相同的处理流程：旋转图像并添加时间水印
    processed_image = add_timestamp_watermark(image.copy())
        
    ret, buffer = cv2.imencode('.jpg', processed_image)
    if not ret:
        print("图像编码失败")
        return False

    data = buffer.tobytes()
    size = len(data)
    print(f"发送图像，大小: {size} 字节")

    try:
        image_client_socket.sendall(f"IMG_START:{size}\n".encode())
        image_client_socket.sendall(data)
        image_client_socket.sendall(b"IMG_END\n")
        print("图像发送完成")
        return True
    except Exception as e:
        print(f"发送图像失败: {e}，连接已断开，将尝试重新连接")
        image_connected = False
        if image_client_socket:
            try:
                image_client_socket.close()
            except:
                pass
            image_client_socket = None
        return False

def command_listener_thread():
    """监听网络指令的线程"""
    global exit_flag, send_flag, command_conn, command_server_socket
    
    while not exit_flag:
        if not command_connected:
            time.sleep(1)
            continue
            
        try:
            print("等待指令连接...")
            command_conn, addr = command_server_socket.accept()
            print(f"指令连接来自: {addr}")
            
            # 发送状态信息到接收端
            try:
                command_conn.sendall("SENDER_READY\n".encode())
            except:
                print("发送就绪信息失败")
                continue
            
            buffer = b''
            while not exit_flag:
                try:
                    data = command_conn.recv(1024)
                    if not data:
                        print("指令连接断开，等待重新连接...")
                        break
                    
                    buffer += data
                    while b'\n' in buffer:
                        line_end = buffer.find(b'\n')
                        command = buffer[:line_end].decode().strip()
                        buffer = buffer[line_end+1:]
                        
                        print(f"收到指令: {command}")
                        process_command(command)
                        
                except Exception as e:
                    if not exit_flag:
                        print(f"指令接收错误: {e}，连接断开，等待重新连接...")
                    break
                    
        except Exception as e:
            if not exit_flag:
                print(f"指令服务器错误: {e}，等待重新连接...")
                time.sleep(1)
        finally:
            if command_conn:
                try:
                    command_conn.close()
                except:
                    pass
                command_conn = None

def process_command(command):
    """处理接收到的指令"""
    global exit_flag, send_flag
    
    cmd = command.lower()
    
    if cmd == 'quit':
        print("收到退出指令")
        exit_flag = True
    elif cmd == 's':
        print("收到发送图像指令")
        send_flag = True
    elif cmd.startswith('rcb'):
        # 同时开启录像和GPIO监测
        fps = 30  # 默认FPS
        if len(cmd) > 3:
            try:
                fps_str = cmd[3:]
                fps = int(fps_str)
                if fps <= 0 or fps > 120:
                    fps = 30
            except ValueError:
                fps = 30
        start_recording(fps)
        start_gpio_monitoring()
        status_msg = create_message(MessageType.STATUS, "TIMELAPSE_RECORDING_AND_GPIO_STARTED")
        send_status_message(status_msg)
    elif cmd == 'rcs':
        # 同时停止录像和GPIO监测
        stop_recording()
        stop_gpio_monitoring()
        status_msg = create_message(MessageType.STATUS, "TIMELAPSE_RECORDING_AND_GPIO_STOPPED")
        send_status_message(status_msg)
    elif cmd.startswith('rb'):
        # 仅开启录像
        fps = 30  # 默认FPS
        if len(cmd) > 2:
            try:
                fps_str = cmd[2:]
                fps = int(fps_str)
                if fps <= 0 or fps > 120:
                    fps = 30
            except ValueError:
                fps = 30
        start_recording(fps)
        status_msg = create_message(MessageType.STATUS, "TIMELAPSE_RECORDING_STARTED")
        send_status_message(status_msg)
    elif cmd == 'rs':
        # 停止录像
        stop_recording()
        status_msg = create_message(MessageType.STATUS, "TIMELAPSE_RECORDING_STOPPED")
        send_status_message(status_msg)
    elif cmd == 'cb':
        # 仅开启GPIO监测
        start_gpio_monitoring()
        status_msg = create_message(MessageType.STATUS, "GPIO_MONITORING_STARTED")
        send_status_message(status_msg)
    elif cmd == 'cs':
        # 停止GPIO监测
        stop_gpio_monitoring()
        status_msg = create_message(MessageType.STATUS, "GPIO_MONITORING_STOPPED")
        send_status_message(status_msg)
    elif cmd == 'list_files':
        # 获取文件列表
        files = get_file_list()
        file_list_msg = create_message(MessageType.FILE_LIST, {
            "files": files,
            "current_dir": os.getcwd()
        })
        send_status_message(file_list_msg)
        print(f"已发送文件列表，共 {len(files)} 个文件")
    elif cmd.startswith('download_file:'):
        # 下载文件
        filename = cmd.split(':', 1)[1].strip()
        print(f"开始发送文件: {filename}")
        send_file_data(filename)
    else:
        print(f"未知指令: {command}")
        status_msg = create_message(MessageType.STATUS, "UNKNOWN_COMMAND")
        send_status_message(status_msg)

def send_status_message(message):
    """发送统一格式的状态消息到指令发送端"""
    global command_conn
    if command_conn:
        try:
            json_msg = json.dumps(message, ensure_ascii=False)
            command_conn.sendall(f"{json_msg}\n".encode('utf-8'))
        except Exception as e:
            print(f"发送状态失败: {e}，指令连接可能已断开")

def send_status(status):
    """发送状态信息到指令发送端 (兼容旧版本)"""
    status_msg = create_message(MessageType.STATUS, status)
    send_status_message(status_msg)

# 启动GPIO监测线程
gpio_thread = threading.Thread(target=gpio_monitoring_thread, daemon=True)
gpio_thread.start()

# 启动运行时状态监控线程
status_thread = threading.Thread(target=runtime_status_thread, daemon=True)
status_thread.start()

# 启动连接线程
print("正在启动连接服务...")
connect_thread = threading.Thread(target=connect_to_image_server, daemon=True)
connect_thread.start()

setup_thread = threading.Thread(target=setup_command_server, daemon=True)
setup_thread.start()

# 启动指令监听线程
command_thread = threading.Thread(target=command_listener_thread, daemon=True)
command_thread.start()

print("系统运行中...")
print("等待与接收端建立连接...")

while not exit_flag:
    ret, frame = cap.read()
    if not ret:
        print("摄像头帧获取失败，退出")
        break
    
    latest_frame = frame.copy()
    
    # 如果正在录像，检查是否到了录制时间间隔
    if recording and video_writer:
        current_time = time.time()
        if current_time - last_record_frame_time >= record_interval:
            frame_with_watermark = add_timestamp_watermark(frame.copy())
            video_writer.write(frame_with_watermark)
            last_record_frame_time = current_time
            # 输出录制信息
            elapsed_time = datetime.now() - recording_start_time
            frame_count = int(elapsed_time.total_seconds())
            print(f"[延时录像] 录制第 {frame_count} 帧 - 已录制时长: {elapsed_time.total_seconds():.1f}秒")
    
    # 发送图像
    if send_flag:
        if image_connected:
            success = send_image(latest_frame)
            if not success:
                print("图像发送失败，连接将自动重试")
                # 连接线程会自动重试，不需要手动启动新线程
        else:
            print("图像服务器未连接，无法发送图像，连接重试中...")
        send_flag = False
    
    # 添加短暂延时避免CPU占用过高
    time.sleep(0.01)

# 清理资源
print("正在清理资源...")

# 停止录像
if recording:
    stop_recording()

# 停止GPIO监测
if gpio_monitoring:
    stop_gpio_monitoring()

# 清理GPIO
if GPIO_AVAILABLE:
    try:
        GPIO.cleanup()
        print("GPIO资源已释放")
    except Exception as e:
        print(f"GPIO清理时出现错误: {e}")

cap.release()
if image_client_socket:
    image_client_socket.close()
if command_server_socket:
    command_server_socket.close()
if command_conn:
    command_conn.close()
print("程序退出，资源释放完成")
