# WiFi传感器控制系统

这是一个基于WiFi的传感器数据采集和摄像头控制系统，包含发送端（树莓派）和接收端（Windows GUI）。

## 主要功能

### 发送端（wifi_sender.py）
- **传感器数据采集**: 集成了ADS1115 ADC和环境传感器(光照、温度、气压、湿度、海拔)
- **摄像头控制**: 支持图像采集和录像功能
- **数据保存**: 自动创建带时间戳的文件夹，保存CSV数据和JPG图像
- **网络通信**: 通过WiFi接收控制指令，发送数据和图像

### 接收端（wifi_receiver_gui.py）
- **图形化界面**: 直观的控制面板和实时数据显示
- **远程控制**: 
  - 数据监测控制：开启/停止传感器数据读取
  - 录像控制：开启/停止图像采集
  - 数据记录：开启/停止数据保存到CSV
  - 录像+数据：同时进行录像和数据记录
- **实时数据显示**: 
  - ADC数据（4通道电压/电流）
  - 环境传感器数据（光照、温度、气压、湿度、海拔）
  - 运行状态和时长统计
- **文件传输**: 从发送端下载保存的文件

## 数据显示逻辑

### 传感器数据显示规则：
1. **未检测状态**（灰色）: 当所有功能都关闭时显示"未检测"
2. **监测状态**（彩色）: 当以下任一功能开启时显示实时数据：
   - 数据监测
   - 录像
   - 数据记录  
   - 录像+数据

### 数据更新频率：
- 传感器数据读取：每100ms
- GUI界面更新：每500ms
- 网络状态检查：实时

## 文件命名规则

### 发送端保存的文件：
- **结果文件夹**: `result_YYYYMMDD_HHMMSS/`
- **CSV数据文件**: `data_YYYYMMDD_HHMMSS.csv`
- **图像文件**: `img_YYYYMMDD_HHMMSS_mmm.jpg`

### CSV文件包含的数据列：
- timestamp（时间戳）
- voltage_ch0, current_ch1, voltage_ch2, voltage_ch3（ADC数据）
- raw_ch0, raw_ch1, raw_ch2, raw_ch3（ADC原始值）
- lux, temperature, pressure, humidity, altitude（环境数据）

## 使用方法

### 发送端启动：
```bash
# 使用启动脚本（推荐）
./start_wifi_sender.sh

# 或直接运行
python3 wifi_sender.py
```

### 接收端启动：
```bash
python wifi_receiver_gui.py
```

### 操作步骤：
1. 启动发送端（树莓派）
2. 启动接收端GUI（Windows）
3. 等待连接建立（状态栏显示绿色"已连接"）
4. 点击"开启数据监测"开始读取传感器数据
5. 根据需要选择其他功能：
   - 仅看数据：只开启"数据监测"
   - 仅录像：开启"录像"
   - 仅保存数据：开启"数据记录"
   - 录像+数据：开启"录像+数据"

## 网络配置

### 默认配置：
- **指令端口**: 8889
- **图像端口**: 8888
- **发送端IP**: 192.168.1.205（需要根据实际情况修改）

### 修改IP地址：
在 `wifi_receiver_gui.py` 中修改 `SENDER_IP` 变量

## 依赖包

### 发送端（树莓派）：
```bash
pip3 install Adafruit-ADS1x15 smbus picamera
```

### 接收端（Windows）：
```bash
pip install tkinter（通常Python自带）
```

## 硬件要求

### 发送端：
- 树莓派（已启用I2C和摄像头）
- ADS1115 ADC模块
- 环境传感器（I2C地址0x5B）
- 摄像头模块

### 接收端：
- Windows/Linux/Mac电脑
- Python 3.6+
- 网络连接

## 故障排除

### 常见问题：

#### 1. 连接问题
- **症状**: 连接失败，状态显示"未连接"
- **解决**: 检查网络连接和IP地址配置
- **检查**: `wifi_receiver_gui.py` 中的 `SENDER_IP` 变量

#### 2. 传感器问题
- **症状**: 传感器初始化失败，数据显示"数据不可用"
- **解决**: 检查I2C连接和权限
- **检查**: 运行 `sudo i2cdetect -y 1` 查看I2C设备

#### 3. 摄像头问题
- **症状**: 无法捕获图像，图像捕获失败
- **快速诊断**: 运行 `python3 test_camera.py`
- **详细指南**: 查看 `CAMERA_TROUBLESHOOTING.md`
- **常见解决方案**:
  - 启用摄像头: `sudo raspi-config`
  - 检查连接线
  - 增加GPU内存分配
  - 安装picamera: `pip3 install picamera`

#### 4. 数据显示问题
- **症状**: 数据显示"未检测"
- **解决**: 确保已开启数据监测功能
- **检查**: 点击"开启数据监测"按钮

#### 5. 权限问题
- **症状**: GPIO或摄像头权限被拒绝
- **解决**: 
  ```bash
  sudo usermod -a -G video,gpio,i2c $USER
  sudo chmod 666 /dev/gpiomem
  ```

### 调试工具：

#### 摄像头测试脚本：
```bash
python3 test_camera.py
```

#### 系统状态检查：
```bash
# 检查摄像头
vcgencmd get_camera

# 检查GPU内存
vcgencmd get_mem gpu

# 检查I2C设备
sudo i2cdetect -y 1
```

### 日志信息：
- 发送端：终端输出详细状态信息
- 接收端：GUI底部日志区域显示连接和操作状态
