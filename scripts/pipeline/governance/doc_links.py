"""Extract Markdown link targets from a document's prose.

Used to validate that local links in current-state documentation resolve to
real files. Examples inside fenced and inline code are not documentation
links, so they are stripped before extraction.
"""
import re

LINK = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]*)\)")


def link_targets(document):
    prose = re.sub(r"(?ms)^\x60\x60\x60[^\n]*\n.*?^\x60\x60\x60[^\n]*$", "", document)
    prose = re.sub(r"\x60[^\x60\n]+\x60", "", prose)
    return LINK.findall(prose)
