"""Local lexical RAG over explicitly approved puzzles; no model or SQL dependency."""
import math
import re
from collections import Counter


def terms(text):
    text = str(text).lower()
    latin = re.findall(r"[a-z0-9]+", text)
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    return Counter(latin + [char for part in chinese for char in part]
                   + [part[i:i+2] for part in chinese for i in range(len(part)-1)])


class ApprovedPuzzleRetriever:
    def __init__(self, source=lambda: (), limit=3):
        self.source = source
        self.limit = limit

    def search(self, theme):
        query = terms(theme)
        ranked = []
        # Source is refreshed on each generation, so committed puzzles are immediately visible.
        for item in self.source():
            generation = item.get("generation", {})
            if generation.get("approved") is not True:
                continue
            reference = {key: item.get(key) for key in ("id", "title", "surface", "bottom", "key_points")}
            reference["tags"] = generation.get("tags", [])
            # Bound reference context; never include traces, model instructions or entire history.
            text = " ".join(str(reference[k]) for k in ("title", "surface", "bottom", "key_points", "tags"))
            vector = terms(text)
            overlap = sum(value * vector.get(term, 0) for term, value in query.items())
            score = overlap / (math.sqrt(sum(v*v for v in vector.values())) or 1)
            if score > 0:
                ranked.append((score, str(item["id"]), reference))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        return [row[2] for row in ranked[:self.limit]]
