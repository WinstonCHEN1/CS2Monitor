import asyncio
from playwright.async_api import async_playwright
import json
import os
import logging
from datetime import datetime
import random

# 根URL
BASE_URL = "https://buff.163.com/market/csgo#game=csgo"

# 从提供的 set-cookie 中提取的初始 Cookie
INITIAL_COOKIES = [
    {
        "name": "session",
        "value": "1-jv8s...",
        "domain": ".buff.163.com",
        "path": "/"
    },
    {
        "name": "csrf_token",
        "value": "ImN...",
        "domain": ".buff.163.com",
        "path": "/"
    }
]

# 设置日志和文件的时间戳
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = f"cs_scraper_{TIMESTAMP}.log"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        # logging.FileHandler(LOG_FILE, encoding='utf-8'),  # 保存到文件
        logging.StreamHandler()  # 同时输出到控制台
    ]
)
logger = logging.getLogger(__name__)

# 修改保存结果的函数，增加创建目录的功能
def save_to_json(data, filename):
    # 确保目录存在
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
    else:
        existing_data = {}
    existing_data.update(data)
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=4)
    logger.info(f"数据已增量保存到 {filename}")

# 抓取单页数据的函数（带重试机制）
async def scrape_page(page_num, context, category_group=None, max_retries=3):
    for attempt in range(max_retries):
        try:
            # 添加0-3秒的随机延迟
            delay = random.uniform(0, 3)
            logger.info(f"第 {page_num} 页将在 {delay:.2f} 秒后开始抓取 (尝试 {attempt + 1}/{max_retries})")
            await asyncio.sleep(delay)
            
            page = await context.new_page()
            url = f"{BASE_URL}&page_num={page_num}&tab=selling"
            if category_group:
                # url += f"&category_group={category_group}"
                url += f"&category={category_group}"
            logger.info(f"正在抓取第 {page_num} 页：{url}")
            
            await page.goto(url, wait_until="networkidle", timeout=6000)
            await page.wait_for_selector("div.list_card", timeout=3000)
            
            html_content = await page.content()
            logger.debug(f"第 {page_num} 页 HTML（前 500 字符）：{html_content[:500]}")
            
            name_elements = await page.query_selector_all("div.list_card a")
            names = [await elem.inner_text() for elem in name_elements]
            names = [name.strip() for name in names if name.strip()]
            logger.info(f"第 {page_num} 页 - 找到 {len(names)} 个饰品名称：{names}")
            
            price_elements = await page.query_selector_all("div.list_card p strong")
            prices = [await elem.inner_text() for elem in price_elements]
            logger.info(f"第 {page_num} 页 - 找到 {len(prices)} 个价格：{prices}")
            
            if len(names) != len(prices):
                logger.warning(f"第 {page_num} 页 - 名称 ({len(names)}) 和价格 ({len(prices)}) 数量不匹配")
            
            result = {names[i]: prices[i] for i in range(min(len(names), len(prices)))}
            
            await page.close()
            return result
        
        except Exception as e:
            logger.error(f"第 {page_num} 页出错 (尝试 {attempt + 1}/{max_retries})：{str(e)}")
            await page.close()
            if attempt == max_retries - 1:
                logger.error(f"第 {page_num} 页在 {max_retries} 次尝试后仍然失败，跳过此页")
                return {}
            await asyncio.sleep(random.uniform(1, 5))  # 在重试前等待1-5秒

# 获取总页数的函数
async def get_total_pages(context, category_group=None):
    try:
        page = await context.new_page()
        url = f"{BASE_URL}&page_num=1&tab=selling"
        if category_group:
            # url += f"&category_group={category_group}"
            url += f"&category={category_group}"

        logger.info(f"获取总页数：{url}")
        
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_selector("div.pager", timeout=15000)
        
        page_links = await page.query_selector_all("div.pager a.page-link")
        if not page_links:
            logger.warning("未找到分页链接，返回默认页数 1")
            await page.close()
            return 1
        
        page_numbers = [await link.inner_text() for link in page_links]
        logger.debug(f"分页链接文本：{page_numbers}")
        
        valid_numbers = [int(num) for num in page_numbers if num.strip().isdigit()]
        if len(valid_numbers) < 2:
            logger.warning("分页链接不足2个有效数字，返回默认页数 1")
            await page.close()
            return 1
        
        total_pages = valid_numbers[-1]  # 取最后一个数字作为总页数
        logger.info(f"动态获取的总页数：{total_pages}")
        
        await page.close()
        return total_pages
    
    except Exception as e:
        logger.error(f"获取总页数出错：{str(e)}，使用默认页数 1")
        return 1

# 修改并发抓取函数，每批次完成后立即保存
async def scrape_pages_concurrently(start_page, end_page, concurrency, context, output_file, category_group=None):
    tasks = []
    for page_num in range(start_page, end_page + 1):
        tasks.append(scrape_page(page_num, context, category_group))
    
    for i in range(0, len(tasks), concurrency):
        batch = tasks[i:i + concurrency]
        batch_results = await asyncio.gather(*batch)
        # 每个批次完成后立即保存
        for result in batch_results:
            if result:  # 只在有数据时保存
                save_to_json(result, output_file)

# 主函数
async def main(concurrency, category_group=None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(INITIAL_COOKIES)
        
        TOTAL_PAGES = await get_total_pages(context, category_group)
        logger.info(f"将抓取的总页数设置为：{TOTAL_PAGES}")
        
        pages_per_batch = max(1, TOTAL_PAGES // concurrency)
        OUTPUT_FILE = f"../cs_data/cs_{category_group}_{TIMESTAMP}.json"
        
        for i in range(0, TOTAL_PAGES, pages_per_batch):
            start_page = i + 1
            end_page = min(i + pages_per_batch, TOTAL_PAGES)
            logger.info(f"处理第 {start_page} 到 {end_page} 页")
            
            await scrape_pages_concurrently(start_page, end_page, concurrency, context, OUTPUT_FILE, category_group)
        
        await context.close()
        await browser.close()

# 运行程序
if __name__ == "__main__":
    CONCURRENCY = 2  # 并发数量
    # CATEGORY_GROUP = ["knife", "hands"]
    CATEGORY_GROUP = ["weapon_knife_butterfly"]
    for category in CATEGORY_GROUP:
        asyncio.run(main(CONCURRENCY, category))