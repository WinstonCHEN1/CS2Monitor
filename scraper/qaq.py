import asyncio
from playwright.async_api import async_playwright
import logging
import json
from datetime import datetime
import os
from lxml import html

# 根URL
BASE_URL = "https://csqaq.com/detail"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def get_item_data(page):
    """获取单个饰品的详细信息"""
    try:
        content = await page.content()
        tree = html.fromstring(content)

        today_changes = tree.xpath("//div[contains(text(),'今日')]/..//span//text()")
        today_change = ''.join([text.strip() for text in today_changes if text.strip()]) if today_changes else None

        week_changes = tree.xpath("//div[contains(text(),'本周')]/..//span//text()")
        week_change = ''.join([text.strip() for text in week_changes if text.strip()]) if week_changes else None

        buff_price_elements = tree.xpath("(//div[@class='plat_sub___UxEG0'])[1]/text()")
        buff_price = buff_price_elements[0].strip() if buff_price_elements else None

        uu_price_elements = tree.xpath("(//div[@class='plat_sub___UxEG0'])[3]/text()")
        uu_price = uu_price_elements[0].strip() if uu_price_elements else None

        return {
            "today_change": today_change,
            "week_change": week_change,
            "buff_price": buff_price,
            "uu_price": uu_price
        }
    except Exception as e:
        logger.error(f"获取饰品数据时出错：{str(e)}")
        return None

def load_existing_data(filename):
    """加载已存在的数据"""
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(filename, data):
    """保存数据到文件"""
    # 确保目录存在
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def scroll_to_bottom(page):
    """滚动到页面底部"""
    last_height = await page.evaluate("document.body.scrollHeight")
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(2)  # 等待新内容加载
        
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

async def fetch_item_data(item_type, semaphore):
    async with semaphore:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"../cs_data/qaq_{item_type}_{timestamp}.json"
        
        all_items_data = load_existing_data(filename)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            await context.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())
            page = await context.new_page()
            await page.set_viewport_size({"width": 1366, "height": 768})
            await page.route("**/*", lambda route: route.continue_() if not route.request.resource_type in ["image", "media"] else route.abort())
            
            logger.info(f"正在访问页面：{BASE_URL}")
            await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_load_state("domcontentloaded")
            
            logger.info("点击筛选按钮...")
            await page.click("button:has-text('筛选')")
            await asyncio.sleep(1)
            
            logger.info(f"选择 {item_type}...")
            item_option = await page.wait_for_selector(f"//div[contains(text(),'{item_type}')]", timeout=5000)
            if item_option:
                await item_option.click()
                await asyncio.sleep(1)
            else:
                logger.error(f"未找到 {item_type} 选项")
                return
            
            logger.info("点击完成...")
            butterfly_option = await page.wait_for_selector("//span[contains(text(),'完 成')]", timeout=5000)
            if butterfly_option:
                await butterfly_option.click()
                await asyncio.sleep(1)
            else:
                logger.error("点击不到完成")
                return
            
            await page.wait_for_selector("div.ant-card:has-text('￥')", timeout=10000)
            processed_items = set(all_items_data.keys())
            
            while True:
                cards = await page.query_selector_all("div.ant-card:has-text('￥')")
                logger.info(f"找到 {len(cards)} 个包含￥符号的卡片")
                
                new_items_found = False
                
                for i, card in enumerate(cards):
                    try:
                        item_name = await card.evaluate("""(card) => {
                            const span = card.querySelector('span');
                            return span ? span.textContent.trim() : null;
                        }""")
                        
                        if not item_name or item_name in processed_items:
                            continue
                        
                        logger.info(f"正在处理饰品：{item_name}")
                        
                        async with context.expect_page() as new_page_info:
                            await card.click()
                        new_page = await new_page_info.value
                        
                        await new_page.wait_for_load_state("networkidle")
                        await new_page.wait_for_load_state("domcontentloaded")
                        
                        item_data = await get_item_data(new_page)
                        if item_data:
                            all_items_data[item_name] = item_data
                            processed_items.add(item_name)
                            new_items_found = True
                            save_data(filename, all_items_data)
                            logger.info(f"已保存数据到：{filename}")
                    
                        await new_page.close()
                        
                    except Exception as e:
                        logger.error(f"处理第 {i+1} 个卡片时出错：{str(e)}")
                        continue
                
                if not new_items_found:
                    await scroll_to_bottom(page)
                    new_cards = await page.query_selector_all("div.ant-card:has-text('￥')")
                    if len(new_cards) == len(cards):
                        logger.info("没有新内容加载，爬取完成")
                        break
                    cards = new_cards
            
            await page.close()
            await context.close()
            await browser.close()

async def main(item_types=["蝴蝶刀"], concurrency=5):
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [fetch_item_data(item_type, semaphore) for item_type in item_types]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    item_types = ["蝴蝶刀", "音乐盒", "运动手套"]  # 添加需要抓取的饰品类型
    concurrency = 5  # 设置并发数量
    asyncio.run(main(item_types, concurrency))