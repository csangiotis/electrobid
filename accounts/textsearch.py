"""Αναζήτηση που αγνοεί κεφαλαία και τόνους (π.χ. «φωτοβολταικο» βρίσκει «Φωτοβολταϊκό»)."""
import unicodedata


def fold(text):
    text = unicodedata.normalize("NFD", str(text or "")).casefold()
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").replace("ς", "σ")


def matches(query, *fields):
    terms = fold(query).split()
    haystack = " ".join(fold(f) for f in fields)
    return all(t in haystack for t in terms)
