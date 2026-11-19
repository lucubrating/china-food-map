"""Look up administrative units in data/divisions.json. Standard library only.

The table has one row per unit at the three levels the map shows. A unit's level is its `depth`
in the tree (1, 2 or 3), never the shape of its code: a Beijing district has a six-digit county
code but sits at depth 2, directly under the municipality.

Used by the import scripts to place records and by the build script to check them.
"""
import os
import re

from common import DATA_DIR, read_json

TABLE_PATH = os.path.join(DATA_DIR, "divisions.json")

# Ethnic designations that appear inside the names of autonomous units, longest first.
# A few units write them without the final 族 (伊犁哈萨克自治州), so both forms are listed.
ETHNIC = sorted([
    "蒙古族", "回族", "藏族", "维吾尔族", "苗族", "彝族", "壮族", "布依族", "朝鲜族", "满族", "侗族", "瑶族",
    "白族", "土家族", "哈尼族", "哈萨克族", "傣族", "黎族", "傈僳族", "佤族", "畲族", "高山族", "拉祜族",
    "水族", "东乡族", "纳西族", "景颇族", "柯尔克孜族", "土族", "达斡尔族", "仫佬族", "羌族", "布朗族",
    "撒拉族", "毛南族", "仡佬族", "锡伯族", "阿昌族", "普米族", "塔吉克族", "怒族", "乌孜别克族",
    "俄罗斯族", "鄂温克族", "德昂族", "保安族", "裕固族", "京族", "塔塔尔族", "独龙族", "鄂伦春族",
    "赫哲族", "门巴族", "珞巴族", "基诺族", "各族",
    "蒙古", "哈萨克", "柯尔克孜", "塔吉克", "锡伯", "鄂伦春",
], key=len, reverse=True)

# Endings removed to make a short name, tried in this order.
PLAIN_ENDINGS = ("特别行政区", "行政委员会", "自治区", "地区", "特区", "新区", "盟", "省", "市", "县", "区")
# The one real forestry district. Other names ending in 林区 are ordinary districts (碑林区).
FORESTRY_DISTRICTS = {"神农架林区"}
# What is left after removing an ending must not be one of these: "市中区" stays "市中区".
TOO_GENERIC = {"市中", "城关", "新城", "城中", "城北", "城西", "城东", "城南", "新市", "高新"}
# Names that are ordinary words. In running text they count only right after their parent's name.
ORDINARY_WORDS = {"城区", "郊区", "矿区", "东区", "西区", "南区", "北区", "新区", "市中区", "城关区", "新城区",
                  "城中区", "城北区", "城西区", "城东区", "和县", "新市区", "高新区", "开发区"}


def _without_ethnic(stem):
    """Drop ethnic designations from the end of a name, as long as two characters remain."""
    changed = True
    while changed:
        changed = False
        for token in ETHNIC:
            if stem.endswith(token) and len(stem) - len(token) >= 2:
                stem = stem[:-len(token)]
                changed = True
                break
    return stem


def short_name(name, unit_id=""):
    """The everyday short form of a unit's name: 成都市 gives 成都, 北川羌族自治县 gives 北川."""
    if unit_id.startswith("mo:") or name.endswith("矿区") or name.endswith("旗") and "自治" not in name:
        return name
    if name in FORESTRY_DISTRICTS:
        return name[:-2]
    match = re.match(r"^(.+?)自治(?:州|县|旗)$", name)
    if match:
        stem = _without_ethnic(match.group(1))
        if stem in ETHNIC and stem.endswith("族"):
            stem = stem[:-1]
        return stem
    for ending in PLAIN_ENDINGS:
        if name.endswith(ending):
            stem = _without_ethnic(name[:-len(ending)])  # 管城回族区 gives 管城
            if len(stem) >= 2 and stem not in TOO_GENERIC:
                return stem
    return name


def kind_of(name, depth, code=""):
    """A plain label for the type of unit, worked out from its name."""
    if depth == 1:
        if name.endswith("特别行政区"):
            return "special-administrative-region"
        if name.endswith("自治区"):
            return "autonomous-region"
        return "municipality" if name.endswith("市") else "province"
    if name in FORESTRY_DISTRICTS:
        return "forestry-district"
    endings = (
        ("自治州", "autonomous-prefecture"), ("自治县", "autonomous-county"), ("自治旗", "autonomous-banner"),
        ("地区", "prefecture"), ("盟", "league"), ("特区", "special-district"),
        ("行政委员会", "administrative-committee"), ("填海区", "reclaimed-area"), ("堂区", "parish"),
        ("旗", "banner"), ("县", "county"), ("区", "district"),
    )
    for ending, kind in endings:
        if name.endswith(ending):
            return kind
    if name.endswith("市"):
        return "prefecture-level-city" if code.endswith("00") else "county-level-city"
    return "other"


class Divisions:
    """The table, indexed for lookups."""

    def __init__(self, path=TABLE_PATH):
        table = read_json(path)
        self.editions = table.get("editions", {})
        self.units = table["units"]
        self.by_id = {unit["id"]: unit for unit in self.units}
        self.children = {}
        for unit in self.units:
            self.children.setdefault(unit["parent"], []).append(unit["id"])
        self._names = {}

    def get(self, unit_id):
        return self.by_id.get(unit_id)

    def ancestors(self, unit_id):
        """Ids from the province-level unit down to the unit itself."""
        chain = []
        while unit_id:
            chain.append(unit_id)
            unit_id = self.by_id[unit_id]["parent"]
        return chain[::-1]

    def province(self, unit_id):
        return self.ancestors(unit_id)[0]

    def inside(self, unit_id, ancestor_id):
        """True if the unit is the ancestor itself or lies within it."""
        return ancestor_id in self.ancestors(unit_id)

    def descendants(self, unit_id):
        found = []
        for child in self.children.get(unit_id, []):
            found.append(child)
            found.extend(self.descendants(child))
        return found

    def label(self, unit_id):
        """Full path in Chinese, such as 四川省成都市蒲江县."""
        return "".join(self.by_id[i]["name"] for i in self.ancestors(unit_id))

    def _informal(self, unit):
        """Other ways running text writes a unit's name.

        An autonomous unit is often written without its ethnic designation (保亭县, 凉山州). A county,
        county-level city or district is often written with the ending it had before a change of
        status (无为县 for 无为市, 蓬莱市 for 蓬莱区).
        """
        name = unit["name"]
        if "自治" in name:
            ending = {"自治县": "县", "自治旗": "旗", "自治州": "州"}.get(name[-3:])
            stem = short_name(name, unit["id"])
            return {stem + ending} if ending and len(stem) >= 2 else set()
        lower = unit["depth"] == 3 or unit["kind"] in ("district", "county", "county-level-city")
        if lower and name[-1] in "区市县" and not name.endswith(("矿区", "新区", "林区", "特区")) and len(name) >= 3:
            return {name[:-1] + ending for ending in "区市县"} - {name}
        return set()

    def _names_in(self, province_id):
        """Every name a unit of this province may go by: (name, unit id, is a full name)."""
        if province_id not in self._names:
            names = []
            units = [self.by_id[unit_id] for unit_id in self.descendants(province_id)]
            real = {name for unit in units for name in [unit["name"]] + unit.get("was", [])}
            for unit in units:
                unit_id = unit["id"]
                for name in [unit["name"]] + unit.get("was", []):
                    names.append((name, unit_id, True))
                for name in sorted(self._informal(unit) - real):
                    names.append((name, unit_id, True))
                if unit["short"] != unit["name"]:
                    names.append((unit["short"], unit_id, False))
            names.sort(key=lambda item: (-len(item[0]), not item[2], item[1]))
            self._names[province_id] = names
        return self._names[province_id]

    def locate(self, text, province_id):
        """Units of one province named in `text`, as specific as the text allows.

        Full names are matched first, longest first, and each matched stretch of text is used only
        once, so 长沙县 is the county and never also the city 长沙. A name shared by several units of
        the province, or one that is an ordinary word, counts only directly after the name of its
        parent or in a list of its siblings. Short names (成都 for 成都市) are tried only for
        second-level units.
        A second-level unit is dropped when one of its own third-level units is also named.
        """
        text = re.sub(r"\s+", "", text or "")
        if not text or province_id not in self.by_id:
            return []
        names = self._names_in(province_id)
        counts = {}
        for name, _unit_id, full in names:
            if full:
                counts[name] = counts.get(name, 0) + 1

        taken = [False] * len(text)
        found = {}   # unit id -> position of its first mention
        spans = []   # (start, end, unit id)

        def free(start, end):
            return not any(taken[start:end])

        def mark(start, end, unit_id):
            for index in range(start, end):
                taken[index] = True
            spans.append((start, end, unit_id))
            found.setdefault(unit_id, start)

        def follows_family(start, unit_id):
            """True if the name comes straight after its parent, or continues a list of its siblings."""
            parent = self.by_id[unit_id]["parent"]
            for _s, end, owner in spans:
                if end <= start and (owner == parent or self.by_id[owner]["parent"] == parent):
                    if re.fullmatch(r"[、，,；;和及与]*", text[end:start]):
                        return True
            return False

        # Pass 1: full names that are safe on their own.
        for name, unit_id, full in names:
            if not full or counts[name] > 1 or name in ORDINARY_WORDS:
                continue
            for match in re.finditer(re.escape(name), text):
                if free(match.start(), match.end()):
                    mark(match.start(), match.end(), unit_id)
        # Pass 2: short names of second-level units, where no full name claimed the text. A short
        # name counts only at the end of a phrase or straight before one of its own units, so
        # 徐州鼓楼区 names 徐州市 but a township called 大同镇 does not name the city 大同.
        def ends_phrase(end, unit_id):
            if end == len(text) or text[end] in "、，,。；;（()）":
                return True
            rest = text[end:]
            return any(rest.startswith(name) for child in self.children.get(unit_id, [])
                       for name in [self.by_id[child]["name"]] + self.by_id[child].get("was", []))

        for name, unit_id, full in names:
            if full or self.by_id[unit_id]["depth"] != 2 or len(name) < 2:
                continue
            for match in re.finditer(re.escape(name), text):
                if free(match.start(), match.end()) and ends_phrase(match.end(), unit_id):
                    mark(match.start(), match.end(), unit_id)
        # Pass 3: shared or ordinary names, accepted only straight after their parent or in a list
        # of its siblings (阳泉市城区、矿区、郊区). Repeated until nothing more is found.
        again = True
        while again:
            again = False
            for name, unit_id, full in names:
                if not full or not (counts[name] > 1 or name in ORDINARY_WORDS):
                    continue
                for match in re.finditer(re.escape(name), text):
                    if free(match.start(), match.end()) and follows_family(match.start(), unit_id):
                        mark(match.start(), match.end(), unit_id)
                        again = True

        parents_with_child = {self.by_id[unit_id]["parent"] for unit_id in found}
        kept = [unit_id for unit_id in found if unit_id not in parents_with_child]
        return sorted(kept, key=lambda unit_id: found[unit_id])

    def leading_unit(self, text, province_id):
        """The unit of one province whose name `text` starts with, or None.

        For names that open with a bare place name, such as 青田稻鱼共生系统 (青田县). Short names
        count here, and a banner may drop its 旗. The longest name wins; between a unit and its
        parent with the same short name, the lower unit wins.
        """
        text = re.sub(r"\s+", "", text or "")
        best = None
        for unit_id in self.descendants(province_id) if province_id in self.by_id else []:
            unit = self.by_id[unit_id]
            names = {unit["name"], unit["short"]} | set(unit.get("was", []))
            if unit["name"].endswith("旗") and "自治" not in unit["name"] and len(unit["name"]) > 3:
                names.add(unit["name"][:-1])
            for name in names:
                if len(name) >= 2 and text.startswith(name):
                    rank = (len(name), unit["depth"])
                    if best is None or rank > best[0]:
                        best = (rank, unit_id)
        return best[1] if best else None

    def centre_of(self, unit_ids):
        """A point for a record placed in these units: the centre of one, or the mean of several."""
        points = [self.by_id[i]["centre"] for i in unit_ids if self.by_id[i].get("centre")]
        if not points:
            return None
        return [round(sum(p[0] for p in points) / len(points), 3), round(sum(p[1] for p in points) / len(points), 3)]
