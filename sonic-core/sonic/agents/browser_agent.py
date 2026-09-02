"""
SONIC-REDA — Browser Vision Agent (Playwright + Screenshot Proofs)
====================================================================
Autonomous browser interaction agent using Playwright for:
    - Rendering SPAs (React, Vue, Angular) and extracting dynamic DOM
    - Capturing screenshot proof for XSS, UI bugs, and visual vulnerabilities
    - Clicking, typing, navigating, and waiting for dynamic content
    - Extracting hidden API routes from JavaScript bundles
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sonic.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PageSnapshot:
    """Captured state of a web page."""
    url: str
    title: str
    status_code: int
    html_content: str
    screenshot_b64: str  # Base64 PNG
    cookies: list[dict[str, Any]] = field(default_factory=list)
    console_logs: list[str] = field(default_factory=list)
    network_requests: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class DOMElement:
    """An interactive element found in the DOM."""
    tag: str
    text: str
    selector: str
    attributes: dict[str, str] = field(default_factory=dict)
    is_visible: bool = True


class BrowserAgent:
    """
    Autonomous browser controller for visual testing and proof capture.
    Uses Playwright when available, falls back to httpx for basic HTTP.
    """

    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        self._using_playwright = False

    async def launch(self) -> bool:
        """Launch browser instance."""
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self.headless)
            self._context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (SONIC-REDA Browser Agent) Chrome/120",
                ignore_https_errors=True,
                accept_downloads=True,
            )
            self._page = await self._context.new_page()
            self._using_playwright = True
            logger.info("browser_agent_launched", engine="playwright")
            return True
        except ImportError:
            logger.warning("playwright_not_installed", fallback="httpx")
            self._using_playwright = False
            return True  # Fall back to httpx mode
        except Exception as e:
            logger.error("browser_launch_failed", error=str(e))
            return False

    async def navigate(self, url: str) -> PageSnapshot:
        """Navigate to URL and capture full page state."""
        if self._using_playwright and self._page:
            return await self._playwright_navigate(url)
        return await self._httpx_navigate(url)

    async def _playwright_navigate(self, url: str) -> PageSnapshot:
        """Full browser navigation with Playwright."""
        console_logs: list[str] = []
        network_reqs: list[dict[str, Any]] = []

        self._page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        self._page.on("request", lambda req: network_reqs.append({
            "url": req.url, "method": req.method, "resource_type": req.resource_type,
        }))

        response = await self._page.goto(url, timeout=self.timeout, wait_until="networkidle")
        status = response.status if response else 0

        # Wait for dynamic content
        await self._page.wait_for_timeout(1000)

        title = await self._page.title()
        html = await self._page.content()
        screenshot = await self._page.screenshot(full_page=True, type="png")
        screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")

        cookies = await self._context.cookies()

        return PageSnapshot(
            url=url,
            title=title,
            status_code=status,
            html_content=html[:50000],
            screenshot_b64=screenshot_b64,
            cookies=[{"name": c["name"], "value": c["value"], "domain": c["domain"]} for c in cookies],
            console_logs=console_logs[:50],
            network_requests=network_reqs[:100],
        )

    async def _httpx_navigate(self, url: str) -> PageSnapshot:
        """Fallback HTTP-only navigation without browser rendering."""
        import httpx
        async with httpx.AsyncClient(verify=False, timeout=15, follow_redirects=True) as client:
            response = await client.get(url)
            return PageSnapshot(
                url=str(response.url),
                title="",
                status_code=response.status_code,
                html_content=response.text[:50000],
                screenshot_b64="",
                cookies=[],
                console_logs=[],
                network_requests=[],
            )

    async def click(self, selector: str) -> bool:
        """Click an element by CSS selector."""
        if not self._using_playwright or not self._page:
            return False
        try:
            await self._page.click(selector, timeout=5000)
            return True
        except Exception as e:
            logger.debug("click_failed", selector=selector, error=str(e))
            return False

    async def type_text(self, selector: str, text: str) -> bool:
        """Type text into an input field."""
        if not self._using_playwright or not self._page:
            return False
        try:
            await self._page.fill(selector, text)
            return True
        except Exception as e:
            logger.debug("type_failed", selector=selector, error=str(e))
            return False

    async def wait_for_element(self, selector: str, timeout_ms: int = 15000) -> bool:
        """Wait until an element matching the selector is visible.

        A human waits for a "Download" or "Next" button to render before
        clicking it; without this the agent clicks stale coordinates on a
        page that is still loading. No-op (True) in httpx fallback mode.
        """
        if not self._using_playwright or not self._page:
            return True
        try:
            await self._page.wait_for_selector(selector, state="visible", timeout=timeout_ms)
            return True
        except Exception as e:
            logger.debug("wait_for_element_failed", selector=selector, error=str(e))
            return False

    async def download(self, selector: str, save_path: str, timeout_ms: int = 60000) -> bool:
        """Click a download link/button and save the file to save_path.

        Models the human step: click "Download" on the website, wait for the
        file to arrive, then it is on disk ready to run. accept_downloads is
        enabled at context creation so the download stream is captured rather
        than triggering Chromium's download UI. Returns False if Playwright is
        unavailable or the download does not complete.
        """
        if not self._using_playwright or not self._page:
            return False
        try:
            async with self._page.expect_download(timeout=timeout_ms) as dl_info:
                await self._page.click(selector, timeout=5000)
            dl = await dl_info.value
            dl.save_as(save_path)
            return True
        except Exception as e:
            logger.debug("download_failed", selector=selector, save_path=save_path, error=str(e))
            return False

    async def find_interactive_elements(self) -> list[DOMElement]:
        """Find all clickable/input elements on the page."""
        if not self._using_playwright or not self._page:
            return []

        elements: list[DOMElement] = []
        for tag in ["a", "button", "input", "select", "textarea", "form"]:
            try:
                locators = self._page.locator(tag)
                count = await locators.count()
                for i in range(min(count, 50)):
                    el = locators.nth(i)
                    text = (await el.inner_text())[:100] if tag != "input" else ""
                    visible = await el.is_visible()
                    attrs = {}
                    for attr in ["href", "action", "name", "id", "type", "value"]:
                        val = await el.get_attribute(attr)
                        if val:
                            attrs[attr] = val

                    elements.append(DOMElement(
                        tag=tag,
                        text=text.strip(),
                        selector=f"{tag}:nth-of-type({i+1})",
                        attributes=attrs,
                        is_visible=visible,
                    ))
            except Exception:
                pass

        return elements

    async def extract_api_endpoints(self) -> list[str]:
        """Extract API endpoint URLs from page JavaScript and network traffic."""
        endpoints: set[str] = []
        if not self._using_playwright or not self._page:
            return list(endpoints)

        # From page content
        html = await self._page.content()
        import re
        api_patterns = re.findall(r'["\']/(api|v[0-9]+|graphql)[^"\']*["\']', html)
        for match in api_patterns:
            endpoints.add(f"/{match}")

        # From fetch/XHR URLs
        urls = await self._page.evaluate("""
            () => {
                const entries = performance.getEntriesByType('resource');
                return entries
                    .filter(e => e.initiatorType === 'fetch' || e.initiatorType === 'xmlhttprequest')
                    .map(e => e.name)
                    .slice(0, 50);
            }
        """)
        if isinstance(urls, list):
            endpoints.update(urls)

        return list(endpoints)

    async def inject_xss_payload(self, selector: str, payload: str) -> dict[str, Any]:
        """Inject XSS payload and check if it triggers."""
        if not self._using_playwright or not self._page:
            return {"injected": False, "triggered": False}

        alert_triggered = False

        async def handle_dialog(dialog):
            nonlocal alert_triggered
            alert_triggered = True
            await dialog.dismiss()

        self._page.on("dialog", handle_dialog)

        await self.type_text(selector, payload)

        # Try submitting nearby form
        try:
            form = self._page.locator(f"{selector}").locator("xpath=ancestor::form")
            if await form.count() > 0:
                submit = form.locator('button[type="submit"], input[type="submit"]')
                if await submit.count() > 0:
                    await submit.first.click()
        except Exception:
            pass

        await self._page.wait_for_timeout(2000)

        # Capture screenshot as proof
        screenshot = await self._page.screenshot(full_page=True, type="png")
        screenshot_b64 = base64.b64encode(screenshot).decode("utf-8")

        return {
            "injected": True,
            "triggered": alert_triggered,
            "payload": payload,
            "screenshot_proof": screenshot_b64,
        }

    async def close(self) -> None:
        """Close browser and cleanup. Safe to call even if launch failed."""
        # Close the page/context before stopping playwright so the browser
        # process can shut down cleanly. Each step is independent so a
        # partially-launched agent (e.g. context created but page failed)
        # still cleans up what it can.
        if self._page is not None:
            try:
                await self._page.close()
            except Exception as e:
                logger.debug("browser_page_close_error", error=str(e))
            self._page = None
        if self._context is not None:
            try:
                await self._context.close()
            except Exception as e:
                logger.debug("browser_context_close_error", error=str(e))
            self._context = None
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as e:
                logger.debug("browser_close_error", error=str(e))
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug("playwright_stop_error", error=str(e))
            self._playwright = None
        self._using_playwright = False
        logger.info("browser_agent_closed")

    async def __aenter__(self) -> BrowserAgent:
        await self.launch()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def current_page_state(self) -> tuple[str, str]:
        """Return the live (url, title) of the current page, or a blank default.

        Used by the unified computer-use loop so the observation reflects the
        page state AFTER interactions (click/type), not just the last navigate.
        """
        if self._using_playwright and self._page:
            try:
                url = self._page.url or "about:blank"
                title = await self._page.title() if self._page else ""
                return url, title
            except Exception:
                return "about:blank", ""
        return "about:blank", ""
