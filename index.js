#!/usr/bin/env node
/**
 * 数码回收网报价工具
 *
 * 功能：
 *   1. 爬取小程序全部分类报价（不依赖小程序，直接HTTP请求）
 *   2. 爬取ZOL手机主图+市场价
 *   3. 匹配客户表格，生成最终结果
 *   4. 多线程下载主图
 *
 * 用法：
 *   node index.js                 # 执行全部流程
 *   node index.js scrape          # 只爬取小程序报价
 *   node index.js zol             # 只爬取ZOL数据
 *   node index.js match           # 只匹配（需要先爬取）
 *   node index.js download        # 只下载图片
 */

const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');

// ============ 配置 ============
const CONFIG = {
    // 客户表格
    INPUT_FILE: path.join(__dirname, '副本leupload (12)(1).xls'),
    // 输出
    OUTPUT_FILE: path.join(__dirname, '匹配结果_ZOL报价.xlsx'),
    OUTPUT_PRICES_JSON: path.join(__dirname, 'data', 'all_prices.json'),
    OUTPUT_CATEGORIES_JSON: path.join(__dirname, 'data', 'all_categories.json'),
    ZOL_CACHE: path.join(__dirname, 'zol_products_cache.json'),
    IMG_DIR: path.join(__dirname, 'zol_images'),
    // 小程序报价
    XCX_HASH: 'eJ9NdVl',
    XCX_BASE_URL: 'https://smbjd.smhsw.com/index/make/indexV2',
    XCX_BATCH_SIZE: 10,
    // ZOL
    ZOL_LIST_URL: 'https://detail.zol.com.cn/cell_phone_index/subcate57_0_list_1_0_1_2_0_{page}.html',
    ZOL_TOTAL_PAGES: 91,
    ZOL_THREADS: 10,
    // 下载
    DOWNLOAD_THREADS: 30,
};

// 确保 data 目录存在
const dataDir = path.join(__dirname, 'data');
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

// ============ 依赖加载 ============
let XLSX;
try {
    XLSX = require('xlsx');
} catch (e) {
    // 尝试从 WMPFDebugger-mac 加载
    try {
        XLSX = require('/Users/a136/vs/WMPFDebugger-mac/node_modules/xlsx');
    } catch (e2) {
        console.error('请先安装 xlsx: npm install xlsx');
        process.exit(1);
    }
}

// ============ 工具函数 ============
function fetchUrl(url, headers = {}) {
    return new Promise((resolve, reject) => {
        const mod = url.startsWith('https') ? https : http;
        const req = mod.get(url, {
            timeout: 30000,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                ...headers,
            },
        }, (res) => {
            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                fetchUrl(res.headers.location, headers).then(resolve, reject);
                return;
            }
            let data = '';
            res.setEncoding('utf8');
            res.on('data', chunk => data += chunk);
            res.on('end', () => resolve(data));
        });
        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
    });
}

function downloadFile(url, filePath) {
    return new Promise((resolve) => {
        const mod = url.startsWith('https') ? https : http;
        const req = mod.get(url, {
            timeout: 15000,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': 'https://detail.zol.com.cn/',
            },
        }, (res) => {
            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                downloadFile(res.headers.location, filePath).then(resolve);
                return;
            }
            if (res.statusCode !== 200) {
                resolve(false);
                return;
            }
            const ws = fs.createWriteStream(filePath);
            res.pipe(ws);
            ws.on('finish', () => { ws.close(); resolve(true); });
            ws.on('error', () => resolve(false));
        });
        req.on('error', () => resolve(false));
        req.on('timeout', () => { req.destroy(); resolve(false); });
    });
}

async function runPool(tasks, concurrency, fn) {
    let idx = 0, done = 0, success = 0, fail = 0;
    const total = tasks.length, start = Date.now();
    async function worker() {
        while (idx < total) {
            const i = idx++;
            const ok = await fn(tasks[i], i, total);
            done++;
            if (ok) success++; else fail++;
            if (done % 100 === 0 || done === total) {
                const s = ((Date.now() - start) / 1000).toFixed(1);
                console.log(`  [${done}/${total}] 成功:${success} 失败:${fail} | ${s}s`);
            }
        }
    }
    await Promise.all(Array.from({ length: concurrency }, () => worker()));
    return { success, fail };
}

function normalize(s) {
    if (!s) return '';
    return String(s).toLowerCase().replace(/\s+/g, '').trim();
}

function normMem(s) {
    if (!s) return '';
    return String(s).toLowerCase().replace(/\s+/g, '')
        .replace('1tg', '1tb').replace(/^1t$/, '1tb').trim();
}

function today() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// ============ 1. 小程序报价爬取 ============
function parseProductsFromHtml(html) {
    const products = [];
    const regex = /JSON\.parse\('(\[.*?\])'\)/gs;
    let match;
    while ((match = regex.exec(html)) !== null) {
        try {
            let jsonStr = match[1].replace(/\\'/g, "'").replace(/\\n/g, '\n').replace(/\\t/g, '\t');
            const data = JSON.parse(jsonStr);
            if (Array.isArray(data) && data.length > 0 && data[0].recovery_serie_id !== undefined) {
                data.forEach(serie => {
                    if (serie.products && serie.products.col) {
                        serie.products.col.forEach(colGroup => {
                            colGroup.forEach(group => {
                                if (group.child) {
                                    group.child.forEach(product => {
                                        const item = {
                                            series: serie.series_name,
                                            sub_category: group.one_level_sub_category_name || '',
                                        };
                                        for (const [key, val] of Object.entries(product)) {
                                            if (key === '型号') item.model = val.title;
                                            else if (key === '排序') { item.product_id = val.product_id; item.sort = val.title; }
                                            else if (key === '网络型号') item.network = val.title;
                                            else if (typeof val === 'object' && val !== null && val.store_price !== undefined) {
                                                item[key + '_store'] = val.store_price;
                                                item[key + '_deliver'] = val.deliver_price;
                                                if (!item.sku_names) item.sku_names = [];
                                                item.sku_names.push(key);
                                            }
                                        }
                                        if (item.model) products.push(item);
                                    });
                                }
                            });
                        });
                    }
                });
            }
        } catch (e) { /* ignore */ }
    }
    return products;
}

async function scrapeXcxPrices() {
    console.log('\n========== 爬取小程序报价 ==========');
    const date = today();

    // 加载分类
    let categories;
    if (fs.existsSync(CONFIG.OUTPUT_CATEGORIES_JSON)) {
        categories = JSON.parse(fs.readFileSync(CONFIG.OUTPUT_CATEGORIES_JSON, 'utf8'));
    } else {
        // 从小程序首页获取分类（需要先通过 CDP 获取，这里用已保存的）
        const catFile = path.join(path.dirname(CONFIG.OUTPUT_PRICES_JSON), '..', '..', 'WMPFDebugger-mac', 'all_categories.json');
        if (fs.existsSync(catFile)) {
            categories = JSON.parse(fs.readFileSync(catFile, 'utf8'));
            fs.writeFileSync(CONFIG.OUTPUT_CATEGORIES_JSON, JSON.stringify(categories, null, 2));
        } else {
            console.error('分类文件不存在，请先通过 WMPFDebugger 获取分类列表');
            return [];
        }
    }

    console.log(`分类数: ${categories.length}, 日期: ${date}`);
    const allProducts = [];
    const batchSize = CONFIG.XCX_BATCH_SIZE;

    for (let i = 0; i < categories.length; i += batchSize) {
        const batch = categories.slice(i, i + batchSize);
        const results = await Promise.all(batch.map(async (cat, j) => {
            const url = `${CONFIG.XCX_BASE_URL}/catId/${cat.offer_cat_id}/hash/${CONFIG.XCX_HASH}/store_id/0//history_date/${date}/points/0`;
            try {
                const html = await fetchUrl(url);
                const products = parseProductsFromHtml(html);
                console.log(`  [${i + j + 1}/${categories.length}] ${cat.cat_name}: ${products.length}`);
                return products.map(p => ({ ...p, category: cat.cat_name, top_category: cat.top_category, offer_cat_id: cat.offer_cat_id }));
            } catch (e) {
                console.log(`  [${i + j + 1}/${categories.length}] ${cat.cat_name} ERROR: ${e.message}`);
                return [];
            }
        }));
        results.forEach(r => allProducts.push(...r));
        if (i + batchSize < categories.length) await new Promise(r => setTimeout(r, 300));
    }

    console.log(`\n小程序报价总计: ${allProducts.length} 个产品`);
    fs.writeFileSync(CONFIG.OUTPUT_PRICES_JSON, JSON.stringify(allProducts, null, 2));
    return allProducts;
}

// ============ 2. 匹配逻辑 ============
const TYPE_MAP = {
    '靓机回收报价': '新机靓机报价',
    '废旧手机回收报价': '环保手机报价',
    '手表报价/靓机平板': '新机靓机报价',
    '数码相机回收报价': '数码相机报价',
    '环保品牌平板': '电脑主机报价',
    '废旧手机内配回收报价': '手机内配报价',
    '电子产品杂货铺报价': '电子杂货报价',
    '笔记本电脑/平板回收报价': '电脑主机报价',
    '台式电脑报价': '电脑主机报价',
};

function buildPriceIndex(priceData) {
    const index = {};
    priceData.forEach(p => {
        const brand = normalize(p.category);
        const model = normalize(p.model);
        const mem = normMem(p.sub_category);
        const topCat = p.top_category;
        const prices = {};
        Object.keys(p).forEach(k => {
            if (k.endsWith('_store')) prices[k.replace('_store', '')] = p[k];
        });
        if (p.sku_names) prices._skuNames = p.sku_names;
        const key = `${topCat}|${brand}|${model}|${mem}`;
        if (!index[key]) index[key] = prices;
        if (!mem) {
            const k2 = `${topCat}|${brand}|${model}|`;
            if (!index[k2]) index[k2] = prices;
        }
    });
    return index;
}

function findPrices(priceIndex, clientType, clientBrand, clientModel, mem) {
    const topCat = TYPE_MAP[clientType] || clientType;
    const brand = normalize(clientBrand);
    const model = normalize(clientModel);
    const memNorm = normMem(mem);

    let brandVariants = [brand];
    if (brand === '苹果' && topCat === '新机靓机报价') brandVariants = ['苹果有保', '苹果无保'];

    const modelVariants = [
        model, model + '5g', model.replace('5g', ''),
        model.replace('8p', '8plus'), model.replace('7p', '7plus'),
        model.replace('6sp', '6splus'), model.replace('iphone苹果x', 'iphonex'),
    ];

    // 精确匹配
    for (const mv of modelVariants) {
        for (const bv of brandVariants) {
            const bvNorm = normalize(bv);
            for (const key of [`${topCat}|${bvNorm}|${mv}|${memNorm}`, `${topCat}|${bvNorm}|${mv}|`]) {
                if (priceIndex[key]) return priceIndex[key];
            }
        }
    }

    // 模糊匹配（包含关系）
    for (const mv of modelVariants) {
        for (const bv of brandVariants) {
            const bvNorm = normalize(bv);
            for (const key of Object.keys(priceIndex)) {
                const parts = key.split('|');
                if (parts[0] === topCat && parts[1] === bvNorm) {
                    const im = parts[2], imem = parts[3];
                    if ((im.includes(mv) || mv.includes(im)) && im.length > 3) {
                        if (!memNorm || imem === memNorm || !imem) return priceIndex[key];
                    }
                }
            }
        }
    }
    return null;
}

function matchAndMerge(priceData) {
    console.log('\n========== 匹配报价到客户表格 ==========');

    // 读取客户表（带ZOL数据的版本或原始版本）
    let inputFile = CONFIG.OUTPUT_FILE;
    if (!fs.existsSync(inputFile)) inputFile = CONFIG.INPUT_FILE;
    const wb = XLSX.readFile(inputFile);
    const rawData = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]]);
    console.log(`客户表: ${rawData.length} 行`);

    const priceIndex = buildPriceIndex(priceData);
    console.log(`报价索引: ${Object.keys(priceIndex).length} 条`);

    let matched = 0;
    const outputRows = [];

    rawData.forEach(row => {
        const clientType = String(row['类型'] || '');
        const clientBrand = String(row['品牌'] || '');
        const clientModel = String(row['机型'] || '');
        const clientMem = String(row['内存'] || row['内存'] || '');
        const mems = clientMem && clientMem !== 'undefined' ? clientMem.split(',').map(m => m.trim()) : [''];

        mems.forEach(mem => {
            const prices = findPrices(priceIndex, clientType, clientBrand, clientModel, mem);
            const outRow = {
                '类型': clientType,
                '类型id': row['id'] || row['类型id'] || '',
                '品牌': clientBrand,
                '品牌id': row['id2'] || row['id.1'] || row['品牌id'] || '',
                '机型': clientModel,
                '机型id': row['id3'] || row['id.2'] || row['机型id'] || '',
                '内存': mem || '',
                'ZOL报价': row['ZOL报价'] || '',
                'ZOL图片': row['ZOL图片'] || '',
                'ZOL链接': row['ZOL链接'] || '',
                'ZOL匹配': row['ZOL匹配'] || row['匹配状态'] || '',
                'SKU1名称': '', 'SKU1回收价': '',
                'SKU2名称': '', 'SKU2回收价': '',
                'SKU3名称': '', 'SKU3回收价': '',
                'SKU4名称': '', 'SKU4回收价': '',
                'SKU5名称': '', 'SKU5回收价': '',
                'SKU6名称': '', 'SKU6回收价': '',
                '小程序匹配': '未匹配',
            };

            if (prices) {
                matched++;
                outRow['小程序匹配'] = '已匹配';
                const skuNames = prices._skuNames || Object.keys(prices).filter(k => !k.startsWith('_'));
                skuNames.forEach((sku, i) => {
                    if (i < 6 && prices[sku] !== undefined) {
                        outRow[`SKU${i + 1}名称`] = sku;
                        outRow[`SKU${i + 1}回收价`] = prices[sku];
                    }
                });
            }
            outputRows.push(outRow);
        });
    });

    console.log(`匹配结果: ${matched} 行有价格 / ${outputRows.length} 总行`);

    // 写入
    const outWb = XLSX.utils.book_new();
    const outWs = XLSX.utils.json_to_sheet(outputRows);
    XLSX.utils.book_append_sheet(outWb, outWs, 'Sheet1');
    XLSX.writeFile(outWb, CONFIG.OUTPUT_FILE);
    console.log(`已保存: ${CONFIG.OUTPUT_FILE}`);
    return outputRows;
}

// ============ 3. 图片下载 ============
async function downloadImages() {
    console.log('\n========== 下载ZOL图片 ==========');
    if (!fs.existsSync(CONFIG.IMG_DIR)) fs.mkdirSync(CONFIG.IMG_DIR, { recursive: true });

    const wb = XLSX.readFile(CONFIG.OUTPUT_FILE);
    const data = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]]);

    const tasks = [];
    const seenFile = new Set();
    const existing = new Set(fs.readdirSync(CONFIG.IMG_DIR));

    data.forEach(row => {
        const url = String(row['ZOL图片'] || '').trim();
        if (!url || !url.startsWith('http')) return;
        const brand = String(row['品牌'] || '').replace(/[\/:*?"<>|\s]/g, '_');
        const model = String(row['机型'] || '').replace(/[\/:*?"<>|]/g, '_').replace(/\s+/g, '_');
        if (!model) return;
        const ext = path.extname(url.split('?')[0]) || '.jpg';
        const filename = `${brand}_${model}${ext}`;
        if (seenFile.has(filename) || existing.has(filename)) return;
        seenFile.add(filename);
        tasks.push({ url, filename });
    });

    console.log(`需要下载: ${tasks.length} 张（已有: ${existing.size} 张）`);
    if (tasks.length === 0) { console.log('所有图片已就绪'); return; }

    const result = await runPool(tasks, CONFIG.DOWNLOAD_THREADS, async (task) => {
        return downloadFile(task.url, path.join(CONFIG.IMG_DIR, task.filename));
    });
    console.log(`下载完成: 成功 ${result.success}, 失败 ${result.fail}`);
}

// ============ 主流程 ============
async function main() {
    const cmd = process.argv[2] || 'all';
    console.log(`数码回收网报价工具 - ${today()}`);
    console.log(`命令: ${cmd}\n`);

    if (cmd === 'scrape' || cmd === 'all') {
        await scrapeXcxPrices();
    }

    if (cmd === 'match' || cmd === 'all') {
        let priceData;
        if (fs.existsSync(CONFIG.OUTPUT_PRICES_JSON)) {
            priceData = JSON.parse(fs.readFileSync(CONFIG.OUTPUT_PRICES_JSON, 'utf8'));
        } else {
            console.error('请先运行 scrape 爬取报价数据');
            process.exit(1);
        }
        matchAndMerge(priceData);
    }

    if (cmd === 'download' || cmd === 'all') {
        if (!fs.existsSync(CONFIG.OUTPUT_FILE)) {
            console.error('请先运行 match 生成匹配结果');
            process.exit(1);
        }
        await downloadImages();
    }

    if (cmd === 'zol') {
        console.log('ZOL爬取请运行: python3 scrape_zol_fast.py');
    }

    console.log('\n========== 完成 ==========');
}

main().catch(console.error);
