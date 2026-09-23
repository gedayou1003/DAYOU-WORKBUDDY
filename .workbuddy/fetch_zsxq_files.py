#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识星球附件（PDF/docx）下载 + 正文抽取，供报告撰写前入库。
## 为什么要有这个脚本

2026-09-21 晨报复盘时发现：`fetch_zsxq.py::extract_files()` 刻意
**「不下载，仅记录元数据」**（只留 `file_id` / `name` / `size`），
于是报告第一块只能写「附件 X 个」+ 文件名列表 ——
**投行研报的正文从来没进过上下文**。当天因此漏掉一整条医药主线：
基业长青+ 推的医药研报正文里有关键结论，而报告只字未提。
用户随后把它列为交接给下一档的强制整改项④。

本脚本补齐「下载 + 抽正文」这一环。

## 退出码语义（与全仓约定一致）

    0  全部附件已读（正文抽取成功）
    1  ERROR：有附件下载失败 / 抽取崩栈 / 参数非法 —— 报告不得声称「已读全部」
    2  WARN ：下载与抽取都跑了，但**部分附件无文本层**（扫描版 PDF 等），
             这部分只能算「未读」，报告须如实写明「已读 N / 未读 M」

**职责判定**（2026-09-23 加固技能第三原则）：本脚本的职责是「让附件正文可被读取」。
如果 11 个附件里 8 个抽不出文字却退 0，报告就会在**毫不知情**的情况下漏主线 ——
这比崩栈更危险。因此「未读」必须进退出码（走 WARN=2），不能只 print。

## 用法

    python fetch_zsxq_files.py                    # 默认今日，读主快照
    python fetch_zsxq_files.py --list             # 只列附件，不下载
    python fetch_zsxq_files.py --snapshot X.json  # 指定快照
    python fetch_zsxq_files.py --outdir D         # 指定输出目录
    python fetch_zsxq_files.py --force            # 已下载的也重下
    python fetch_zsxq_files.py --only 储能        # 只处理名字含「储能」的

## 产物

    <outdir>/<file_id>_<安全化后的原名>.pdf
    <outdir>/<file_id>.txt                —— 抽取出的正文（UTF-8）
    <outdir>/_files_manifest.json         —— 逐附件状态（已读/未读/失败 + 原因）
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except Exception:  # silent-ok: 终端编码收口尽力而为，失败不影响结论
        pass

_HERE = os.path.dirname(os.path.abspath(__file__))
COOKIE_FILE = os.path.join(_HERE, 'zsxq_cookie.txt')
DEFAULT_SNAPSHOT = os.path.join(_HERE, 'zsxq_fetch_raw.json')
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 抽取出的正文低于这个字数，视为「无文本层」（扫描版/纯图片 PDF）
MIN_TEXT_CHARS = 50

# 「正文真的可读吗」判据 —— 光看**字数**会放出一种假绿（2026-09-23 实测踩到）：
#   野村《中国医疗健康》附件是 7 页扫描版，pypdf 只抽出一串**水印文字层**：
#     '1IzBWGiAoU8YaY8ObP9PoMqQtRtNjMrRyRiNpNqRaQoPqQuOtRmMMYmOnR'
#   共 58 字 —— 刚刚越过 MIN_TEXT_CHARS=50，于是被记成 **[已读]**。
#   报告据此写「已读 11 / 未读 0」，而这份研报实际上**一个字都没进上下文**。
#   （讽刺的是：这正是 9/21 漏医药那条事故本身——同一份附件第二次骗过闸门。）
# 因此改判**内容 token 数**：
#   中文按字计（每个汉字 = 1），拉丁按词计（长度 ≥2 的字母串 = 1）。
#   水印串那种「一个 58 字母的长 token」只算 1，必然判未读。
MIN_TOKENS = 30


def content_tokens(text):
    """把抽取文本折算成「可读内容 token 数」：汉字逐字 + 拉丁词逐词"""
    cjk = 0
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff':
            cjk += 1
    latin = len(re.findall(r'[A-Za-z]{2,}', text))
    return cjk + latin

# Windows 文件名非法字符
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _cookie():
    if not os.path.isfile(COOKIE_FILE):
        sys.stderr.write('[FAIL] 找不到 Cookie 文件：%s\n' % COOKIE_FILE)
        sys.stderr.write('       附件下载需要登录态，请先补 zsxq_cookie.txt\n')
        return None
    txt = open(COOKIE_FILE, encoding='utf-8').read().strip()
    if not txt:
        sys.stderr.write('[FAIL] Cookie 文件为空：%s\n' % COOKIE_FILE)
        return None
    return txt


def _safe_name(name, limit=80):
    """把附件原名安全化为可用文件名（保留中文与全角符号，只去非法字符）"""
    s = _ILLEGAL.sub('_', name or 'unnamed')
    s = s.strip().strip('.')
    if len(s) > limit:
        stem, ext = os.path.splitext(s)
        s = stem[:limit - len(ext)] + ext
    return s or 'unnamed'


def _api_json(url, cookie, timeout=30):
    """GET 一个返回 JSON 的 API，返回 (data|None, err_str|None)"""
    req = urllib.request.Request(url, headers={
        'Cookie': cookie, 'User-Agent': UA,
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://wx.zsxq.com', 'Referer': 'https://wx.zsxq.com/',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8')), None
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None, 'HTTP %d 鉴权失败（Cookie 已失效）' % e.code
        return None, 'HTTP %d' % e.code
    except Exception as e:
        return None, '%s: %s' % (type(e).__name__, e)


def get_download_url(file_id, cookie, retries=4):
    """取附件签名下载地址。返回 (url|None, err|None)

    2026-09-23 实测（本脚本首跑踩到）：该接口会对**单个 file_id 随机**返回
    `succeeded=false` + `error="内部错误"`，且响应体里夹带一段「获取内容，稳定可靠
    👉 garden.zsxq.com/skill/」的推广文案 —— 这是软限流，不是权限问题：
    同一 file_id 连查 4 次全成功、隔几秒再查又全失败，与请求参数无关。

    旧实现（本函数初版）把这种情况笼统报成「接口未返回 succeeded=true」，
    丢失了接口自称的错误原因，也**不做重试** —— 实测导致 11 个附件里 2 个
    无谓失败（野村那份 2MB 的研报被误判为下不到）。现改为：
      ① 退避重试，抖动只是抖动；
      ② 报错时优先透出接口自带的 `error` 字段，让「内部错误」和「文件已删除」
         这类本质不同的原因在日志里可分辨（否则运维只能靠猜）。
    """
    last = None
    for attempt in range(retries):
        d, err = _api_json('https://api.zsxq.com/v2/files/%s/download_url' % file_id, cookie)
        if err:
            last = err
            # 鉴权失败重试无意义，立即返回
            if '鉴权失败' in err:
                return None, err
        elif not isinstance(d, dict) or not d.get('succeeded'):
            api_err = (d or {}).get('error') if isinstance(d, dict) else None
            last = '接口 error=%r' % (api_err or '未提供')
            if api_err and api_err != '内部错误':
                # 「内部错误」是软限流可重试；其它 error（文件不存在/无权限）重试也无用
                return None, last
        else:
            url = (d.get('resp_data') or {}).get('download_url')
            if url:
                if attempt:
                    sys.stdout.write('    [retry-ok] 第 %d 次尝试拿到下载地址（软限流抖动）\n'
                                     % (attempt + 1))
                return url, None
            last = 'resp_data 里没有 download_url'
        if attempt < retries - 1:
            time.sleep(2 + attempt * 2)      # 2s / 4s / 6s
    return None, '%s（已重试 %d 次）' % (last, retries)


def download_file(url, save_path, cookie):
    """下载到 save_path（先写 .part 再原子替换，避免半截文件被当成已下载）"""
    tmp = save_path + '.part'
    req = urllib.request.Request(url, headers={
        'Cookie': cookie, 'User-Agent': UA, 'Referer': 'https://wx.zsxq.com/',
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        if len(data) < 1024:
            return None, '响应体过小（%d 字节，疑似错误页）' % len(data)
        # 粗略校验 PDF 魔数；扩展名与内容不符时如实报出，不静默接受
        head = data[:5]
        if save_path.lower().endswith('.pdf') and head != b'%PDF-':
            return None, '扩展名为 .pdf 但响应头不是 %%PDF-（实际 %r）' % head
        if save_path.lower().endswith('.docx') and head[:2] != b'PK':
            return None, '扩展名为 .docx 但响应头不是 PK zip（实际 %r）' % head
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, save_path)
        return save_path, None
    except Exception as e:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:  # silent-ok: 清临时文件失败不影响本次结论（真失败已由下面的 return 报出）
            pass
        return None, '%s: %s' % (type(e).__name__, e)


def extract_docx_text(path):
    """抽取 .docx 正文。返回 (text, pages, err|None)

    docx 的正文就是 zip 里的 `word/document.xml`，用 zipfile + 标签剥离即可，
    无需 python-docx 依赖（少一个必须装的东西，就少一处「未安装 → 静默跳过」的风险）。

    2026-09-23 补：上一窗口（9/21 晨报，40 个附件）里有 8 个 `.mp3` + 8 个
    `_原文.docx` 成对出现（专家组电话会纪要）—— 整改口径允许 mp3 只记标题，
    但 **docx 是纯文本、必须读**，否则等于把「会议纪要」整类内容排除在外。
    """
    import re as _re
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if 'word/document.xml' not in names:
                return '', 0, '不是标准 docx（zip 内缺 word/document.xml，实含 %d 项：%s）' \
                    % (len(names), ', '.join(names[:5]))
            xml = z.read('word/document.xml').decode('utf-8', errors='replace')
    except Exception as e:
        return '', 0, '%s: %s' % (type(e).__name__, e)
    # <w:p> 段落 → 换行；<w:tab/> → 制表；其余标签一律剥掉
    xml = _re.sub(r'</w:p>', '\n', xml)
    xml = _re.sub(r'<w:tab\b[^>]*/>', '\t', xml)
    xml = _re.sub(r'<w:br\b[^>]*/>', '\n', xml)
    text = _re.sub(r'<[^>]+>', '', xml)
    # 反转义（docx 正文里 &amp; 一类是常态）
    for a, b in (('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&apos;', "'"),
                 ('&amp;', '&')):
        text = text.replace(a, b)
    text = _re.sub(r'\n{3,}', '\n\n', text)
    # pages 对 docx 无意义，用段落数（按行数近似）承载，便于简报可读
    return text, len([x for x in text.split('\n') if x.strip()]), None


def extract_pdf_text(path):
    """抽取 PDF 正文。返回 (text, pages, err|None)"""
    try:
        from pypdf import PdfReader
    except ImportError:
        return '', 0, 'pypdf 未安装（pip install pypdf）'
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            # 空密码尝试解密；解不开就如实报，不返回半截正文
            try:
                if reader.decrypt('') == 0:
                    return '', len(reader.pages), 'PDF 已加密且空密码无法解密'
            except Exception as e:
                return '', len(reader.pages), 'PDF 解密失败：%s' % e
        pages = len(reader.pages)
        chunks = []
        for i, pg in enumerate(reader.pages):
            try:
                t = pg.extract_text() or ''
            except Exception as e:
                # 单页失败不该毁掉整份文档，但必须留痕（不静默吞）
                t = ''
                chunks.append('\n[第 %d 页抽取失败：%s]\n' % (i + 1, e))
            if t.strip():
                chunks.append(t)
        text = '\n'.join(chunks)
        return text, pages, None
    except Exception as e:
        return '', 0, '%s: %s' % (type(e).__name__, e)


# 可抽文本的扩展名 → 抽取函数
_TEXT_EXTRACTORS = {
    '.pdf': extract_pdf_text,
    '.docx': extract_docx_text,
}
# 按整改口径「mp3 可只记标题」的纯二进制附件（不算失败，但必须计未读）
_AUDIO_LIKE = ('.mp3', '.m4a', '.wav', '.aac', '.zip', '.rar', '.7z',
               '.xlsx', '.xls', '.pptx', '.ppt', '.png', '.jpg', '.jpeg')


def extract_text(path):
    """按扩展名分派抽取。返回 (text, pages, err|None)

    不认识 / 不可抽的扩展名**不返回 err**（那不是错误），而是返回空文本，
    由调用方按「未读」计数 —— 这样退出码走 WARN(2) 而非 ERROR(1)，
    语义上区分「环境故障」与「这份附件本来就是音频」。
    """
    ext = os.path.splitext(path)[1].lower()
    fn = _TEXT_EXTRACTORS.get(ext)
    if fn:
        return fn(path)
    if ext in _AUDIO_LIKE:
        return '', 0, None          # 由 main 按 _AUDIO_LIKE 判为「未读（音频/二进制）」
    return '', 0, None              # 未知扩展名同样计未读，不误报为失败


def load_snapshot(path):
    """读抓取快照，返回附件条目列表。返回 (items|None, err|None)"""
    if not os.path.isfile(path):
        return None, '找不到快照文件：%s' % path
    try:
        raw = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        return None, '快照不是合法 JSON：%s' % e
    if not isinstance(raw, list):
        return None, '快照顶层应为 list（实为 %s）—— 结构变了，请先核对 fetch_zsxq.py' % type(raw).__name__
    items, seen = [], set()
    for t in raw:
        for f in (t.get('files') or []):
            fid = str(f.get('file_id') or '').strip()
            if not fid:
                # 没有 file_id 就没法下载 —— 出声，不静默跳过
                sys.stderr.write('[WARN] 有一条附件没有 file_id，已跳过：%r @ %s\n'
                                 % (f.get('name'), t.get('group')))
                continue
            if fid in seen:      # 同附件被转发到多星球时只处理一次
                continue
            seen.add(fid)
            items.append({
                'file_id': fid,
                'name': f.get('name', ''),
                'size': f.get('size', 0),
                'group': t.get('group', ''),
                'topic_id': t.get('topic_id'),
                'create_time': t.get('create_time', ''),
            })
    return items, None


def parse_args(argv):
    """返回 (opts dict, err|None)"""
    o = {'date': None, 'snapshot': DEFAULT_SNAPSHOT, 'outdir': None,
         'force': False, 'do_list': False, 'only': None}
    i, positional = 0, []
    while i < len(argv):
        a = argv[i]
        if a in ('-h', '--help'):
            return o, 'HELP'
        if a == '--snapshot':
            if i + 1 >= len(argv):
                return None, '--snapshot 缺少取值'
            o['snapshot'] = argv[i + 1]
            i += 2
            continue
        if a == '--outdir':
            if i + 1 >= len(argv):
                return None, '--outdir 缺少取值'
            o['outdir'] = argv[i + 1]
            i += 2
            continue
        if a == '--only':
            if i + 1 >= len(argv):
                return None, '--only 缺少取值'
            o['only'] = argv[i + 1]
            i += 2
            continue
        if a == '--force':
            o['force'] = True
            i += 1
            continue
        if a == '--list':
            o['do_list'] = True
            i += 1
            continue
        if a.startswith('-'):
            return None, '未知参数 %r' % a
        positional.append(a)
        i += 1
    if len(positional) > 1:
        return None, '最多接受一个位置参数（日期），收到 %d 个：%r' % (len(positional), positional)
    if positional:
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', positional[0]):
            return None, '日期格式应为 YYYY-MM-DD，收到 %r' % positional[0]
        o['date'] = positional[0]
    return o, None


def main(argv):
    opts, err = parse_args(argv)
    if err == 'HELP':
        sys.stdout.write(__doc__)
        return 0
    if err:
        sys.stderr.write('[FAIL] 参数错误：%s\n' % err)
        sys.stderr.write('       用法见 python fetch_zsxq_files.py -h\n')
        return 1

    date = opts['date'] or time.strftime('%Y-%m-%d')
    outdir = opts['outdir'] or os.path.join(_HERE, 'zsxq_files', date)

    items, err = load_snapshot(opts['snapshot'])
    if err:
        sys.stderr.write('[FAIL] %s\n' % err)
        return 1
    if opts['only']:
        # 支持逗号分隔多关键词（2026-09-23 补）：单关键词时多次调用会把 manifest
        # 覆盖成「只有最后一个文件」的子集 —— 多个附件要一起取证时台账就失真了。
        keys = [k.strip() for k in opts['only'].split(',') if k.strip()]
        if not keys:
            sys.stderr.write('[FAIL] --only 取值为空（应为关键词，或用逗号分隔多个）\n')
            return 1
        items = [x for x in items if any(k in x['name'] for k in keys)]
        if not items:
            sys.stderr.write('[FAIL] --only %r 没有匹配到任何附件\n' % opts['only'])
            return 1

    if not items:
        sys.stdout.write('[OK] 快照内没有附件，无需处理（date=%s）\n' % date)
        return 0

    sys.stdout.write('附件总数：%d（date=%s）\n' % (len(items), date))
    if opts['do_list']:
        for n, x in enumerate(items, 1):
            sys.stdout.write('  #%-2d %-22s %8.1f KB  %s\n'
                             % (n, x['group'], x['size'] / 1024.0, x['name']))
        return 0

    cookie = _cookie()
    if not cookie:
        return 1

    try:
        os.makedirs(outdir, exist_ok=True)
    except Exception as e:
        sys.stderr.write('[FAIL] 无法创建输出目录 %s：%s\n' % (outdir, e))
        return 1

    recs = []
    for n, x in enumerate(items, 1):
        fid, name = x['file_id'], x['name']
        local_path = os.path.join(outdir, '%s_%s' % (fid, _safe_name(name)))
        txt_path = os.path.join(outdir, '%s.txt' % fid)
        ext = os.path.splitext(name)[1].lower()
        rec = dict(x)
        rec.update({'pdf_path': local_path, 'txt_path': txt_path, 'ext': ext,
                    'status': '', 'reason': '', 'pages': 0, 'chars': 0, 'tokens': 0})

        # 1) 下载（已存在且非 --force 则复用）
        if os.path.isfile(local_path) and not opts['force']:
            rec['download'] = 'reuse'
            sys.stdout.write('  #%-2d [复用] %s\n' % (n, name[:60]))
        else:
            url, derr = get_download_url(fid, cookie)
            if derr:
                rec.update({'status': 'failed', 'reason': '取下载地址失败：%s' % derr,
                            'download': 'fail'})
                recs.append(rec)
                sys.stderr.write('  #%-2d [FAIL] %s —— %s\n' % (n, name[:50], derr))
                continue
            p, derr = download_file(url, local_path, cookie)
            if derr:
                rec.update({'status': 'failed', 'reason': '下载失败：%s' % derr,
                            'download': 'fail'})
                recs.append(rec)
                sys.stderr.write('  #%-2d [FAIL] %s —— %s\n' % (n, name[:50], derr))
                continue
            rec['download'] = 'ok'
            time.sleep(0.4)      # 轻微限速，避免连拉 11 个大文件触发限流

        # 2) 抽取正文
        #    不可抽的扩展名（mp3 等）在这里走「未读」而非「失败」——不是故障，
        #    是整改口径明确允许的「音频只记标题」。但**必须计入未读**，
        #    否则报告会以为它读过了（这正是 9/21 漏医药那条事故的同一类错误）。
        if ext not in _TEXT_EXTRACTORS:
            rec.update({'status': 'unread',
                        'reason': '%s 不在可抽文本类型内（按整改口径只记标题）' % (ext or '无扩展名')})
            sys.stderr.write('  #%-2d [未读] %s —— %s\n' % (n, name[:50], rec['reason']))
            recs.append(rec)
            continue

        text, pages, eerr = extract_text(local_path)
        rec['pages'] = pages
        rec['chars'] = len(text.strip())
        rec['tokens'] = content_tokens(text)
        if eerr:
            rec.update({'status': 'failed', 'reason': '抽取失败：%s' % eerr})
            sys.stderr.write('  #%-2d [FAIL] %s —— 抽取失败：%s\n' % (n, name[:50], eerr))
            recs.append(rec)
            continue
        if rec['chars'] < MIN_TEXT_CHARS or rec['tokens'] < MIN_TOKENS:
            rec.update({'status': 'unread',
                        'reason': '无有效文本层（%d %s / %d 字 / 仅 %d 个内容单元，'
                                  '疑为扫描版或只有水印文字层）'
                                  % (pages, '页' if ext == '.pdf' else '段',
                                     rec['chars'], rec['tokens'])})
            sys.stderr.write('  #%-2d [未读] %s —— %s\n' % (n, name[:50], rec['reason']))
            recs.append(rec)
            continue

        try:
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception as e:
            rec.update({'status': 'failed', 'reason': '正文写盘失败：%s' % e})
            sys.stderr.write('  #%-2d [FAIL] %s —— 正文写盘失败：%s\n' % (n, name[:50], e))
            recs.append(rec)
            continue

        rec.update({'status': 'read',
                    'reason': '%d %s / %d 字 / %d 内容单元'
                              % (pages, '页' if ext == '.pdf' else '段',
                                 rec['chars'], rec['tokens'])})
        sys.stdout.write('  #%-2d [已读] %-50s %s\n' % (n, name[:50], rec['reason']))
        recs.append(rec)

    # 3) 落 manifest
    n_read = sum(1 for r in recs if r['status'] == 'read')
    n_unread = sum(1 for r in recs if r['status'] == 'unread')
    n_failed = sum(1 for r in recs if r['status'] == 'failed')
    manifest = {
        'date': date,
        'snapshot': os.path.abspath(opts['snapshot']),
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'total': len(recs),
        'read': n_read,
        'unread': n_unread,
        'failed': n_failed,
        'records': recs,
    }
    mpath = os.path.join(outdir, '_files_manifest.json')
    try:
        with open(mpath, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
    except Exception as e:
        sys.stderr.write('[FAIL] manifest 写盘失败：%s\n' % e)
        return 1

    sys.stdout.write('附件简报: 已读 %d / 未读 %d / 失败 %d（共 %d）\n'
                     % (n_read, n_unread, n_failed, len(recs)))
    sys.stdout.write('manifest: %s\n' % mpath)

    if n_failed:
        sys.stderr.write('[FAIL] %d 个附件彻底没读到（下载或抽取失败），'
                         '报告不得声称「已读全部附件」\n' % n_failed)
        return 1
    if n_unread:
        sys.stderr.write('[WARN] %d 个附件未能取得正文（无文本层 / 音频等不可抽类型），'
                         '只能计为「未读」——报告第一块须写明'
                         '「已读 %d / 未读 %d」\n' % (n_unread, n_read, n_unread))
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
