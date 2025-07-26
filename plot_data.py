import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np
import os
import sys
import argparse
import cv2
import glob
from PIL import Image

def parse_arguments():
    """
    解析命令行参数
    """
    parser = argparse.ArgumentParser(description='处理CSV数据并生成图表，可选择生成视频')
    parser.add_argument('csv_file', help='CSV文件路径')
    parser.add_argument('-v', '--video', choices=['y', 'n'], default='n', 
                       help='是否处理图片为视频 (y/n，默认为n)')
    
    return parser.parse_args()

def remove_outliers(df, column, method='jump', threshold=3):
    """
    删除异常值/错误点
    
    Parameters:
    df: DataFrame
    column: 列名
    method: 'iqr' (四分位距法)、'zscore' (Z分数法) 或 'jump' (跳变检测法)
    threshold: 阈值，对于jump是标准差倍数，对于IQR是倍数，对于zscore是标准差倍数
    """
    if method == 'jump':
        # 基于相邻点差异的跳变检测法，专门针对单独的异常跳变点
        data = df[column].values
        outlier_mask = np.zeros(len(data), dtype=bool)
        
        if len(data) < 3:
            return outlier_mask
        
        # 计算相邻点的差异
        diff = np.abs(np.diff(data))
        diff_std = np.std(diff)
        diff_mean = np.mean(diff)
        
        # 对于每个点，检查它与前后点的差异
        for i in range(1, len(data) - 1):
            # 计算当前点与前一点和后一点的差异
            diff_prev = abs(data[i] - data[i-1])
            diff_next = abs(data[i] - data[i+1])
            
            # 如果当前点与前后两点的差异都很大，且远超过正常变化范围
            if (diff_prev > diff_mean + threshold * diff_std and 
                diff_next > diff_mean + threshold * diff_std):
                outlier_mask[i] = True
        
        return outlier_mask
        
    elif method == 'iqr':
        # 使用四分位距法检测异常值
        Q1 = df[column].quantile(0.25)
        Q3 = df[column].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - threshold * IQR
        upper_bound = Q3 + threshold * IQR
        
        # 标记异常值
        outlier_mask = (df[column] < lower_bound) | (df[column] > upper_bound)
        
    elif method == 'zscore':
        # 使用Z分数法检测异常值
        z_scores = np.abs((df[column] - df[column].mean()) / df[column].std())
        outlier_mask = z_scores > threshold
    
    return outlier_mask

def create_video_from_images(csv_file):
    """
    将CSV文件同目录下的JPG图片合并成MP4视频
    
    Parameters:
    csv_file: CSV文件路径
    """
    # 获取CSV文件所在目录和文件名前缀
    csv_dir = os.path.dirname(csv_file)
    csv_prefix = os.path.splitext(os.path.basename(csv_file))[0]
    
    # 查找同目录下以img开头的jpg文件
    jpg_pattern = os.path.join(csv_dir, "img*.jpg")
    jpg_files = glob.glob(jpg_pattern)
    
    if not jpg_files:
        print("未找到以img开头的JPG文件，跳过视频生成")
        return
    
    # 按文件名排序
    jpg_files.sort()
    print(f"找到 {len(jpg_files)} 个以img开头的JPG文件")
    
    # 读取第一张图片获取尺寸
    first_image = cv2.imread(jpg_files[0])
    if first_image is None:
        print("无法读取第一张图片")
        return
    
    height, width, layers = first_image.shape
    
    # 设置视频参数
    fps = 10  # 帧率，可以根据需要调整
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    
    # 创建输出视频文件路径
    output_video = os.path.join(csv_dir, f"{csv_prefix}.mp4")
    
    # 创建VideoWriter对象
    video_writer = cv2.VideoWriter(output_video, fourcc, fps, (width, height))
    
    if not video_writer.isOpened():
        print("无法创建视频文件")
        return
    
    # 逐帧写入视频
    for i, jpg_file in enumerate(jpg_files):
        image = cv2.imread(jpg_file)
        if image is not None:
            # 确保图片尺寸一致
            if image.shape[:2] != (height, width):
                image = cv2.resize(image, (width, height))
            video_writer.write(image)
            if (i + 1) % 10 == 0:  # 每10帧打印一次进度
                print(f"已处理 {i + 1}/{len(jpg_files)} 张图片")
        else:
            print(f"无法读取图片: {jpg_file}")
    
    # 释放资源
    video_writer.release()
    print(f"视频已保存: {output_video}")

def plot_csv_data(csv_file):
    """
    读取CSV文件并为每一列绘制单独的图像
    横坐标为时间，第一帧为0秒，后面按照秒计算
    """
    # 读取CSV文件
    df = pd.read_csv(csv_file)
    
    # 转换时间戳为datetime对象
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # 计算相对时间（从第一帧开始的秒数）
    first_time = df['timestamp'].iloc[0]
    df['relative_time'] = (df['timestamp'] - first_time).dt.total_seconds()
    
    # 获取除了timestamp和relative_time之外的所有数据列，排除raw开头的列
    data_columns = [col for col in df.columns if col not in ['timestamp', 'relative_time'] and not col.startswith('raw')]
    
    # 获取CSV文件名前缀（不包括扩展名）和所在目录
    csv_prefix = os.path.splitext(os.path.basename(csv_file))[0]
    csv_dir = os.path.dirname(csv_file)
    
    # 为每一列创建单独的图像
    for column in data_columns:
        plt.figure(figsize=(12, 6))
        # 转换为numpy数组以避免pandas版本兼容性问题
        x_data = df['relative_time'].to_numpy()
        y_data = df[column].to_numpy()
        plt.plot(x_data, y_data, linewidth=1, marker='o', markersize=2)
        plt.title(f'{column}', fontsize=14, fontweight='bold')
        plt.xlabel('Time (seconds)', fontsize=12)
        plt.ylabel(column, fontsize=12)
        plt.grid(True, alpha=0.3)
        
        # 设置纵坐标从0到数据最大值的1.2倍
        y_max = df[column].max()
        plt.ylim(0, y_max * 1.2)
        
        # 设置图形样式
        plt.tight_layout()
        
        # 保存图像到CSV文件所在目录，使用CSV文件名作为前缀
        output_filename = os.path.join(csv_dir, f'{csv_prefix}_{column}_plot.png')
        plt.savefig(output_filename, dpi=300, bbox_inches='tight')
        print(f"已保存图像: {output_filename}")
        
        # 关闭当前图像以释放内存
        plt.close()
    
    # 打印数据摘要
    print(f"\n数据摘要:")
    print(f"总时间范围: {df['relative_time'].iloc[-1]:.2f} 秒")
    print(f"数据点数量: {len(df)}")
    print(f"采样频率: {len(df) / df['relative_time'].iloc[-1]:.2f} Hz")
    print(f"数据列数量: {len(data_columns)}")
    print(f"数据列: {', '.join(data_columns)}")

if __name__ == "__main__":
    # 解析命令行参数
    args = parse_arguments()
    
    csv_file = args.csv_file
    create_video = args.video == 'y'
    
    # 检查CSV文件是否存在
    if not os.path.exists(csv_file):
        print(f"错误: 文件 {csv_file} 不存在")
        sys.exit(1)
    
    print(f"正在处理文件: {csv_file}")
    
    # 绘制数据图表
    plot_csv_data(csv_file)
    
    # 根据命令行参数决定是否创建视频
    if create_video:
        print("\n开始处理以img开头的JPG图片生成视频...")
        create_video_from_images(csv_file)
    else:
        print("\n未指定视频处理参数，跳过视频生成")