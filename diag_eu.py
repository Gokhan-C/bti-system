#!/usr/bin/env python3
"""EBTI tanılama: connector'ın 19 Haziran için kullandığı arama URL'sini
gerçek tarayıcıda açar, sonuç sayısını ve ilk referansları yazar."""
import sys, asyncio
from datetime import datetime
from urllib.parse import quote
sys.path.insert(0, "/Users/gokhancankaya/bti_system")
from connectors.eu_ebti import _build_search_url

async def main():
    d = datetime(2026, 6, 19)
    date_hyphen = d.strftime("%d-%m-%Y")
    date_slash_encoded = quote(d.strftime("%d/%m/%Y"), safe="")
    url = _build_search_url(date_hyphen, date_slash_encoded)
    print("SEARCH URL:\n", url, "\n")

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        pg = await (await b.new_context()).new_page()
        await pg.goto(url, wait_until="load", timeout=120000)
        try:
            await pg.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        body = await pg.inner_text("body")
        # sonuç sayısı ipuçları
        import re
        for pat in ["results match your search", "result match", "results match",
                    "results found", "No results", "0 results"]:
            for m in re.finditer(r".{0,40}" + re.escape(pat) + r".{0,10}", body):
                print("MATCH:", repr(m.group(0).strip()))
        rows = await pg.query_selector_all("table.table-result tbody tr")
        print("\ntable.table-result row count:", len(rows))
        # ilk referanslar
        refs = []
        for r in rows[:8]:
            cells = await r.query_selector_all("td")
            if cells:
                refs.append((await cells[0].inner_text()).strip())
        print("first refs:", refs)
        # connector'ın bail koşulu
        bail = ("0 results match" in body) or ("results match your search" not in body)
        print("\nCONNECTOR BAIL (sonuç yok sayar mı)?:", bail)
        print("\n--- body ilk 600 char ---\n", body[:600])
        await b.close()

asyncio.run(main())
