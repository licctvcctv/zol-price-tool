#!/usr/bin/env python3
"""
ZOL手机报价爬虫 - 爬取中关村在线手机报价和主图
功能：
1. 爬取ZOL所有手机列表页的型号、价格、图片
2. 与Excel表格中的机型进行匹配
3. 输出匹配结果到新的Excel文件
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import os
import json
from urllib.parse import urljoin

# ============ 配置 ============
INPUT_FILE = "副本leupload (12)(1).xls"
OUTPUT_FILE = "匹配结果_ZOL报价.xlsx"
ZOL_IMAGE_DIR = "zol_images"  # 主图保存目录
BASE_URL = "https://detail.zol.com.cn"
LIST_URL_TEMPLATE = "https://detail.zol.com.cn/cell_phone_index/subcate57_0_list_1_0_1_2_0_{page}.html"
TOTAL_PAGES = 91  # ZOL手机列表总页数
DELAY = 1.0  # 请求间隔（秒）

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://detail.zol.com.cn/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

session = requests.Session()
session.headers.update(HEADERS)


def fetch_page(url, retries=3):
    """请求页面，带重试"""
    for i in range(retries):
        try:
            r = session.get(url, timeout=15)
            r.encoding = 'gbk'
            return r.text
        except Exception as e:
            print(f"  请求失败 ({i+1}/{retries}): {e}")
            time.sleep(2)
    return None


def parse_list_page(html):
    """解析列表页，提取手机信息"""
    soup = BeautifulSoup(html, 'html.parser')
    products = []

    ul = soup.select_one('#J_PicMode')
    if not ul:
        return products

    for li in ul.select('li[data-follow-id]'):
        try:
            product = {}

            # 型号名称
            h3_a = li.select_one('h3 a')
            if h3_a:
                # 只取型号，不要描述span
                title = h3_a.get('title', '') or h3_a.get_text(strip=True)
                # 去掉span部分
                span = h3_a.select_one('span')
                if span:
                    title = title.replace(span.get_text(), '').strip()
                product['名称'] = title.strip()

            # 价格
            price_el = li.select_one('.price-type')
            if price_el:
                product['ZOL报价'] = price_el.get_text(strip=True)

            # 图片URL
            img = li.select_one('a.pic img')
            if img:
                img_url = img.get('.src') or img.get('src') or img.get('data-src', '')
                if img_url and not img_url.startswith('http'):
                    img_url = 'https:' + img_url
                product['图片URL'] = img_url

            # 详情页链接
            link_a = li.select_one('a.pic')
            if link_a:
                href = link_a.get('href', '')
                if href and not href.startswith('http'):
                    if href.startswith('//'):
                        href = 'https:' + href
                    else:
                        href = BASE_URL + href
                product['详情链接'] = href

            # 产品ID
            product['产品ID'] = li.get('data-follow-id', '').replace('p', '')

            if product.get('名称'):
                products.append(product)
        except Exception as e:
            print(f"  解析产品出错: {e}")
            continue

    return products


def scrape_all_pages(max_pages=None):
    """爬取所有列表页"""
    all_products = []
    pages = max_pages or TOTAL_PAGES

    for page in range(1, pages + 1):
        if page == 1:
            url = "https://detail.zol.com.cn/cell_phone_index/subcate57_list_1.html"
        else:
            url = LIST_URL_TEMPLATE.format(page=page)

        print(f"[{page}/{pages}] 正在爬取: {url}")
        html = fetch_page(url)
        if not html:
            print(f"  第{page}页获取失败，跳过")
            continue

        products = parse_list_page(html)
        print(f"  获取到 {len(products)} 个产品")
        all_products.extend(products)

        if page < pages:
            time.sleep(DELAY)

    print(f"\n总共爬取 {len(all_products)} 个产品")
    return all_products


def normalize_name(name):
    """标准化名称用于匹配"""
    if not name:
        return ''
    name = str(name).strip()
    # 统一大小写
    name = name.upper()
    # 去掉空格
    name = re.sub(r'\s+', ' ', name)
    # 统一一些常见变体
    name = name.replace('（', '(').replace('）', ')')
    return name


def extract_model_core(name):
    """提取型号核心部分（去掉内存配置等）"""
    name = normalize_name(name)
    # 去掉括号内的内存信息 如 (12GB/256GB)
    name = re.sub(r'\(\d+GB/\d+[GT]B\)', '', name)
    # 去掉括号内的存储信息 如 (256GB)
    name = re.sub(r'\(\d+[GT]B\)', '', name)
    return name.strip()


def match_products(excel_df, zol_products):
    """将Excel中的机型与ZOL爬取的产品进行匹配
    匹配策略：
    1. 精确匹配核心型号（去掉内存后）
    2. 模糊匹配（型号关键词包含）
    每个Excel机型会匹配到ZOL中所有内存版本（最低价）
    """
    # 构建ZOL产品索引
    zol_index = {}  # 标准化名称 -> 产品
    zol_core_index = {}  # 核心型号 -> [产品列表]

    for p in zol_products:
        norm = normalize_name(p['名称'])
        zol_index[norm] = p

        core = extract_model_core(p['名称'])
        if core not in zol_core_index:
            zol_core_index[core] = []
        zol_core_index[core].append(p)

    # 品牌名映射（Excel品牌 -> ZOL中常用的品牌前缀）
    brand_map = {
        '苹果': ['苹果', 'APPLE', 'IPHONE'],
        '华为': ['HUAWEI', '华为'],
        '华为旗舰': ['HUAWEI', '华为'],
        '小米': ['小米', 'XIAOMI', 'MI'],
        '红米、黑鲨': ['REDMI', '红米', '黑鲨'],
        'VIVO': ['VIVO'],
        'OPPO': ['OPPO'],
        'iQOO': ['IQOO'],
        '荣耀': ['荣耀', 'HONOR'],
        '荣耀其他': ['荣耀', 'HONOR'],
        '一加': ['一加', 'ONEPLUS'],
        '三星': ['三星', 'SAMSUNG', 'GALAXY'],
        '真我/realme': ['REALME', '真我'],
        '魅族': ['魅族', 'MEIZU'],
        '努比亚': ['努比亚', 'NUBIA'],
        '联想': ['联想', 'LENOVO'],
        '摩托罗拉': ['摩托罗拉', 'MOTOROLA', 'MOTO'],
    }

    matched = 0
    results = []

    for _, row in excel_df.iterrows():
        brand = str(row.get('品牌', ''))
        model = str(row.get('机型', ''))
        memory = str(row.get('内存', ''))

        result = row.to_dict()
        result['ZOL报价'] = ''
        result['ZOL图片'] = ''
        result['ZOL链接'] = ''
        result['匹配状态'] = '未匹配'

        if not model or model == 'nan':
            results.append(result)
            continue

        model_norm = normalize_name(model)
        match_found = False
        best_match = None

        # 策略1: 精确核心型号匹配
        for core_name, prods in zol_core_index.items():
            if model_norm == core_name or model_norm in core_name:
                # 检查不是子串误匹配（如 "13" 匹配到 "13 PRO MAX"）
                # 确保型号词边界匹配
                if model_norm in core_name:
                    # 检查型号后面不是更长的型号（如 IPHONE 16 不应匹配 IPHONE 16 PRO）
                    remaining = core_name.replace(model_norm, '').strip()
                    # 如果剩余部分含有 PRO/MAX/PLUS/MINI 等型号后缀，说明不是精确匹配
                    if remaining and re.search(r'(PRO|MAX|PLUS|MINI|ULTRA|LITE|SE|NOTE)', remaining):
                        continue

                # 选价格最低的版本
                def safe_price(x):
                    p = x.get('ZOL报价', '')
                    try:
                        return int(p)
                    except (ValueError, TypeError):
                        return 999999
                best = min(prods, key=safe_price)
                best_match = best
                match_found = True
                break

        # 策略2: 品牌前缀 + 型号匹配
        if not match_found:
            brand_prefixes = brand_map.get(brand, [])
            for zol_name, zol_prod in zol_index.items():
                zol_core = extract_model_core(zol_prod['名称'])
                # 检查品牌
                brand_ok = not brand_prefixes  # 如果没有映射，跳过品牌检查
                for prefix in brand_prefixes:
                    if prefix.upper() in zol_name:
                        brand_ok = True
                        break
                if not brand_ok:
                    continue

                # 型号包含匹配
                if model_norm in zol_core:
                    remaining = zol_core.replace(model_norm, '').strip()
                    if remaining and re.search(r'(PRO|MAX|PLUS|MINI|ULTRA|LITE|SE|NOTE)', remaining):
                        continue
                    best_match = zol_prod
                    match_found = True
                    break

        # 策略3: 更宽松的模糊匹配 - 关键词匹配
        if not match_found:
            # 把型号拆成关键词
            keywords = [w for w in model_norm.split() if len(w) > 1]
            if keywords:
                best_score = 0
                for zol_name, zol_prod in zol_index.items():
                    # 品牌过滤
                    brand_prefixes = brand_map.get(brand, [])
                    if brand_prefixes:
                        brand_ok = any(p.upper() in zol_name for p in brand_prefixes)
                        if not brand_ok:
                            continue
                    score = sum(1 for kw in keywords if kw in zol_name)
                    if score > best_score and score >= len(keywords) * 0.7:
                        best_score = score
                        best_match = zol_prod
                        match_found = True

        if match_found and best_match:
            result['ZOL报价'] = best_match.get('ZOL报价', '')
            result['ZOL图片'] = best_match.get('图片URL', '')
            result['ZOL链接'] = best_match.get('详情链接', '')
            result['匹配状态'] = '已匹配'
            matched += 1

        results.append(result)

    print(f"\n匹配结果: {matched}/{len(excel_df)} 个机型匹配成功")
    return pd.DataFrame(results)


def download_image(url, save_path):
    """下载图片"""
    try:
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(r.content)
            return True
    except Exception as e:
        print(f"  下载图片失败: {e}")
    return False


def download_matched_images(result_df):
    """下载所有匹配到的产品主图"""
    os.makedirs(ZOL_IMAGE_DIR, exist_ok=True)

    matched = result_df[result_df['匹配状态'] == '已匹配']
    total = len(matched)
    downloaded = 0

    for idx, row in matched.iterrows():
        img_url = row.get('ZOL图片', '')
        model = str(row.get('机型', 'unknown'))
        if not img_url:
            continue

        # 安全文件名
        safe_name = re.sub(r'[^\w\-.]', '_', model)
        ext = os.path.splitext(img_url.split('?')[0])[-1] or '.jpg'
        save_path = os.path.join(ZOL_IMAGE_DIR, f"{safe_name}{ext}")

        if os.path.exists(save_path):
            downloaded += 1
            continue

        print(f"  [{downloaded+1}/{total}] 下载: {model}")
        if download_image(img_url, save_path):
            downloaded += 1
        time.sleep(0.3)

    print(f"\n下载完成: {downloaded}/{total} 张图片")


def get_detail_page_image(detail_url):
    """从详情页获取高清主图"""
    html = fetch_page(detail_url)
    if not html:
        return None
    soup = BeautifulSoup(html, 'html.parser')
    # 尝试多种选择器获取主图
    for selector in ['#J_ImgBooth img', '.product-summary-pic img', '.big-pic img']:
        img = soup.select_one(selector)
        if img:
            src = img.get('src') or img.get('data-src', '')
            if src and not src.startswith('http'):
                src = 'https:' + src
            return src
    return None


def main():
    print("=" * 60)
    print("ZOL 手机报价爬虫")
    print("=" * 60)

    # 1. 读取Excel
    print(f"\n[1] 读取Excel: {INPUT_FILE}")
    df = pd.read_excel(INPUT_FILE)
    print(f"  共 {len(df)} 行数据, {df['机型'].nunique()} 个独立机型")

    # 2. 爬取ZOL（支持从缓存加载）
    zol_cache_file = "zol_products_cache.json"
    if os.path.exists(zol_cache_file):
        print(f"\n[2] 从缓存加载ZOL数据: {zol_cache_file}")
        with open(zol_cache_file, 'r', encoding='utf-8') as f:
            zol_products = json.load(f)
        print(f"  加载了 {len(zol_products)} 个产品")
    else:
        print(f"\n[2] 开始爬取ZOL手机报价 (共{TOTAL_PAGES}页)...")
        zol_products = scrape_all_pages()
        with open(zol_cache_file, 'w', encoding='utf-8') as f:
            json.dump(zol_products, f, ensure_ascii=False, indent=2)
        print(f"  ZOL数据已缓存到: {zol_cache_file}")

    # 3. 匹配
    print(f"\n[3] 进行型号匹配...")
    result_df = match_products(df, zol_products)

    # 4. 保存结果
    print(f"\n[4] 保存匹配结果到: {OUTPUT_FILE}")
    result_df.to_excel(OUTPUT_FILE, index=False)
    print(f"  完成!")

    # 5. 下载主图
    print(f"\n[5] 下载匹配到的产品主图...")
    download_matched_images(result_df)

    # 统计
    print("\n" + "=" * 60)
    print("爬取完成! 统计:")
    print(f"  ZOL产品总数: {len(zol_products)}")
    print(f"  Excel机型数: {len(df)}")
    matched_count = len(result_df[result_df['匹配状态'] == '已匹配'])
    print(f"  匹配成功: {matched_count}")
    print(f"  匹配率: {matched_count/len(df)*100:.1f}%")
    print(f"  结果文件: {OUTPUT_FILE}")
    print(f"  图片目录: {ZOL_IMAGE_DIR}/")
    print("=" * 60)


if __name__ == '__main__':
    main()
