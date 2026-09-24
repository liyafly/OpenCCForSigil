"""Synthesize a realistic ~200-file, ~3 MB simplified-Chinese EPUB text set."""
import random

WORDS = """我们 这个 发展 国家 电脑 软件 网络 信息 学习 问题 时间 历史 经济 社会 文化 关系 应该 开始 已经
认为 东西 头发 后来 里面 面条 干净 干部 皇后 后面 这里 那里 为什么 怎么样 还是 进行 实现 专业 质量
电视 书籍 图书馆 医院 银行 车辆 飞机 铁路 广场 城市 农业 工业 历史学家 传统 现代 艺术 音乐 电影
乡村 风景 阳光 云彩 窗户 门口 墙壁 灯光 厨房 饭菜 茶叶 苹果 香蕉 鸡蛋 猪肉 鱼类 汤面 面包 蛋糕
朋友 老师 学生 医生 记者 律师 警察 军队 将军 皇帝 丞相 百姓 商人 农民 工人 儿童 妇女 老人 青年
说话 听见 看见 觉得 想起 回忆 忘记 爱情 愿望 梦想 希望 担心 害怕 高兴 难过 满意 惊讶 愤怒 平静
时候 地方 办法 样子 事情 声音 颜色 体会 经验 结论 观点 态度 感觉 条件 环境 资源 能源 技术 设备
发现 决定 选择 准备 参加 组织 领导 负责 处理 解决 讨论 调查 研究 分析 设计 开发 测试 发布 维护
台湾 香港 澳门 北京 上海 广州 深圳 杭州 南京 苏州 长江 黄河 泰山 华山 西湖 边疆 丝绸 之路
一个 两个 几个 许多 所有 每个 其他 另外 自己 别人 大家 他们 她们 你们 咱们 谁 什么 哪里 这样
的 了 着 过 和 与 及 或 但 而 因为 所以 虽然 如果 即使 只要 不过 于是 然后 并且 甚至 就是 只是
""".split()
PUNCT = ["，", "，", "，", "。", "。", "、", "；", "：", "！", "？"]
ALT = ["插图说明", "封面图片", "作者肖像", "历史地图", "统计图表", "风景照片"]


def sentence(rng, n=None):
    n = n or rng.randint(8, 22)
    body = "".join(rng.choice(WORDS) for _ in range(n))
    if rng.random() < 0.15:
        body = "“" + body + "”"
    return body + rng.choice(PUNCT)


def paragraph(rng, target_chars):
    out = []
    size = 0
    while size < target_chars:
        s = sentence(rng)
        out.append(s)
        size += len(s)
    return "".join(out)


def chapter(rng, index, han_budget):
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n',
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
        'xml:lang="zh-CN" lang="zh-CN">\n<head>\n<meta charset="utf-8"/>\n',
        f'<title>第{index}章 {sentence(rng, 3)}</title>\n',
        '<link href="../Styles/style.css" rel="stylesheet" type="text/css"/>\n</head>\n',
        f'<body class="chapter" id="ch{index:03d}" epub:type="bodymatter">\n',
        f'<section id="sec{index}" class="level1" epub:type="chapter" data-ch="{index}">\n',
        f'<h1 class="title" id="h{index}" title="{sentence(rng, 4)}">第{index}章　{sentence(rng, 4)}</h1>\n',
    ]
    used = 0
    p = 0
    while used < han_budget:
        p += 1
        roll = rng.random()
        if roll < 0.08:
            # ruby annotation paragraph
            rb = "".join(
                f'<ruby>{w}<rp>(</rp><rt>{"ㄓㄨˋ" if rng.random() < .5 else "zhù"}</rt><rp>)</rp></ruby>'
                for w in rng.sample(WORDS, 4))
            text = f'<p class="ruby" id="p{index}-{p}">{paragraph(rng, 60)}{rb}{paragraph(rng, 60)}</p>\n'
            used += 180
        elif roll < 0.12:
            rows = []
            for r in range(rng.randint(3, 8)):
                cells = "".join(
                    f'<td class="c{c}" title="{rng.choice(WORDS)}">{sentence(rng, 3)}</td>' for c in range(4))
                rows.append(f'<tr class="r{r}">{cells}</tr>')
            text = (f'<table class="data" id="t{index}-{p}" summary="{sentence(rng,4)}">'
                    f'<caption>{sentence(rng, 5)}</caption><tbody>{"".join(rows)}</tbody></table>\n')
            used += 60 * len(rows)
        elif roll < 0.15:
            text = (f'<div class="figure" id="f{index}-{p}"><img src="../Images/i{p}.jpg" '
                    f'alt="{rng.choice(ALT)}{sentence(rng,3)}" title="{sentence(rng,3)}" class="img" width="600" height="400"/>'
                    f'<p class="caption">{sentence(rng, 6)}</p></div>\n')
            used += 60
        elif roll < 0.18:
            text = (f'<blockquote class="quote"><p>{paragraph(rng, 120)}</p>'
                    f'<p class="src"><a href="../Text/notes.xhtml#n{p}" id="r{index}-{p}" class="noteref" '
                    f'epub:type="noteref">[{p}]</a></p></blockquote>\n')
            used += 130
        else:
            n = rng.randint(80, 260)
            body = paragraph(rng, n)
            if rng.random() < 0.3:
                cut = len(body) // 2
                body = (body[:cut] + f'<span class="em" lang="zh-CN" id="s{index}-{p}"><em>{sentence(rng,4)}</em></span>'
                        + body[cut:])
            if rng.random() < 0.05:
                body += '<code class="k">变量名称 = 数据</code>'
            text = f'<p class="indent" id="p{index}-{p}" data-idx="{p}">{body}</p>\n'
            used += n
        parts.append(text)
    parts.append("</section>\n</body>\n</html>\n")
    return "".join(parts)


def make_book(files=200, total_han=1_000_000, seed=20260924):
    rng = random.Random(seed)
    per = total_han // files
    return {f"ch{i:03d}": chapter(rng, i, int(per * rng.uniform(0.5, 1.5))) for i in range(files)}


if __name__ == "__main__":
    book = make_book()
    total = sum(len(v.encode()) for v in book.values())
    chars = sum(len(v) for v in book.values())
    han = sum(1 for v in book.values() for c in v if "一" <= c <= "鿿")
    print(len(book), "files", total, "bytes", chars, "chars", han, "han")
