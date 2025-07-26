# 摄像头问题诊断和解决指南

## 问题：wifi_sender.py无法捕获图像

### 1. 快速诊断

运行摄像头测试脚本：
```bash
python3 test_camera.py
```

### 2. 常见问题和解决方案

#### 问题1：picamera模块未安装
**错误信息**: `ModuleNotFoundError: No module named 'picamera'`

**解决方案**:
```bash
pip3 install picamera
# 或者
sudo apt install python3-picamera
```

#### 问题2：摄像头未启用
**错误信息**: `Camera is not enabled` 或 `No such file or directory`

**解决方案**:
1. 启用摄像头接口：
```bash
sudo raspi-config
```
2. 选择 `Interface Options` → `Camera` → `Yes`
3. 重启树莓派：
```bash
sudo reboot
```

#### 问题3：摄像头硬件未检测到
**错误信息**: `Camera is not detected`

**解决方案**:
1. 检查摄像头连接线是否正确插入
2. 确保连接线没有损坏
3. 检查摄像头模块本身
4. 验证检测状态：
```bash
vcgencmd get_camera
```
应该显示: `supported=1 detected=1`

#### 问题4：GPU内存不足
**错误信息**: 摄像头初始化失败或图像捕获异常

**解决方案**:
1. 检查GPU内存分配：
```bash
vcgencmd get_mem gpu
```
2. 如果少于64MB，需要增加GPU内存：
```bash
sudo raspi-config
```
3. 选择 `Advanced Options` → `Memory Split` → 设置为 `128`
4. 重启树莓派

#### 问题5：摄像头被其他程序占用
**错误信息**: `out of resources` 或 `Camera is busy`

**解决方案**:
1. 关闭其他使用摄像头的程序
2. 查找占用摄像头的进程：
```bash
sudo lsof /dev/vchiq
sudo lsof /dev/video*
```
3. 如果必要，重启树莓派

#### 问题6：权限问题
**错误信息**: `Permission denied`

**解决方案**:
1. 确保用户在video组中：
```bash
sudo usermod -a -G video $USER
```
2. 注销并重新登录，或重启

### 3. 系统要求检查

#### 检查摄像头硬件：
```bash
# 检查摄像头检测状态
vcgencmd get_camera

# 检查GPU内存
vcgencmd get_mem gpu

# 检查设备文件
ls -l /dev/video*
ls -l /dev/vchiq
```

#### 检查系统版本：
```bash
# 查看树莓派型号
cat /proc/cpuinfo | grep Model

# 查看操作系统版本
cat /etc/os-release
```

### 4. 手动测试步骤

#### 步骤1：基础命令行测试
```bash
# 使用raspistill测试
raspistill -o test.jpg -t 2000

# 如果成功，说明硬件正常
```

#### 步骤2：Python基础测试
```python
import picamera
import time

camera = picamera.PiCamera()
camera.capture('/home/pi/test_python.jpg')
camera.close()
```

#### 步骤3：运行完整测试脚本
```bash
python3 test_camera.py
```

### 5. wifi_sender.py 特定修复

如果摄像头硬件测试正常，但wifi_sender.py仍然无法捕获图像：

1. **检查初始化顺序**：确保摄像头在其他模块之前初始化
2. **增加预热时间**：摄像头需要足够的预热时间
3. **检查内存使用**：大量的传感器读取可能影响摄像头性能
4. **网络连接问题**：确保网络配置正确

### 6. 调试信息

修改后的wifi_sender.py包含详细的调试信息：

- 摄像头初始化状态
- 图像捕获过程日志
- 错误类型和详细信息
- 网络连接状态

### 7. 联系支持

如果以上方法都无法解决问题，请提供以下信息：

1. `test_camera.py` 的完整输出
2. `vcgencmd get_camera` 的输出
3. `vcgencmd get_mem gpu` 的输出
4. 树莓派型号和操作系统版本
5. wifi_sender.py的错误日志

### 8. 备选方案

如果摄像头仍然无法工作，可以：

1. **使用USB摄像头**：修改代码使用cv2库
2. **禁用摄像头功能**：只使用传感器数据采集
3. **使用网络摄像头**：通过IP摄像头获取图像

### 9. 预防措施

1. 定期检查摄像头连接
2. 避免频繁插拔摄像头连接线
3. 确保充足的电源供应
4. 定期更新系统和软件包
