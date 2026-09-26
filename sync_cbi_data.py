"""Discover, validate and atomically publish the CBI monthly bulletin.

No credentials required. Failures preserve the last valid cbi_latest.json.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from extract_cbi_data import DataValidationError, PARSER_VERSION, parse_workbook

SOURCE_PAGE = 'https://cbi.iq/page/122'
DATA_DIR = Path(__file__).resolve().parent / 'data'
MAX_DOWNLOAD = 15 * 1024 * 1024


def official_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname != 'cbi.iq' or parsed.port not in (None, 443) or parsed.username:
        raise DataValidationError('Source URL must be HTTPS on cbi.iq')
    return url


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        official_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url):
    official_url(url)
    for attempt in range(3):
        try:
            request = Request(url, headers={'User-Agent': 'IraqBudgetApp-CBI-Sync/1.0', 'Cache-Control': 'no-cache'})
            with build_opener(OfficialRedirect()).open(request, timeout=40) as response:
                official_url(response.geturl())
                content = response.read(MAX_DOWNLOAD + 1)
                if len(content) > MAX_DOWNLOAD:
                    raise DataValidationError('Source download exceeds 15 MB')
                return content
        except DataValidationError:
            raise
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


class ExcelLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            url = urljoin(SOURCE_PAGE, href)
            if urlsplit(url).path.lower().endswith('.xlsx'):
                self.links.add(official_url(url))


def discover_link(html):
    parser = ExcelLinks()
    parser.feed(html)
    if len(parser.links) != 1:
        raise DataValidationError('Expected one unambiguous Excel bulletin link on page 122')
    return parser.links.pop()


def read_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.cbi-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def validate_container(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if '[Content_Types].xml' not in archive.namelist():
            raise DataValidationError('Response is not an Excel workbook')
        if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
            raise DataValidationError('Expanded workbook exceeds 100 MB')


def sync(output=DATA_DIR, fetch=download, now=None):
    output = Path(output)
    now = now or datetime.now(timezone.utc)
    checked = now.isoformat(timespec='seconds')
    status_path = output / 'cbi_status.json'
    previous_status = read_json(status_path)
    try:
        previous = read_json(output / 'cbi_latest.json')
        url = discover_link(fetch(SOURCE_PAGE).decode('utf-8'))
        content = fetch(url)
        digest = hashlib.sha256(content).hexdigest()
        changed = (previous.get('source', {}).get('sha256') != digest
                   or previous.get('parser_version') != PARSER_VERSION)
        if changed:
            validate_container(content)
            dataset = parse_workbook(content, today=now.date())
            for key, latest in previous.get('periods', {}).items():
                if dataset['periods'][key] < latest:
                    raise DataValidationError(f'Latest {key} period would move backwards')
            dataset['source'] = {'page_url': SOURCE_PAGE, 'file_url': url, 'sha256': digest,
                                 'updated_at': checked}
            # One atomic file contains all tables; the app never sees a partial dataset.
            atomic_json(output / 'cbi_latest.json', dataset)
        else:
            dataset = previous
        status = {'last_checked_at': checked, 'last_success_at': checked,
                  'last_updated_at': dataset['source']['updated_at'],
                  'status': 'updated' if changed else 'unchanged',
                  'page_url': SOURCE_PAGE, 'file_url': url,
                  'periods': dataset['periods'], 'warnings': dataset['warnings']}
        atomic_json(status_path, status)
        return status
    except Exception as exc:
        status = {**previous_status, 'last_checked_at': checked, 'status': 'failed',
                  'error': f'{type(exc).__name__}: {exc}', 'page_url': SOURCE_PAGE}
        atomic_json(status_path, status)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DATA_DIR)
    args = parser.parse_args()
    result = sync(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
