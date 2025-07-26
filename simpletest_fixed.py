# Simple demo of reading each analog input from the ADS1x15 and printing it to
# the screen.
# Author: Tony DiCola
# License: Public Domain
import time
import sys

# Import the ADS1x15 module.
import Adafruit_ADS1x15
# Import smbus for I2C communication
import smbus

try:
    # Create an ADS1115 ADC (16-bit) instance.
    # Try to specify the I2C bus explicitly (usually bus 1 on Raspberry Pi)
    adc = Adafruit_ADS1x15.ADS1115(busnum=1)
    
    # Initialize I2C bus for environmental sensor
    i2c_bus = smbus.SMBus(1)  # Use I2C bus 1
    ENV_SENSOR_ADDR = 0x5B    # 7-bit I2C address
    
except Exception as e:
    print(f"Error initializing ADS1115 with busnum=1: {e}")
    try:
        # Try without specifying the bus
        adc = Adafruit_ADS1x15.ADS1115()
        i2c_bus = smbus.SMBus(1)
        ENV_SENSOR_ADDR = 0x5B
    except Exception as e2:
        print(f"Error initializing devices: {e2}")
        print("I2C might not be enabled. Please enable I2C and try again.")
        print("You can run: sudo dtparam i2c_arm=on")
        sys.exit(1)

# Or create an ADS1015 ADC (12-bit) instance.
#adc = Adafruit_ADS1x15.ADS1015()

# Note you can change the I2C address from its default (0x48), and/or the I2C
# bus by passing in these optional parameters:
#adc = Adafruit_ADS1x15.ADS1015(address=0x49, busnum=1)

# Choose a gain of 1 for reading voltages from 0 to 4.09V.
# Or pick a different gain to change the range of voltages that are read:
#  - 2/3 = +/-6.144V
#  -   1 = +/-4.096V
#  -   2 = +/-2.048V
#  -   4 = +/-1.024V
#  -   8 = +/-0.512V
#  -  16 = +/-0.256V
# See table 3 in the ADS1015/ADS1115 datasheet for more info on gain.
GAIN = 1

# ADS1115转换参数
# ADS1115是16位ADC，对于GAIN=1，电压范围是±4.096V
# 最大正值ADC读数是32767，对应+4.096V
MAX_ADC_VALUE = 32767
ADC_VOLTAGE_RANGE = 4.096  # V

# 转换系数
# 通道0：电压测量，测量电压0-3.3V对应实际电压0-60V
# 转换公式：实际电压 = (ADC电压读数 / 3.3V) * 60V
VOLTAGE_SCALE = 60.0 / 3.3  # 实际电压范围 / 测量电压范围

# 通道1：电流测量，测量电压0-3.3V对应实际电流0-120A  
# 转换公式：实际电流 = (ADC电压读数 / 3.3V) * 120A
CURRENT_SCALE = 120.0 / 3.3  # 实际电流范围 / 测量电压范围

def adc_to_voltage_reading(adc_value):
    """将ADC原始值转换为电压读数(V)"""
    if adc_value < 0:
        return 0.0  # 负值按0处理
    voltage_reading = (adc_value / MAX_ADC_VALUE) * ADC_VOLTAGE_RANGE
    return min(voltage_reading, 3.3)  # 限制在3.3V以内

def convert_to_actual_voltage(adc_value):
    """将ADC值转换为实际电压(0-60V)"""
    voltage_reading = adc_to_voltage_reading(adc_value)
    actual_voltage = voltage_reading * VOLTAGE_SCALE
    return actual_voltage

def convert_to_actual_current(adc_value):
    """将ADC值转换为实际电流(0-120A)"""
    voltage_reading = adc_to_voltage_reading(adc_value)
    actual_current = voltage_reading * CURRENT_SCALE
    return actual_current

def read_env_sensor_data():
    """读取环境传感器数据"""
    try:
        # 读取光照强度数据 (从寄存器0x00开始读取4字节)
        lux_data = []
        for i in range(4):
            lux_data.append(i2c_bus.read_byte_data(ENV_SENSOR_ADDR, 0x00 + i))
        # 读取BME传感器数据 (从寄存器0x04开始读取10字节)
        bme_data = []
        for i in range(10):
            bme_data.append(i2c_bus.read_byte_data(ENV_SENSOR_ADDR, 0x04 + i))
        
        # 解析光照强度 (32位数据，使用方法2：忽略首字节)
        if lux_data[0] == 0x80:  # 检测到错误标志，忽略首字节
            lux_raw = (lux_data[1] << 16) | (lux_data[2] << 8) | lux_data[3]
        else:  # 标准32位解析
            data_16_0 = (lux_data[0] << 8) | lux_data[1]
            data_16_1 = (lux_data[2] << 8) | lux_data[3]
            lux_raw = (data_16_0 << 16) | data_16_1
            
        # 转换为实际lux值，限制合理范围
        if lux_raw > 1000000:
            lux = 0  # 异常大值设为0
        else:
            lux = lux_raw / 100.0
            if lux > 100000:
                lux = 100000  # 限制最大值
        
        # 解析温度 (16位数据)
        temperature = (bme_data[0] << 8) | bme_data[1]
        temperature = temperature / 100.0  # 转换为摄氏度
        
        # 解析气压 (32位数据)
        pressure_16_0 = (bme_data[2] << 8) | bme_data[3]
        pressure_16_1 = (bme_data[4] << 8) | bme_data[5]
        pressure = (pressure_16_0 << 16) | pressure_16_1
        pressure = pressure / 100.0  # 转换为Pa
        
        # 解析湿度 (16位数据)
        humidity = (bme_data[6] << 8) | bme_data[7]
        humidity = humidity / 100.0  # 转换为百分比
        
        # 解析海拔 (16位数据)
        altitude = (bme_data[8] << 8) | bme_data[9]
        # 海拔保持原始值，单位为米
        
        return {
            'lux': lux,
            'temperature': temperature,
            'pressure': pressure,
            'humidity': humidity,
            'altitude': altitude
        }
    except Exception as e:
        print(f"Error reading environmental sensor: {e}")
        return None

print('Reading ADS1x15 values, press Ctrl-C to quit...')
print('=' * 80)
# Main loop.
try:
    while True:
        # Read all the ADC channel values in a list.
        values = [0]*4
        for i in range(4):
            # Read the specified ADC channel using the previously set gain value.
            values[i] = adc.read_adc(i, gain=GAIN)
            # Note you can also pass in an optional data_rate parameter that controls
            # the ADC conversion time (in samples/second). Each chip has a different
            # set of allowed data rate values, see datasheet Table 9 config register
            # DR bit values.
            #values[i] = adc.read_adc(i, gain=GAIN, data_rate=128)
            # Each value will be a 12 or 16 bit signed integer value depending on the
            # ADC (ADS1015 = 12-bit, ADS1115 = 16-bit).
        
        # 转换通道0和通道1的值
        voltage = convert_to_actual_voltage(values[0])
        current = convert_to_actual_current(values[1])
        
        # 转换通道2和通道3为电压值 (ADC电压读数)
        voltage_ch2 = adc_to_voltage_reading(values[2])
        voltage_ch3 = adc_to_voltage_reading(values[3])
        
        # 读取环境传感器数据
        env_data = read_env_sensor_data()
        
        # 显示当前时间
        current_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(f"\n[{current_time}] 传感器数据读取:")
        print("-" * 60)
        
        # 打印ADC转换后的数据
        print("📊 ADC数据:")
        print(f"  通道0 - 电压: {voltage:8.2f} V    (原始值: {values[0]:6})")
        print(f"  通道1 - 电流: {current:8.2f} A    (原始值: {values[1]:6})")
        print(f"  通道2 - 电压: {voltage_ch2:8.3f} V  (原始值: {values[2]:6})")
        print(f"  通道3 - 电压: {voltage_ch3:8.3f} V  (原始值: {values[3]:6})")
        
        # 打印环境传感器数据
        print("\n🌡️  环境传感器数据:")
        if env_data:
            print(f"  光照强度:  {env_data['lux']:8.2f} lux")
            print(f"  温度:      {env_data['temperature']:6.2f} °C")
            print(f"  气压:      {env_data['pressure']:8.2f} Pa")
            print(f"  湿度:      {env_data['humidity']:6.2f} %")
            print(f"  海拔:      {env_data['altitude']:6} m")
        else:
            print("  ❌ 环境传感器读取失败")
        
        print("=" * 60)
        # Pause for half a second.
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nProgram interrupted by user")
    sys.exit(0)
except Exception as e:
    print(f"Error during operation: {e}")
    sys.exit(1)
