"""Sort protected regional products into kinds of food by the last words of their names.

A product name is a place followed by a product word: 五常大米, 洛川苹果, 西湖龙井. The place
comes first, so the kind is read from the end of the name. Each kind below lists name endings;
the longest ending that fits wins, which lets 核桃 (a nut) beat 桃 (a fruit) and 腐乳 beat 乳.

Names the rules get wrong or cannot place are listed, one by one, in
data/overrides/product-kinds.json. Run this file to see how the current data sorts:

    python3 scripts/product_kinds.py
"""
import os
import re

from common import DATA_DIR, read_json

# Kinds in the order the page lists them. "other" is food the rules could not place more exactly.
KINDS = ["tea", "grain", "vegetable", "fruit", "nut", "meat", "aquatic", "drink", "condiment",
         "sweet", "herb", "prepared", "other", "not-food"]

ENDINGS = {
    "tea": """茶 茶叶 毛尖 毛峰 龙井 银针 瓜片 碧螺春 铁观音 大红袍 普洱 雀舌 翠芽 云雾 香尖 曲毫 白毫 松针
        猴魁 单丛 单枞 茗 剑毫 银毫 银芽 雪芽 仙芽 玉露 芽 尖 毫 祁红 滇红 宁红 宜红 川红 英红 闽红
        咖啡 咖啡豆""",
    "grain": """米 稻 稻谷 谷 谷子 麦 荞 玉米 苞米 苞谷 高粱 粱 青稞 稞 薏仁 薏苡 糯 黍 糜子 杂粮 面粉
        豆 黄豆 大豆 绿豆 红豆 黑豆 蚕豆 芸豆 豌豆 小豆 鹰嘴豆""",
    "vegetable": """菜 卜 薯 洋芋 土豆 地瓜 芋 芋头 芋艿 艿 蒜 蒜头 蒜薹 葱 姜 藕 藕带 笋 菇 蘑 菌 松茸
        羊肚菌 竹荪 耳 茄 茄子 番茄 西红柿 椒 黄瓜 冬瓜 南瓜 丝瓜 苦瓜 佛手瓜 瓠瓜 北瓜 葫芦 芹 韭 韭黄 薹
        椿 山药 淮山 怀山 合 茭白 荸荠 荠 慈姑 茨菇 姑 菱角 菱 豆角 四季豆 豇豆 扁豆 刀豆 毛豆 荷兰豆
        豆芽 黄花 西兰花 菜花 蓝 折耳根 鱼腥草 茼蒿 藜蒿 芦蒿 蒌蒿 粉葛 马兰 芥兰 莼 蕨 头""",
    "fruit": """果 梨 桃 桃子 萄 提 枣 瓜 橙 柚 桔 橘 柑 柠檬 李 李子 杏 莓 梅 荔枝 眼 桂圆 柿 柿子 柿饼
        榴 杷 楂 蕉 萝 凤梨 椰子 椰 椹 葚 橄榄 榄 棘 菠萝蜜 波罗蜜 蔗 文旦 黄皮 酸角 葡萄干 海棠 木瓜
        番木瓜 巨峰 娘""",
    "nut": """核桃 胡桃 栗 栗子 榛子 榛 松子 松籽 松仁 香榧 榧 杏仁 巴旦木 巴旦杏 白果 银杏 腰果 开心果
        夏威夷果 花生 生 花生米 瓜子 葵花 向日葵 籽 芝麻 胡麻 火麻 莲子 莲 莲米 芡实 核桃仁 花生仁""",
    "meat": """猪 鸡 鸭 鹅 牛 羊 兔 驴 鸽 鹌鹑 鹧鸪 雁 鸵鸟 鹿 驼 肉 肉干 火腿 腿 肠 肚 蹄 肘 板鸭 蛋 奶
        乳 乳扇 乳饼 奶酪 奶粉 奶皮 酥油""",
    "aquatic": """鱼 虾 蟹 贝 螺 蛤 蜊 蛏 蚝 牡蛎 蛎 蚬 蚌 蚶 鲍 海参 刺参 辽参 鳖 龟 鳅 鳝 蛙 鲤 鲫 鲈 鳜
        鲢 鳙 鲶 鲟 鳗 鲳 鳟 蜇 海带 紫菜 海菜 裙带菜 龙须菜 石花菜 苔 藻 海胆 虾米 海米 虾皮 虾仁
        鱼胶 花胶""",
    "drink": """酒 老窖 大曲 特曲 二锅头 老白干 白干 矿泉水 泉水 水 饮料 汁""",
    "condiment": """醋 酱油 酱 豆豉 腐乳 豆瓣 味精 盐 油 油茶 花椒 胡椒 藤椒 麻椒 八角 桂皮 肉桂 孜然 茴香
        草果 香叶 芥末 山葵 丁香 山奈 辣椒粉 胡椒粉 五香粉 豆蔻""",
    "sweet": """蜜 糖 蜂王浆 蜂胶 花粉 蜂""",
    "herb": """参 芪 归 枸杞 杞 枸杞子 三七 天麻 金银花 银花 艾 艾草 艾叶 贝母 母 川贝 浙贝 平贝 伊贝 芍
        芍药 苓 芝 斛 精 草 连 仲 朴 术 黄 菊 菊花 瑰 玫瑰花 桂花 红花 茉莉花 槐花 栀子 翘 胡 夏 附子
        乌 芎 芷 防风 芩 梗 根 萸 五味子 决明子 覆盆子 酸枣仁 砂仁 桃仁 陈皮 丹皮 橘红 佛手 罗汉果
        雪莲 黄莲 穿心莲 金线莲 楼 活 艽 胆 藿 蓉 阳 虫草 茸 阿胶 胶 薄荷 荷 苏 木香 藿香 绞股蓝 青蒿
        艾蒿 及 玉竹 冬 桑叶 荷叶 壳 实 孢子粉 葛 桂枝 佩兰 泽兰 乌头 香橼 蝎""",
    "prepared": """粉丝 粉条 粉 面 线 饼 糕 馍 馒头 包子 饺子 粽子 粽 汤圆 元宵 豆腐 豆干 香干 腐竹 豆皮
        千张 百叶 榨菜 泡菜 酸菜 咸菜 酱菜 腌菜 梅干菜 霉干菜 梅菜 冬菜 芽菜 干 罐头 蜜饯 果脯 脯 凉果
        酥 糍粑 粑 麻花 馓子 锅盔 馕 锅巴 汤 羹 凉皮 粉皮 面皮 米皮 豆花""",
    "not-food": """花炮 烟花 礼花 砚 绣 雕 瓷 瓷器 陶 陶器 紫砂 器 漆 宣纸 纸 景泰蓝 毯 薰衣草 牧草 席草
        龙须草 灯心草 蒲草 草坪 茧 蚕 丝 丝绸 绸 缎 锦 棉 棉花 苎麻 亚麻 黄麻 烟 烟叶 兰 兰花 荷花 牡丹
        丹 牡丹花 月季 水仙 杜鹃 梅花 樱花 茶花 盆景 花卉 苗木 苗 竹 木 楠 杉 石 玉 墨 笔 扇 伞 刀 剑 席
        布 毛 绒 珍珠 马 桐油 沉香 檀香 松香 壶 灯 画""",
}


def _table():
    table = {}
    for kind, text in ENDINGS.items():
        for ending in text.split():
            if ending in table and table[ending] != kind:
                raise ValueError("ending %s is listed under both %s and %s" % (ending, table[ending], kind))
            table[ending] = kind
    return table


TABLE = _table()
LONGEST = max(len(ending) for ending in TABLE)
OVERRIDES_PATH = os.path.join(DATA_DIR, "overrides", "product-kinds.json")


def by_rule(title):
    """The kind named by the longest listed ending of the title, or None."""
    for text in (re.sub(r"[（(].*?[）)]", "", title), "".join(re.findall(r"[（(](.*?)[）)]", title))):
        for length in range(min(LONGEST, len(text)), 0, -1):
            kind = TABLE.get(text[-length:])
            if kind:
                return kind
    return None


def load_overrides():
    return read_json(OVERRIDES_PATH).get("kinds", {}) if os.path.exists(OVERRIDES_PATH) else {}


def classify(title, overrides=None):
    """Kind of a product. Hand-made corrections win; names no rule fits are "other"."""
    overrides = load_overrides() if overrides is None else overrides
    return overrides.get(title) or by_rule(title) or "other"


if __name__ == "__main__":
    import collections
    import glob
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    fixes = load_overrides()
    titles = sorted({row["title"] for path in glob.glob(os.path.join(DATA_DIR, "products", "*.json")) for row in read_json(path)})
    groups = collections.defaultdict(list)
    for title in titles:
        groups[classify(title, fixes)].append(title)
    for kind in KINDS:
        print("%-10s %4d" % (kind, len(groups[kind])))
    unplaced = [title for title in titles if title not in fixes and by_rule(title) is None]
    print("no rule fits (%d): %s" % (len(unplaced), " ".join(unplaced)))
