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
        # 获取页面 HTML 内容
        content = await page.content()
        tree = html.fromstring(content)

        # 获取今日涨跌的所有 span 文本并拼接
        today_changes = tree.xpath("//div[contains(text(),'今日')]/..//span//text()")
        today_change = ''.join([text.strip() for text in today_changes if text.strip()]) if today_changes else None

        # 获取本周涨跌的所有 span 文本并拼接
        week_changes = tree.xpath("//div[contains(text(),'本周')]/..//span//text()")
        week_change = ''.join([text.strip() for text in week_changes if text.strip()]) if week_changes else None

        # 获取BUFF在售价格
        buff_price_elements = tree.xpath("(//div[@class='plat_sub___UxEG0'])[1]/text()")
        buff_price = buff_price_elements[0].strip() if buff_price_elements else None

        # 获取悠悠在售价格
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

async def main():

    # 设置数据文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"../cs/qaq_butterfly_{timestamp}.json"
    
    # 加载已存在的数据
    all_items_data = load_existing_data(filename)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # 设置路由规则，阻止所有图片加载
        await context.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())
        
        # 设置页面加载策略，不加载图片
        page = await context.new_page()
        await page.set_viewport_size({"width": 1366, "height": 768})
        
        # 设置请求拦截，阻止图片加载
        await page.route("**/*", lambda route: route.continue_() if not route.request.resource_type in ["image", "media"] else route.abort())
        
        logger.info(f"正在访问页面：{BASE_URL}")
        await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        
        # 等待页面加载完成
        await page.wait_for_load_state("networkidle")
        await page.wait_for_load_state("domcontentloaded")
        
        # 点击筛选按钮
        logger.info("点击筛选按钮...")
        await page.click("button:has-text('筛选')")
        await asyncio.sleep(1)
        
        # 使用XPath定位并点击蝴蝶刀选项
        logger.info("选择蝴蝶刀...")
        butterfly_option = await page.wait_for_selector("//div[contains(text(),'蝴蝶刀')]", timeout=5000)
        if butterfly_option:
            await butterfly_option.click()
            await asyncio.sleep(1)
        else:
            logger.error("未找到蝴蝶刀选项")
            return
        
        # 使用XPath定位并点击蝴蝶刀选项
        logger.info("点击完成...")
        butterfly_option = await page.wait_for_selector("//span[contains(text(),'完 成')]", timeout=5000)
        if butterfly_option:
            await butterfly_option.click()
            await asyncio.sleep(1)
        else:
            logger.error("点击不到完成")
            return
        
        # 等待￥符号出现
        await page.wait_for_selector("div.ant-card:has-text('￥')", timeout=10000)
        
        # 记录已处理的饰品名称
        processed_items = set(all_items_data.keys())
        
        while True:
            # 查找所有包含￥符号的卡片
            cards = await page.query_selector_all("div.ant-card:has-text('￥')")
            logger.info(f"找到 {len(cards)} 个包含￥符号的卡片")
            
            new_items_found = False
            
            # 遍历所有卡片
            for i, card in enumerate(cards):
                try:
                    # 获取饰品名称
                    item_name = await card.evaluate("""(card) => {
                        const span = card.querySelector('span');
                        return span ? span.textContent.trim() : null;
                    }""")
                    
                    if not item_name or item_name in processed_items:
                        continue
                    
                    logger.info(f"正在处理饰品：{item_name}")
                    
                    # 点击卡片
                    async with context.expect_page() as new_page_info:
                        await card.click()
                    new_page = await new_page_info.value
                    
                    # 等待详情页加载完成
                    await new_page.wait_for_load_state("networkidle")
                    await new_page.wait_for_load_state("domcontentloaded")
                    
                    # 获取饰品数据
                    item_data = await get_item_data(new_page)
                    if item_data:
                        all_items_data[item_name] = item_data
                        processed_items.add(item_name)
                        new_items_found = True
                        
                        # 增量保存数据
                        save_data(filename, all_items_data)
                        logger.info(f"已保存数据到：{filename}")
                    # 关闭详情页
                    await new_page.close()
                    
                except Exception as e:
                    logger.error(f"处理第 {i+1} 个卡片时出错：{str(e)}")
                    continue
            
            if not new_items_found:
                # 尝试滚动页面
                await scroll_to_bottom(page)
                # 检查是否有新内容加载
                new_cards = await page.query_selector_all("div.ant-card:has-text('￥')")
                if len(new_cards) == len(cards):
                    logger.info("没有新内容加载，爬取完成")
                    break
                cards = new_cards
        
        await page.close()
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())