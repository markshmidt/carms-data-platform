"""
Helper functions for parsing program records from scraped data.
"""
import re
import unicodedata

from .normalization import (
    DISCIPLINE_FR_TO_EN,
    KNOWN_DISCIPLINES,
    SCHOOL_FR_TO_EN,
    STREAM_FR_TO_EN,
)


def normalize_text(text: str) -> str:
    """Normalize unicode text (NFKC) and strip whitespace."""
    return unicodedata.normalize("NFKC", text).strip()


# ── Constants ──────────────────────────────────────────────────────
_YEAR_START_RE = re.compile(r"^\s*\d{4}\b")


# ── Metadata Detection ──────────────────────────────────────────────
def _is_metadata_line(s: str) -> bool:
    """Check if a line is a metadata line (year, match, iteration, stream info)."""
    t = s.strip().lower()
    return (
        t.startswith("# 202") or t.startswith("202")  # year line
        or "residency" in t
        or "match" in t
        or "iteration" in t
        or "premier tour" in t  # French: "first iteration"
        or "jumelage" in t  # French: "match"
        or t.startswith("cmg")
        or t.startswith("img")
        or t.startswith("ros")
    )


def _next_nonempty(lines: list[str], start: int) -> int | None:
    """Find the next non-empty line starting from the given index."""
    for j in range(start, len(lines)):
        if lines[j].strip():
            return j
    return None


def _take_until_metadata(parts: list[str]) -> list[str]:
    """
    Take parts until we hit metadata.
    Metadata can start:
      - inside a part: "Toronto # 2025 ..."
      - as a new part: "2025 ..."
    """
    out = []
    for p in parts:
        if not p:
            continue

        # if metadata is inline after '#'
        if "#" in p:
            left = p.split("#", 1)[0].strip()
            if left:
                out.append(left)
            break

        # if metadata starts as a new piece (often "2025 ...")
        if _YEAR_START_RE.match(p.strip()):
            break

        out.append(p.strip())

    return out


# ── Discipline and Site Parsing ──────────────────────────────────────
def split_discipline_and_site(parts: list[str]) -> tuple[str, str | None]:
    """
    Split discipline and site from parts using known disciplines list.

    Strategy:
    - Join all parts into a string
    - Find the longest matching discipline from KNOWN_DISCIPLINES
    - Everything after the matched discipline is the site

    Examples:
    - ["General Surgery", "Ottawa"]
      -> remainder="General Surgery - Ottawa"
      -> matches "General Surgery"
      -> returns ("General Surgery", "Ottawa")

    - ["Otolaryngology", "Head and Neck Surgery", "Toronto"]
      -> remainder="Otolaryngology - Head and Neck Surgery - Toronto"
      -> matches "Otolaryngology - Head and Neck Surgery"
      -> returns ("Otolaryngology - Head and Neck Surgery", "Toronto")

    - ["Hematological Pathology", "Toronto"]
      -> remainder="Hematological Pathology - Toronto"
      -> matches "Hematological Pathology"
      -> returns ("Hematological Pathology", "Toronto")
    """
    if not parts:
        return "", None

    remainder = " - ".join(parts)

    best_match = None
    for disc in KNOWN_DISCIPLINES:
        if remainder.startswith(disc): # if remainder starts with a known discipline, it is the discipline
            if best_match is None or len(disc) > len(best_match):
                best_match = disc

    if best_match: # if we found a best match, the site is the remainder minus the best match
        site = remainder[len(best_match) :].strip(" -")
        return best_match, site if site else None

    # If no match found, assume first part is discipline, rest is site
    if len(parts) == 1:
        return parts[0], None
    elif len(parts) == 2:
        return parts[0], parts[1]
    else:
        return " - ".join(parts[:-1]), parts[-1]


def _clean_discipline_name(discipline_name: str) -> str:
    """
    Clean up discipline names by removing city suffixes from "including Family Medicine" variants.
    
   This is a fallback for edge cases. The main parsing logic in split_discipline_and_site
    should handle most cases using KNOWN_DISCIPLINES.
    """
    # only process if it contains "including Family Medicine"
    if (
        "including" in discipline_name.lower()
        and "family" in discipline_name.lower()
        and "medicine" in discipline_name.lower()
    ):
        #  keep everything up to and including "including Family Medicine"
        # remove anything after that (likely city suffixes)
        pattern = r"(.+?including\s+[Ff]amily\s+[Mm]edicine).*"
        match = re.search(pattern, discipline_name, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return discipline_name


# ── Stream Extraction ────────────────────────────────────────────────
def _extract_stream(lines: list[str], header_index: int) -> str:
    """
    Extract stream from the line immediately after the metadata line.
    Metadata line pattern: "#  2025 R-1 Main Residency Match - first iteration"
    Also maps French stream names to English.
    """
    # look for the metadata line (year/iteration line)
    for i in range(header_index + 1, len(lines)):
        line = lines[i].strip()

        if not line:
            continue

        if line.startswith("#") and _is_metadata_line(line):
            # next non-header line is the stream
            for j in range(i + 1, len(lines)):
                next_line = lines[j].strip()

                if not next_line:
                    continue
                if next_line.startswith("#"):
                    break

                stream_norm = normalize_text(next_line.lower())

                if stream_norm in STREAM_FR_TO_EN:
                    return STREAM_FR_TO_EN[stream_norm]

                return next_line
    
    return "Unknown"