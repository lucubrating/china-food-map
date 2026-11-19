#!/usr/bin/env python3
"""Convert Simplified Chinese to Traditional Chinese. Standard library only.

Most Simplified characters have one Traditional form. A few hundred have more than one, and
which is right depends on the word: 干 is 乾 in 豆腐乾 (dried), 幹 in 樹幹 (trunk) and stays 干
in 干擾. So a text is converted in this order:

  1. A whole text listed under "texts" in data/overrides/hant.json is taken from there as it is.
  2. Otherwise the text is read from left to right. At each point the longest phrase that
     starts there is converted as a whole: first the phrases under "phrases" in the overrides
     file, then the phrases of the OpenCC tables.
  3. A character that no phrase covers takes its usual Traditional form: the one under "chars"
     in the overrides file if it is there, and the tables' first form otherwise.
  4. What the tables produced is then put into the character forms of one place, Taiwan ("tw")
     or Hong Kong ("hk"). What the overrides file produced is left exactly as written there.

The tables are in data/hant.json, made by scripts/import_hant.py.

Usage as a command, to see how something converts and why:
  python3 scripts/hant.py 豆腐干 余干县
  python3 scripts/hant.py --forms hk 里脊
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA_DIR, read_json  # noqa: E402

TABLES_PATH = os.path.join(DATA_DIR, "hant.json")
OVERRIDES_PATH = os.path.join(DATA_DIR, "overrides", "hant.json")


def by_first(table):
    """{first character: lengths of the keys that start with it, longest first}."""
    lengths = {}
    for key in table:
        lengths.setdefault(key[0], set()).add(len(key))
    return {first: sorted(found, reverse=True) for first, found in lengths.items()}


def longest(text, at, table, lengths):
    """The longest key of `table` that `text` has at position `at`, or None."""
    for n in lengths.get(text[at], ()):
        if text[at:at + n] in table:
            return text[at:at + n]
    return None


class Converter:
    def __init__(self, forms="tw"):
        tables = read_json(TABLES_PATH)
        overrides = read_json(OVERRIDES_PATH) if os.path.exists(OVERRIDES_PATH) else {}
        if forms and forms not in tables["forms"]:
            raise ValueError("no character forms called %r: use one of %s" % (forms, ", ".join(tables["forms"])))
        self.forms = forms
        self.chars = tables["chars"]
        self.phrases = tables["phrases"]
        self.ours = dict(overrides.get("phrases", {}))
        self.our_chars = dict(overrides.get("chars", {}))
        self.texts = dict(overrides.get("texts", {}))
        local = tables["forms"][forms] if forms else {"chars": {}, "phrases": {}}
        self.local_chars = local["chars"]
        self.local_phrases = local["phrases"]
        self.alike = tables["alike"]
        self._phrase_lengths = by_first(self.phrases)
        self._our_lengths = by_first(self.ours)
        self._local_lengths = by_first(self.local_phrases)

    def several(self, char):
        """True for a character with more than one Traditional form."""
        return len(self.chars.get(char, "")) > 1

    def localise(self, text):
        """Put standard Traditional forms into the forms of one place."""
        out, at = [], 0
        while at < len(text):
            phrase = longest(text, at, self.local_phrases, self._local_lengths)
            if phrase:
                out.append(self.local_phrases[phrase])
                at += len(phrase)
            else:
                out.append(self.local_chars.get(text[at], text[at]))
                at += 1
        return "".join(out)

    def pieces(self, text):
        """The text cut into pieces, each (source, result, how).

        `how` says what decided the piece: "text" (the whole text is in the overrides file),
        "ours" (a phrase in the overrides file), "phrase" (a phrase in the tables), "our usual"
        (a character taking the form the overrides file gives it), "usual" (a character taking
        the tables' usual form) or "same" (a character with no other form).
        """
        if text in self.texts:
            return [(text, self.texts[text], "text")]
        found, at = [], 0
        while at < len(text):
            phrase = longest(text, at, self.ours, self._our_lengths)
            if phrase:
                found.append((phrase, self.ours[phrase], "ours"))
                at += len(phrase)
                continue
            phrase = longest(text, at, self.phrases, self._phrase_lengths)
            if phrase:
                found.append((phrase, self.phrases[phrase], "phrase"))
                at += len(phrase)
                continue
            char = text[at]
            if char in self.our_chars:
                found.append((char, self.our_chars[char], "our usual"))
            elif char in self.chars:
                found.append((char, self.chars[char][0], "usual"))
            else:
                found.append((char, char, "same"))
            at += 1
        # Local forms are applied across neighbouring pieces together, because a local phrase
        # can span two of them. A phrase keeps its length when converted, so the result can be
        # cut up again at the same places.
        out, run = [], []

        def close():
            if not run:
                return
            joined = self.localise("".join(piece[1] for piece in run))
            at = 0
            for source, result, how in run:
                out.append((source, joined[at:at + len(result)], how))
                at += len(result)
            del run[:]

        for piece in found:
            if piece[2] in ("ours", "our usual"):
                close()
                out.append(piece)
            else:
                run.append(piece)
        close()
        return out

    def convert(self, text):
        return "".join(piece[1] for piece in self.pieces(text))

    def doubts(self, text):
        """The characters of `text` whose form depended on the word: [(character, form, how, piece)].

        `form` is None where the piece changed length, so the character has no one counterpart.
        """
        found = []
        for source, result, how in self.pieces(text):
            for index, char in enumerate(source):
                if self.several(char):
                    form = result[index] if len(result) == len(source) else None
                    found.append((char, form, how, source))
        return found


def main():
    args = sys.argv[1:]
    forms = "tw"
    if args[:1] == ["--forms"]:
        forms, args = (args[1] if len(args) > 1 else ""), args[2:]
    if not args:
        sys.exit(__doc__.strip())
    converter = Converter(None if forms in ("", "none") else forms)
    for text in args:
        print("%s -> %s" % (text, converter.convert(text)))
        for source, result, how in converter.pieces(text):
            if how != "same" and (how != "usual" or converter.several(source)):
                note = "  (one of %s)" % " ".join(converter.chars[source]) if how.endswith("usual") else ""
                print("    %s -> %s  %s%s" % (source, result, how, note))


if __name__ == "__main__":
    main()
