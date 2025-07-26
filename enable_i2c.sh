#!/bin/bash

echo "Enabling I2C on Raspberry Pi..."

# Method 1: Using dtparam (modern way)
echo "Trying to enable I2C using dtparam..."
sudo dtparam i2c_arm=on

# Method 2: Load modules manually
echo "Loading I2C modules..."
sudo modprobe i2c-dev
sudo modprobe i2c-bcm2835

# Method 3: Check if config file exists and add I2C configuration
CONFIG_FILES=("/boot/config.txt" "/boot/firmware/config.txt" "/boot/firmware/usercfg.txt")

for config_file in "${CONFIG_FILES[@]}"; do
    if [[ -f "$config_file" ]]; then
        echo "Found config file: $config_file"
        # Check if I2C is already enabled
        if ! grep -q "dtparam=i2c_arm=on" "$config_file"; then
            echo "Adding I2C configuration to $config_file"
            echo "dtparam=i2c_arm=on" | sudo tee -a "$config_file"
        else
            echo "I2C already configured in $config_file"
        fi
        break
    fi
done

# Create I2C device nodes if they don't exist
if [[ ! -e /dev/i2c-1 ]]; then
    echo "Creating I2C device node..."
    sudo mknod /dev/i2c-1 c 89 1
    sudo chown root:i2c /dev/i2c-1
    sudo chmod 664 /dev/i2c-1
fi

# Check the result
echo "Checking I2C status..."
ls -la /dev/i2c* 2>/dev/null || echo "No I2C devices found"

echo "I2C setup complete. You may need to reboot for changes to take effect."
echo "After reboot, try running: sudo python3 simpletest_fixed.py"
