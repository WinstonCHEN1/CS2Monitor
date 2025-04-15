import json, os
from django.shortcuts import render
from django.http import JsonResponse
import pandas as pd
import subprocess
from datetime import datetime

import matplotlib
matplotlib.use('Agg')  # 使用无 GUI 的后端
import matplotlib.pyplot as plt

from io import BytesIO
import base64

def home(request):
    return render(request, 'home.html')

def get_json_files():
    folder = './cs_data'
    files = {}
    for file in sorted(os.listdir(folder)):
        if file.endswith('.json') and 'qaq_' in file:
            parts = file.split("_")
            item_type = parts[1]  # 提取类型
            timestamp = parts[-2] + "_" + parts[-1].replace(".json", "")
            
            if timestamp not in files:
                files[timestamp] = []  # 初始化时间戳对应的列表
            
            files[timestamp].append({
                'filename': file,
                'item_type': item_type  # 添加类型信息
            })
    
    # 转换为列表格式
    return [{'timestamp': ts, 'items': items} for ts, items in files.items()]

def load_price_data(filename):
    folder = './cs_data'
    data_points = []
    
    with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
        for name, data in raw_data.items():
            try:
                # 提取buff价格
                buff_price = float(data['buff_price'].replace('￥', '').strip())
                # 提取uu价格
                uu_price = float(data['uu_price'].replace('￥', '').strip())
                # 提取今日变化
                today_change = data['today_change']
                # 提取周变化
                week_change = data['week_change']
                
                data_points.append({
                    "item": name,
                    "buff_price": buff_price,
                    "uu_price": uu_price,
                    "today_change": today_change,
                    "week_change": week_change
                })
            except:
                continue
    return pd.DataFrame(data_points)

def price_overview(request):
    files = get_json_files()
    selected_timestamp = request.GET.get('timestamp', files[0]['timestamp'] if files else None)
    
    if not selected_timestamp:
        return render(request, 'overview.html', {"data": None, "files": files})
    
    # 组织所有类型的数据
    all_items_data = {}
    for entry in files:
        if entry['timestamp'] == selected_timestamp:  # 只处理选中的时间戳
            for item in entry['items']:
                df = load_price_data(item['filename'])
                for _, row in df.iterrows():
                    item_type = item['item_type']
                    if item_type not in all_items_data:
                        all_items_data[item_type] = []
                    all_items_data[item_type].append({
                        "name": row["item"],
                        "buff_price": row["buff_price"],
                        "uu_price": row["uu_price"],
                        "today_change": row["today_change"],
                        "week_change": row["week_change"]
                    })
    
    return render(request, "overview.html", {
        "data": all_items_data,  # 返回所有类型的数据
        "files": files,
        "selected_timestamp": selected_timestamp
    })

def price_chart(request):
    files = get_json_files()
    selected_file = request.GET.get('file', files[0]['filename'] if files else None)
    item_name = request.GET.get("item", "★ 蝴蝶刀")
    
    if not selected_file:
        return render(request, 'chart.html', {"data": None, "files": files})
    
    # 获取所有文件的数据
    all_data = []
    for file in files:
        df = load_price_data(file['filename'])
        if not df.empty:
            df_item = df[df["item"].str.contains(item_name)]
            if not df_item.empty:
                all_data.append({
                    "time": file['timestamp'],
                    "buff_price": df_item["buff_price"].iloc[0],
                    "uu_price": df_item["uu_price"].iloc[0]
                })
    
    if not all_data:
        return render(request, 'chart.html', {"data": None, "files": files})
    
    # 按时间排序
    all_data.sort(key=lambda x: x["time"])
    
    # 准备图表数据
    chart_data = {
        "item": item_name,
        "times": [d["time"] for d in all_data],
        "buff_prices": [d["buff_price"] for d in all_data],
        "uu_prices": [d["uu_price"] for d in all_data],
        "current_buff_price": all_data[-1]["buff_price"] if all_data else None,
        "current_uu_price": all_data[-1]["uu_price"] if all_data else None
    }
    
    return render(request, "chart.html", {
        "data": chart_data,
        "files": files,
        "selected_file": selected_file
    })

def crawler(request):
    crawler_status = "stopped"
    last_run = None
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'start':
            # 获取配置参数
            interval = request.POST.get('interval', '30')
            max_pages = request.POST.get('max_pages', '10')
            item_type = request.POST.get('item_type', 'butterfly')
            
            # 构建命令
            cmd = f"conda activate buff && python cs2monitor/crawler.py --interval {interval} --max_pages {max_pages} --item_type {item_type}"
            
            # 启动爬虫
            try:
                subprocess.Popen(cmd, shell=True)
                crawler_status = "running"
                last_run = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                print(f"Error starting crawler: {e}")
        
        elif action == 'stop':
            # 停止爬虫
            try:
                subprocess.run("pkill -f crawler.py", shell=True)
                crawler_status = "stopped"
            except Exception as e:
                print(f"Error stopping crawler: {e}")
    
    return render(request, "crawler.html", {
        "crawler_status": crawler_status,
        "last_run": last_run
    })

def calculate_technical_indicators(df, item_name):
    """
    计算技术指标
    :param df: 包含价格数据的DataFrame
    :param item_name: 饰品名称
    :return: 包含所有指标的字典
    """
    # 确保数据按时间排序
    df = df.sort_values('time')
    
    # 计算移动平均线
    df['MA5'] = df['buff_price'].rolling(window=5).mean()
    df['MA20'] = df['buff_price'].rolling(window=20).mean()
    
    # 计算价格波动率（7天标准差）
    df['volatility'] = df['buff_price'].rolling(window=7).std()
    
    # 计算RSI
    delta = df['buff_price'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 计算价格相对于7天均值的标准差
    df['buff_price_mean'] = df['buff_price'].rolling(window=7).mean()
    df['buff_price_std'] = df['buff_price'].rolling(window=7).std()
    df['buff_price_zscore'] = (df['buff_price'] - df['buff_price_mean']) / df['buff_price_std']
    
    return df

def generate_trading_signals(df):
    """
    生成交易信号
    :param df: 包含技术指标的DataFrame
    :return: 交易信号字典
    """
    signals = {
        'buy_signals': [],
        'sell_signals': [],
        'current_status': 'hold'
    }
    
    if len(df) < 20:  # 确保有足够的数据
        return signals
    
    current = df.iloc[-1]
    prev = df.iloc[-2]
    
    # 买入信号检查
    buy_conditions = 0
    
    # 1. MA金叉
    if prev['MA5'] <= prev['MA20'] and current['MA5'] > current['MA20']:
        buy_conditions += 1
        signals['buy_signals'].append('MA金叉')
    
    # 2. RSI < 40
    if current['RSI'] < 40:
        buy_conditions += 1
        signals['buy_signals'].append('RSI超卖')
    
    # 3. 价格接近7天低点
    if current['buff_price_zscore'] < -1:
        buy_conditions += 1
        signals['buy_signals'].append('价格接近低点')
    
    # 4. 检查市场库存变化（需要额外数据）
    # 这里假设有库存数据，实际需要根据数据结构调整
    if 'inventory_change' in df.columns and current['inventory_change'] < 0:
        buy_conditions += 1
        signals['buy_signals'].append('库存减少')
    
    # 卖出信号检查
    sell_conditions = 0
    
    # 1. MA死叉
    if prev['MA5'] >= prev['MA20'] and current['MA5'] < current['MA20']:
        sell_conditions += 1
        signals['sell_signals'].append('MA死叉')
    
    # 2. RSI > 60
    if current['RSI'] > 60:
        sell_conditions += 1
        signals['sell_signals'].append('RSI超买')
    
    # 3. 价格接近7天高点
    if current['buff_price_zscore'] > 1:
        sell_conditions += 1
        signals['sell_signals'].append('价格接近高点')
    
    # 4. 检查持有时间（需要额外数据）
    if 'holding_days' in df.columns and current['holding_days'] >= 7:
        sell_conditions += 1
        signals['sell_signals'].append('持有时间达标')
    
    # 生成最终信号
    if buy_conditions >= 3:
        signals['current_status'] = 'buy'
    elif sell_conditions >= 3:
        signals['current_status'] = 'sell'
    
    return signals

def trading_strategy(request):
    """
    量化交易策略视图函数
    """
    files = get_json_files()
    selected_file = request.GET.get('file', files[0]['filename'] if files else None)
    item_name = request.GET.get("item", "★ 蝴蝶刀")
    
    if not selected_file:
        return render(request, 'strategy.html', {"data": None, "files": files})
    
    # 获取所有文件的数据
    all_data = []
    for file in files:
        df = load_price_data(file['filename'])
        if not df.empty:
            df_item = df[df["item"].str.contains(item_name)]
            if not df_item.empty:
                all_data.append({
                    "time": file['timestamp'],
                    "buff_price": df_item["buff_price"].iloc[0],
                    "uu_price": df_item["uu_price"].iloc[0]
                })
    
    if not all_data:
        return render(request, 'strategy.html', {"data": None, "files": files})
    
    # 转换为DataFrame
    df = pd.DataFrame(all_data)
    df['time'] = pd.to_datetime(df['time'])
    df = df.sort_values('time')
    
    # 计算技术指标
    df = calculate_technical_indicators(df, item_name)
    
    # 生成交易信号
    signals = generate_trading_signals(df)
    
    # 准备展示数据
    strategy_data = {
        "item": item_name,
        "current_buff_price": df['buff_price'].iloc[-1],
        "current_uu_price": df['uu_price'].iloc[-1],
        "signals": signals,
        "indicators": {
            "MA5": df['MA5'].iloc[-1],
            "MA20": df['MA20'].iloc[-1],
            "RSI": df['RSI'].iloc[-1],
            "volatility": df['volatility'].iloc[-1],
            "buff_price_zscore": df['buff_price_zscore'].iloc[-1]
        }
    }
    
    return render(request, "strategy.html", {
        "data": strategy_data,
        "files": files,
        "selected_file": selected_file
    })
