#!/usr/bin/env python3
"""
ZOL手机报价爬虫 - 多线程加速版
使用线程池并发爬取，速度提升5-10倍
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# ============ 配置 ============
INPUT_FILE = "副本leupload (12)(1).xls"
OUTPUT_FILE = "匹配结果_ZOL报价.xlsx"
ZOL_IMAGE_DIR = "zol_images"
BASE_URL = "https://detail.zol.com.cn"
LIST_URL_TEMPLATE = "https://detail.zol.com.cn/cell_phone_index/subcate57_0_list_1_0_1_2_0_{page}.html"
TOTAL_PAGES = 91
THREADS_PAGES = 10   # 爬列表页的并发数
THREADS_IMAGES = 20  # 下载图片的并发数

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://detail.zol.com.cn/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

print_lock = Lock()


def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)


def create_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_page(url, retries=3):
    s = create_session()
    for i in range(retries):
        try:
            r = s.get(url, timeout=15)
            r.encoding = 'gbk'
            return r.text
        except Exception as e:
            if i == retries - 1:
                safe_print(f"  请求失败: {url} - {e}")
            time.sleep(1)
    return None


def parse_list_page(html):
    soup = BeautifulSoup(html, 'html.parser')
    products = []
    ul = soup.select_one('#J_PicMode')
    if not ul:
        return products

    for li in ul.select('li[data-follow-id]'):
        try:
            product = {}
            h3_a = li.select_one('h3 a')
            if h3_a:
                title = h3_a.get('title', '') or h3_a.get_text(strip=True)
                span = h3_a.select_one('span')
                if span:
                    title = title.replace(span.get_text(), '').strip()
                product['名称'] = title.strip()

            price_el = li.select_one('.price-type')
            if price_el:
                product['ZOL报价'] = price_el.get_text(strip=True)

            img = li.select_one('a.pic img')
            if img:
                img_url = img.get('.src') or img.get('src') or img.get('data-src', '')
                if img_url and not img_url.startswith('http'):
                    img_url = 'https:' + img_url
                product['图片URL'] = img_url

            link_a = li.select_one('a.pic')
            if link_a:
                href = link_a.get('href', '')
                if href and not href.startswith('http'):
                    href = 'https:' + href if href.startswith('//') else BASE_URL + href
                product['详情链接'] = href

            product['产品ID'] = li.get('data-follow-id', '').replace('p', '')

            if product.get('名称'):
                products.append(product)
        except Exception:
            continue
    return products


def fetch_and_parse_page(page):
    """爬取单页并解析（供线程池调用）"""
    if page == 1:
        url = "https://detail.zol.com.cn/cell_phone_index/subcate57_list_1.html"
    else:
        url = LIST_URL_TEMPLATE.format(page=page)

    html = fetch_page(url)
    if not html:
        safe_print(f"  [{page}/{TOTAL_PAGES}] 失败")
        return []

    products = parse_list_page(html)
    safe_print(f"  [{page}/{TOTAL_PAGES}] {len(products)} 个产品")
    return products


def scrape_all_pages_parallel():
    """多线程爬取所有列表页"""
    all_products = []
    safe_print(f"  使用 {THREADS_PAGES} 个线程并发爬取...")

    with ThreadPoolExecutor(max_workers=THREADS_PAGES) as executor:
        futures = {executor.submit(fetch_and_parse_page, p): p for p in range(1, TOTAL_PAGES + 1)}
        for future in as_completed(futures):
            try:
                products = future.result()
                all_products.extend(products)
            except Exception as e:
                safe_print(f"  线程异常: {e}")

    safe_print(f"\n  总共爬取 {len(all_products)} 个产品")
    return all_products


def normalize_name(name):
    if not name:
        return ''
    name = str(name).strip().upper()
    name = re.sub(r'\s+', ' ', name)
    name = name.replace('（', '(').replace('）', ')')
    return name


def extract_model_core(name):
    name = normalize_name(name)
    # 去掉各种括号内的规格信息: (8GB/128GB/全网通/5G版) 等
    name = re.sub(r'\([^)]*GB[^)]*\)', '', name)
    name = re.sub(r'\(\d+[GT]B\)', '', name)
    name = re.sub(r'\([^)]*全网通[^)]*\)', '', name)
    name = re.sub(r'\([^)]*5G[^)]*\)', '', name)
    name = re.sub(r'\([^)]*版[^)]*\)', '', name)
    return name.strip()


def safe_price(x):
    p = x.get('ZOL报价', '')
    try:
        return int(p)
    except (ValueError, TypeError):
        return 999999


def compact(s):
    """去掉所有空格，用于连写对比: 'Find X8 Pro' → 'FINDX8PRO'"""
    return re.sub(r'\s+', '', s).upper()


# 区分性后缀关键词 - 这些词改变了型号含义
DIFF_KEYWORDS = re.compile(r'(PRO|MAX|PLUS|MINI|ULTRA|LITE|SE|NOTE|FOLD|FLIP|PORSCHE|保时捷)')


def strip_brand(name):
    """去掉型号中的品牌前缀"""
    for prefix in ['苹果', 'APPLE ', 'IPHONE ', 'HUAWEI ', '华为', '小米', 'XIAOMI ',
                    'REDMI ', '红米', 'VIVO ', 'OPPO ', 'IQOO ', '荣耀', 'HONOR ',
                    '一加', 'ONEPLUS ', '三星', 'SAMSUNG ', 'GALAXY ', 'REALME ', '真我',
                    '魅族', 'MEIZU ', '努比亚', 'NUBIA ', '联想', 'LENOVO ',
                    '摩托罗拉', 'MOTOROLA ', 'MOTO ', '黑鲨', '锤子', 'SMARTISAN ',
                    '诺基亚', 'NOKIA ', '中兴', 'ZTE ', 'HTC ', '黑莓', 'BLACKBERRY ']:
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
    return name


def is_model_match(model_norm, zol_core):
    """型号匹配：支持连写/空格差异，但不允许区分性后缀不匹配"""
    if not model_norm or not zol_core:
        return False, ''

    # 完全相等
    if model_norm == zol_core:
        return True, ''

    # 去品牌后比较
    zol_clean = strip_brand(zol_core)
    model_clean = strip_brand(model_norm)

    if not model_clean or not zol_clean:
        return False, ''

    # 紧凑形式（去空格）比较
    mc = compact(model_clean)
    zc = compact(zol_clean)

    # 完全相等（去空格后）
    if mc == zc:
        return True, ''

    # zol 紧凑形式以 model 紧凑形式开头
    if zc.startswith(mc) and len(mc) >= 2:
        remaining = zc[len(mc):]
        # 剩余是 5G/4G 等无关后缀 → OK
        if not remaining or remaining in ('5G', '4G', '全网通'):
            return True, remaining
        # 剩余含区分性关键词 → 不匹配
        if DIFF_KEYWORDS.search(remaining):
            return False, remaining
        # 剩余是纯数字或单字母（可能是子型号如 S, E）→ 不匹配
        if re.match(r'^[A-Z0-9]$', remaining):
            return False, remaining
        # 剩余较短且无意义 → 接受
        if len(remaining) <= 2 and not remaining.isalnum():
            return True, remaining
        return False, remaining

    # model 紧凑形式以 zol 紧凑形式开头（客户写得更详细）
    if mc.startswith(zc) and len(zc) >= 2:
        remaining = mc[len(zc):]
        if not remaining or remaining in ('5G', '4G', '版'):
            return True, remaining
        # 客户多写了5G等后缀
        if re.match(r'^5G$', remaining):
            return True, remaining
        return False, remaining

    return False, ''


def match_products(excel_df, zol_products):
    zol_index = {}
    zol_core_index = {}

    for p in zol_products:
        norm = normalize_name(p['名称'])
        zol_index[norm] = p
        core = extract_model_core(p['名称'])
        if core not in zol_core_index:
            zol_core_index[core] = []
        zol_core_index[core].append(p)

    brand_map = {
        '苹果': ['苹果', 'APPLE', 'IPHONE'],
        '华为': ['HUAWEI', '华为'], '华为旗舰': ['HUAWEI', '华为'],
        '小米': ['小米', 'XIAOMI', 'MI'], '红米、黑鲨': ['REDMI', '红米', '黑鲨'],
        'VIVO': ['VIVO'], 'OPPO': ['OPPO'], 'iQOO': ['IQOO'],
        '荣耀': ['荣耀', 'HONOR'], '荣耀其他': ['荣耀', 'HONOR'],
        '一加': ['一加', 'ONEPLUS'], '三星': ['三星', 'SAMSUNG', 'GALAXY'],
        '真我/realme': ['REALME', '真我'], '魅族': ['魅族', 'MEIZU'],
        '努比亚': ['努比亚', 'NUBIA'], '联想': ['联想', 'LENOVO'],
        '摩托罗拉': ['摩托罗拉', 'MOTOROLA', 'MOTO'],
    }

    matched = 0
    results = []

    for _, row in excel_df.iterrows():
        brand = str(row.get('品牌', ''))
        model = str(row.get('机型', ''))

        result = row.to_dict()
        result['ZOL报价'] = ''
        result['ZOL图片'] = ''
        result['ZOL链接'] = ''
        result['匹配状态'] = '未匹配'

        if not model or model == 'nan':
            results.append(result)
            continue

        model_norm = normalize_name(model)
        brand_prefixes = brand_map.get(brand, [])
        best_match = None
        best_match_score = 0  # 越高越好

        # 策略1: 精确核心型号匹配（带品牌过滤）
        for core_name, prods in zol_core_index.items():
            # 先检查品牌
            if brand_prefixes:
                zol_norm = normalize_name(prods[0]['名称'])
                if not any(p.upper() in zol_norm for p in brand_prefixes):
                    continue

            ok, remaining = is_model_match(model_norm, core_name)
            if ok:
                candidate = min(prods, key=safe_price)
                # 计算匹配分数：完全匹配最高
                score = 100 - len(remaining)
                if score > best_match_score:
                    best_match_score = score
                    best_match = candidate

        # 策略2: 品牌+型号（用严格匹配函数）
        if not best_match:
            for zol_name, zol_prod in zol_index.items():
                if brand_prefixes and not any(p.upper() in zol_name for p in brand_prefixes):
                    continue
                zol_core = extract_model_core(zol_prod['名称'])
                ok, remaining = is_model_match(model_norm, zol_core)
                if ok:
                    score = 100 - len(remaining)
                    if score > best_match_score:
                        best_match_score = score
                        best_match = zol_prod

        # 策略3: 关键词匹配（加严：必须全部关键词都匹配，且需品牌校验）
        if not best_match:
            keywords = [w for w in model_norm.split() if len(w) > 1]
            if len(keywords) >= 2:  # 至少2个关键词才用模糊
                best_score = 0
                for zol_name, zol_prod in zol_index.items():
                    if brand_prefixes and not any(p.upper() in zol_name for p in brand_prefixes):
                        continue
                    score = sum(1 for kw in keywords if kw in zol_name)
                    # 要求所有关键词都匹配（不是70%）
                    if score == len(keywords) and score > best_score:
                        best_score = score
                        best_match = zol_prod

        if best_match:
            result['ZOL报价'] = best_match.get('ZOL报价', '')
            result['ZOL图片'] = best_match.get('图片URL', '')
            result['ZOL链接'] = best_match.get('详情链接', '')
            result['匹配状态'] = '已匹配'
            matched += 1

        results.append(result)

    print(f"\n  匹配结果: {matched}/{len(excel_df)} 个机型匹配成功")
    return pd.DataFrame(results)


def download_single_image(args):
    """下载单张图片（供线程池调用）"""
    img_url, save_path, model = args
    if os.path.exists(save_path):
        return True
    try:
        s = create_session()
        r = s.get(img_url, timeout=10)
        if r.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False


def download_matched_images_parallel(result_df):
    """多线程下载所有匹配到的产品主图"""
    os.makedirs(ZOL_IMAGE_DIR, exist_ok=True)
    matched = result_df[result_df['匹配状态'] == '已匹配']

    tasks = []
    for _, row in matched.iterrows():
        img_url = row.get('ZOL图片', '')
        model = str(row.get('机型', 'unknown'))
        if not img_url:
            continue
        safe_name = re.sub(r'[^\w\-.]', '_', model)
        ext = os.path.splitext(img_url.split('?')[0])[-1] or '.jpg'
        save_path = os.path.join(ZOL_IMAGE_DIR, f"{safe_name}{ext}")
        tasks.append((img_url, save_path, model))

    safe_print(f"  使用 {THREADS_IMAGES} 个线程并发下载 {len(tasks)} 张图片...")
    downloaded = 0

    with ThreadPoolExecutor(max_workers=THREADS_IMAGES) as executor:
        futures = {executor.submit(download_single_image, t): t for t in tasks}
        for future in as_completed(futures):
            if future.result():
                downloaded += 1
            if downloaded % 50 == 0 and downloaded > 0:
                safe_print(f"  已下载: {downloaded}/{len(tasks)}")

    safe_print(f"\n  下载完成: {downloaded}/{len(tasks)} 张图片")


def main():
    print("=" * 60)
    print("ZOL 手机报价爬虫 (多线程加速版)")
    print("=" * 60)

    # 1. 读取Excel
    print(f"\n[1] 读取Excel: {INPUT_FILE}")
    df = pd.read_excel(INPUT_FILE)
    print(f"  共 {len(df)} 行数据, {df['机型'].nunique()} 个独立机型")

    # 2. 爬取ZOL
    zol_cache_file = "zol_products_cache.json"
    if os.path.exists(zol_cache_file):
        print(f"\n[2] 从缓存加载ZOL数据: {zol_cache_file}")
        with open(zol_cache_file, 'r', encoding='utf-8') as f:
            zol_products = json.load(f)
        print(f"  加载了 {len(zol_products)} 个产品")
    else:
        print(f"\n[2] 多线程爬取ZOL手机报价 (共{TOTAL_PAGES}页)...")
        start = time.time()
        zol_products = scrape_all_pages_parallel()
        elapsed = time.time() - start
        print(f"  耗时: {elapsed:.1f}秒")
        with open(zol_cache_file, 'w', encoding='utf-8') as f:
            json.dump(zol_products, f, ensure_ascii=False, indent=2)

    # 3. 匹配
    print(f"\n[3] 进行型号匹配...")
    result_df = match_products(df, zol_products)

    # 4. 保存
    print(f"\n[4] 保存匹配结果到: {OUTPUT_FILE}")
    result_df.to_excel(OUTPUT_FILE, index=False)
    print(f"  完成!")

    # 5. 多线程下载主图
    print(f"\n[5] 多线程下载匹配到的产品主图...")
    start = time.time()
    download_matched_images_parallel(result_df)
    elapsed = time.time() - start
    print(f"  耗时: {elapsed:.1f}秒")

    # 统计
    print("\n" + "=" * 60)
    matched_count = len(result_df[result_df['匹配状态'] == '已匹配'])
    print(f"  ZOL产品: {len(zol_products)} | Excel机型: {len(df)}")
    print(f"  匹配成功: {matched_count} ({matched_count/len(df)*100:.1f}%)")
    print(f"  结果: {OUTPUT_FILE} | 图片: {ZOL_IMAGE_DIR}/")
    print("=" * 60)


if __name__ == '__main__':
    main()
