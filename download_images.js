// 根据当前表格重新下载全部 ZOL 图片
const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');
const XLSX = require('/Users/a136/vs/WMPFDebugger-mac/node_modules/xlsx');

const IMG_DIR = '/Users/a136/vs/54725247/zol_images';
const THREADS = 30;

const wb = XLSX.readFile('/Users/a136/vs/54725247/匹配结果_ZOL报价.xlsx');
const data = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]]);

// 收集去重的下载任务
const tasks = [];
const seenFile = new Set();

data.forEach(row => {
    const url = String(row['ZOL图片'] || '').trim();
    if (!url || !url.startsWith('http')) return;

    const brand = String(row['品牌'] || '').replace(/[\/:*?"<>|\s]/g, '_');
    const model = String(row['机型'] || '').replace(/[\/:*?"<>|]/g, '_').replace(/\s+/g, '_');
    if (!model) return;

    const ext = path.extname(url.split('?')[0]) || '.jpg';
    const filename = `${brand}_${model}${ext}`;

    if (seenFile.has(filename)) return;
    seenFile.add(filename);
    tasks.push({ url, filename });
});

console.log(`需要下载: ${tasks.length} 张图片`);

function download(task) {
    return new Promise((resolve) => {
        const filePath = path.join(IMG_DIR, task.filename);
        const mod = task.url.startsWith('https') ? https : http;
        const req = mod.get(task.url, {
            timeout: 15000,
            headers: {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': 'https://detail.zol.com.cn/',
            }
        }, (res) => {
            if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                download({ ...task, url: res.headers.location }).then(resolve);
                return;
            }
            if (res.statusCode !== 200) {
                resolve({ ok: false, file: task.filename, error: `HTTP ${res.statusCode}` });
                return;
            }
            const ws = fs.createWriteStream(filePath);
            res.pipe(ws);
            ws.on('finish', () => { ws.close(); resolve({ ok: true, file: task.filename }); });
            ws.on('error', (e) => resolve({ ok: false, file: task.filename, error: e.message }));
        });
        req.on('error', (e) => resolve({ ok: false, file: task.filename, error: e.message }));
        req.on('timeout', () => { req.destroy(); resolve({ ok: false, file: task.filename, error: 'timeout' }); });
    });
}

async function runPool(tasks, concurrency) {
    let idx = 0, done = 0, success = 0, fail = 0;
    const total = tasks.length, start = Date.now();

    async function worker() {
        while (idx < total) {
            const i = idx++;
            const r = await download(tasks[i]);
            done++;
            if (r.ok) success++; else fail++;
            if (done % 100 === 0 || done === total) {
                const s = ((Date.now() - start) / 1000).toFixed(1);
                console.log(`[${done}/${total}] 成功:${success} 失败:${fail} | ${s}s`);
            }
        }
    }

    await Promise.all(Array.from({ length: concurrency }, () => worker()));
    console.log(`\n完成！成功:${success} 失败:${fail}`);
    console.log(`图片: ${IMG_DIR}`);
}

runPool(tasks, THREADS);
