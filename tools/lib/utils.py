import shutil

from .genidx import generate

from lxml import etree
from pathlib import Path
from collections import deque
from typing import List, Callable
from concurrent.futures import ProcessPoolExecutor


class Event:
    def __init__(self, num: int, msg: str, file: str, line: int):
        self.num = num
        self.msg = msg
        self.file = file
        self.line = line


class Meta:
    def __init__(self):
        self.desc = ''
        self.type = ''
        self.category = ''
        self.file = ''
        self.function = ''


class Report:
    def __init__(self, file: Path, meta: Meta, events: List[Event]):
        self.file = file
        self.meta = meta
        self.events = events


def _parse_event(file: str, line: int, div: etree._Element) -> Event:
    num = None
    for td in div.iter('td'):
        children = td.getchildren()
        if not children:
            assert num
            return Event(num, td.text, file, line)
        elif 'PathIndex' in children[0].get('class'):
            num = int(children[0].text)
    assert not num
    return Event(0, div.text, file, line)


def _parse_code(file: str, table: etree._Element) -> List[Event]:
    events = []
    line = 0
    for tr in table.getchildren():
        if tr.get('class') == 'codeline':
            line += 1
            continue
        if tr.get('class') == 'variable_popup':
            continue
        div = tr.xpath('td/div[contains(class, msg)]')
        assert div and len(div) == 1
        events.append(_parse_event(file, line, div[0]))
    return events


def _parse_comment(comment: str, meta: Meta):
    if comment.startswith('BUGDESC '):
        meta.desc = comment[len('BUGDESC '):]
    elif comment.startswith('BUGTYPE '):
        meta.type = comment[len('BUGTYPE '):]
    elif comment.startswith('BUGCATEGORY '):
        meta.category = comment[len('BUGCATEGORY '):]
    elif comment.startswith('BUGFILE '):
        meta.file = comment[len('BUGFILE '):]
    elif comment.startswith('FUNCTIONNAME '):
        meta.function = comment[len('FUNCTIONNAME '):]

###############################################################################
# Parse an html report to a Report object.
###############################################################################


def parse_report(report: Path) -> Report:
    events = []
    meta = Meta()
    current_file = None
    tree = etree.parse(report.as_posix(), etree.HTMLParser())
    for element in tree.iter('h4', 'table', etree.Comment):
        if element.tag == etree.Comment:
            _parse_comment(element.text.strip(), meta)
        elif element.get('class') == 'FileName':
            current_file = element.text
        elif element.get('class') == 'code':
            current_file = current_file or meta.file
            events.extend(_parse_code(current_file, element))
    events.sort(key=lambda e: e.num)
    return Report(report, meta, events)

###############################################################################
# Parse reports in a report directory to a list of Report objects.
###############################################################################


def parse_reports(dir: Path, jobs: int = 1) -> List[Report]:
    reports = find_reports(dir)
    with ProcessPoolExecutor(jobs) as e:
        return [report for report in e.map(parse_report, reports)]


class Policy:
    def _handle_memory_leak(report: Report):
        # treat alloc & exception events as important events
        important_events = []
        for event in report.events:
            if ' exception' in event.msg or 'Memory is allocated' in event.msg:
                important_events.append(event)
        return important_events

    def aggressive(report: Report) -> List[Event]:
        # specially handle memory leak report
        if report.meta.type == 'Memory leak':
            return Policy._handle_memory_leak(report)
        # only events in the last file are treated as important events
        important_events = []
        important_file = report.events[-1].file
        for event in report.events:
            if (event.file != important_file
                    or event.msg.startswith('Assuming')
                    or event.msg.startswith('Taking')):
                continue
            important_events.append(event)
        return important_events

    def conservative(report: Report) -> List[Event]:
        # every event is treated as an important event
        return report.events


class _Edge:
    def __init__(self, event: Event):
        self.impl = event.msg, event.file, event.line

    def __hash__(self) -> int:
        return hash(self.impl)

    def __eq__(self, o: object) -> bool:
        return isinstance(o, _Edge) and self.impl == o.impl


class _Node(dict):
    def __init__(self):
        self.report = None

    def _make_leaf(self, report: Report):
        self.report = report
        self.clear()

    def _is_leaf(self) -> bool:
        return self.report and not self


class _Tree:
    def __init__(self, policy):
        self.root = _Node()
        self.policy = policy

    def _insert_report(self, report: Report):
        node = self.root
        for event in reversed(self.policy(report)):
            if (node._is_leaf()):
                # discard this longer report
                return
            edge = _Edge(event)
            if edge not in node:
                node[edge] = _Node()
            node = node[edge]
        # discard previous longer reports
        node._make_leaf(report)

    def _unique_reports(self) -> List[Report]:
        reports = []
        queue = deque()
        queue.append(self.root)
        while len(queue):
            node = queue.popleft()
            if node._is_leaf():
                reports.append(node.report)
            else:
                queue.extend(node.values())
        return reports

###############################################################################
# Remove duplicate reports from a Report list.
#
# Two reports are duplicate if IES (important event sequence) of one report
# is a suffix of IES of another report. Report with longer IES is removed.
# 
# If two reports have the same IESs, which one to remove is not guaranteed.
#
# Two preset policies (Policy.aggressive & Policy.conservative) to determine
# the important event sequence.
###############################################################################


def unique_reports(reports: List[Report], policy: Callable[[Report], List[Event]]) -> List[Report]:
    tree = _Tree(policy)
    for report in reports:
        tree._insert_report(report)
    return tree._unique_reports()

###############################################################################
# Find report paths in a report directory.
###############################################################################


def find_reports(dir: Path) -> List[Path]:
    reports = []
    if not dir.exists():
        return reports
    for file in dir.glob('*.html'):
        if file.name != 'index.html':
            reports.append(file)
    return reports

###############################################################################
# Copy reports to directory.
###############################################################################


def copy_reports(reports: List[Report], dir: Path, index: bool = True):
    dir.mkdir(exist_ok=True, parents=True)
    for report in reports:
        shutil.copy(report.file, dir)
    if index:
        generate_index(dir)

###############################################################################
# Generate index.html in a report directory.
###############################################################################


def generate_index(dir: Path):
    if any(dir.iterdir()):
        generate(dir.as_posix())
