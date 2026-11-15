#!/usr/bin/env python3
"""Read-only literal-repeat candidates for the current draft, not a quality score."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from novel import Book, Problem, digest, han, require


def sentences(text, path, chapter):
    for line_no, line in enumerate(text.splitlines(), 1):
        for m in re.finditer(r'[^。！？!?]+(?:[。！？!?]+[”’"」』]*|$)', line):
            raw = m.group()
            value = ''.join(raw.split()).strip('\ufeff')
            if han(value) >= 18:
                yield value, {'chapter': chapter, 'path': path, 'line': line_no,
                              'column': m.start() + len(raw) - len(raw.lstrip()) + 1}


def inspect(root, limit=12):
    require(type(limit) is int and 1 <= limit <= 50, '输出上限应为1—50')
    book = Book(root)
    state, baseline = book.snapshot()
    book.verify(state)
    task = book.pending(state)
    require(task and task.get('base_state_sha256') == baseline, '请先begin并恢复当前匹配任务')
    path = book.work_path(task['number']) + '/draft.txt'
    body = book.read(path)
    text = body.decode('utf-8')
    require(text.replace('\ufeff', '').strip(), '当前草稿没有正文')
    current, prior = defaultdict(list), defaultdict(list)
    for value, location in sentences(text, path, task['number']):
        current[value].append(location)
    for c in state['chapters'].values():
        name = 'book/' + c['text_path']
        for value, location in sentences(book.read(name).decode('utf-8'), name, c['number']):
            if value in current:
                prior[value].append(location)
    values = [v for v in current if len(current[v]) > 1 or prior[v]]
    values.sort(key=lambda v: (-han(v), current[v][0]['line']))
    candidates = [{'excerpt': value[:160], 'han': han(value),
                   'draft_count': len(current[value]), 'prior_count': len(prior[value]),
                   'draft_locations': current[value][:4], 'prior_locations': prior[value][:4]}
                  for value in values[:limit]]
    return {'status': 'candidates_only', 'book_id': state['book_id'],
            'state_sha256': baseline, 'draft_sha256': digest(body), 'chapter': task['number'],
            'draft_han': han(text), 'history_chapters': state['revision'],
            'method': 'literal_sentence_min_18_han_whitespace_ignored',
            'candidate_count': len(values), 'omitted_candidates': max(0, len(values) - limit),
            'locations_per_side_limit': 4, 'candidates': candidates,
            'limits': '只找字面长句重复；不判断近似改写、情节雷同、AI率或文学质量。回读上下文判断必要回扣，不自动删除；无候选不表示无问题。'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='.')
    p.add_argument('--limit', type=int, default=12)
    a = p.parse_args()
    try:
        print(json.dumps(inspect(a.root, a.limit), ensure_ascii=False, indent=2))
    except (Problem, OSError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as e:
        p.exit(1, '未完成：' + str(e) + '\n')


if __name__ == '__main__':
    main()
