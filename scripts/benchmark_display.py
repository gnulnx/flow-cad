#!/usr/bin/env python3
"""Reproducible browser open/isolate/restore benchmark against a running workbench.

Requires Playwright Chromium. No CAD generation or production export writes.
Show fully assembled clears any current preview, just like the UI action.
"""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend', required=True)
    parser.add_argument('--api', required=True)
    parser.add_argument('--part', required=True, help='Part key to isolate between restores')
    parser.add_argument('--assembly-parts', required=True, type=int)
    parser.add_argument('--cycles', default=3, type=int)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = {'part': args.part, 'assembly_parts': args.assembly_parts, 'renderer': 'Chromium SwiftShader',
              'runs': [], 'model_requests': [], 'errors': []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=[
            '--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        page = browser.new_page(viewport={'width':1500,'height':950})
        page.on('pageerror', lambda error: result['errors'].append(str(error)))
        page.on('request', lambda request: result['model_requests'].append(request.url)
                if '/model' in request.url else None)
        page.add_init_script("window.__longTasks=[];new PerformanceObserver(list=>window.__longTasks.push(...list.getEntries().map(e=>e.duration))).observe({type:'longtask',buffered:true})")
        def ready(count):
            page.wait_for_function('(n)=>document.querySelector(".viewport-progress")?.innerText.includes(`${n} of ${n}`)',
                                   arg=count,timeout=120000)
        started=time.perf_counter()
        page.goto(args.frontend.rstrip('/')+'/?'+urlencode({'api':args.api}))
        ready(args.assembly_parts)
        result['initial_seconds']=time.perf_counter()-started
        for _ in range(args.cycles):
            page.get_by_role('searchbox').fill(args.part)
            page.locator('.inventory-list button[role=option]').first.click()
            ready(1)
            count=len(result['model_requests']); started=time.perf_counter()
            page.get_by_role('button',name='Show fully assembled',exact=True).click()
            ready(args.assembly_parts)
            result['runs'].append({'restore_seconds':time.perf_counter()-started,
                                   'model_requests':len(result['model_requests'])-count})
        result['long_tasks_ms']=page.evaluate('window.__longTasks')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(args.output.with_suffix('.png')))
        browser.close()
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key not in {'model_requests','long_tasks_ms'}}))
    if result['errors']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
