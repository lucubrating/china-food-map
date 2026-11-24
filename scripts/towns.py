"""Towns and subdistricts (乡镇街道), for finding the counties a text means when it names towns.

Source: research/downloads/modood-divisions/streets.json, the statistics bureau's 2023 list of
towns as copied by the modood/Administrative-divisions-of-China repository. It is read by
the importers only; nothing from it is published.

Only towns, townships, subdistricts and sumu count (names ending 镇, 乡, 街道, 苏木). Farms, ranches,
fisheries, development zones and similar units are left out, since their names are often generic
("水产养殖场") and turn up inside longer names in the texts.
"""
import collections
import json
import os
import re

from common import DOWNLOADS_DIR

STREETS = os.path.join(DOWNLOADS_DIR, "modood-divisions", "streets.json")
KIND = re.compile(r"(民族乡|镇|乡|街道|苏木)$")


class Towns:
    """Town names by province, with the counties of the divisions table that hold them."""

    def __init__(self, divisions):
        self.available = os.path.exists(STREETS)
        self.full = collections.defaultdict(lambda: collections.defaultdict(set))   # province -> name -> counties
        self.stems = collections.defaultdict(set)                                   # county -> town stems
        self.nationwide = collections.Counter()                                     # name -> counties holding it
        if not self.available:
            return
        for town in json.load(open(STREETS, encoding="utf-8")):
            county = "cn:" + town["areaCode"]
            name = town["name"]
            if not divisions.get(county) or not KIND.search(name):
                continue
            province = "cn:" + town["provinceCode"] + "0000"
            self.full[province][name].add(county)
            self.nationwide[name] += 1
            stem = KIND.sub("", name)
            if len(stem) >= 2:
                self.stems[county].add(stem)

    def counties_in(self, text, province, within=None):
        """Counties whose towns `text` names in full (港沟街道, 金塘镇), inside `within` (a set of
        units whose counties count) or the province: {county: [towns named, weight]}, where a town
        no other county on the town list has weighs 1 and a common name (和平镇) a third.
        A town counts only where one county in that scope has it, and not where a longer town name
        of the province covers the same words."""
        text = re.sub(r"街办|街道办事处|办事处", "街道", text)
        names = self.full.get(province, {})
        spans = []
        for name in names:
            if len(name) >= 3:
                for match in re.finditer(re.escape(name), text):
                    spans.append((match.start(), match.end(), name))
        found = {}   # county -> [towns, weight], a town weighing 1 if no other county has its name, else 1/3
        seen = set()
        for start, end, name in spans:
            if any(s <= start and end <= e and (e - s) > (end - start) for s, e, _ in spans):
                continue  # part of a longer town's name
            scope = {c for c in names[name] if within is None or c in within}
            if len(scope) == 1 and name not in seen:
                seen.add(name)
                entry = found.setdefault(next(iter(scope)), [0, 0.0])
                entry[0] += 1
                entry[1] += 1 if self.nationwide[name] == 1 else 1 / 3
        return found

    @staticmethod
    def listed(text):
        """The towns a text lists by full name, whether or not they are on the list: 港沟街道, 大有乡."""
        text = re.sub(r"街办|街道办事处|办事处", "街道", text)
        found = re.findall(r"([\u4e00-\u9fff]{2,8}?(?:镇|乡|街道|苏木))(?=[、，,。；;和及与等（(\d]|$)", text)
        return {t for t in found if not re.search(r"个|共|乡镇|各|全", t)}

    def is_town_stem(self, word, counties):
        """True if `word` is the stem of a town of one of `counties` (东海 of 启东市's 东海镇)."""
        return any(word in self.stems.get(c, ()) for c in counties)
